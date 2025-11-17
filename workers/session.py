"""Session detection using LLM with retry logic."""
import logging
import uuid
from datetime import datetime, timedelta
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from openai import OpenAI, APIError
from utils.config import settings
from utils.supabase_client import get_supabase
from prompts.session_detection import get_session_detection_messages

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.openai_api_key)


def get_recent_messages(chat_id: str, limit: int = 20) -> list[dict]:
    """
    Fetch recent messages for a chat from Supabase.

    Args:
        chat_id: WhatsApp chat ID
        limit: Number of recent messages to fetch

    Returns:
        List of message dictionaries
    """
    supabase = get_supabase()

    try:
        response = supabase.table("messages") \
            .select("*") \
            .eq("chat_id", chat_id) \
            .order("message_sent_at", desc=True) \
            .limit(limit) \
            .execute()

        return response.data
    except Exception as e:
        logger.error(f"Error fetching recent messages: {str(e)}")
        return []


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def call_llm_for_session_detection(
    recent_messages: list[dict],
    new_message_content: str
) -> bool:
    """
    Use LLM to determine if new message belongs to the same session.

    Args:
        recent_messages: List of recent messages from the current session (up to 10)
        new_message_content: Content of the new message

    Returns:
        True if same session, False if new session needed
    """
    logger.info("Calling LLM for session detection")

    response = openai_client.chat.completions.create(
        model=settings.openai_session_model,
        messages=get_session_detection_messages(recent_messages, new_message_content),
        temperature=0.0,
        max_tokens=10
    )

    answer = response.choices[0].message.content.strip().lower()
    logger.info(f"LLM session detection answer: {answer}")

    return answer == "yes"


def detect_session(chat_id: str, message_content: str, origin: str) -> str:
    """
    Detect or assign session ID for a message.

    Logic:
    1. Fetch recent messages for the chat
    2. If no previous messages or last message >24h old: new session
    3. If only agent messages so far: continue same session
    4. Otherwise: ask LLM if same topic
    5. Return existing session_id or generate new UUID

    Args:
        chat_id: WhatsApp chat ID
        message_content: Content of the new message
        origin: Message origin (agent or user)

    Returns:
        Session ID (UUID string)
    """
    logger.info(f"Detecting session for chat {chat_id}")

    # Fetch recent messages
    recent_messages = get_recent_messages(chat_id, limit=20)

    # Case 1: No previous messages - create new session
    if not recent_messages:
        logger.info("No previous messages found - creating new session")
        return str(uuid.uuid4())

    # Get the most recent message
    latest_message = recent_messages[0]
    latest_sent_at = latest_message.get("message_sent_at")

    # If no message_sent_at (old messages before migration), create new session
    if not latest_sent_at:
        logger.info("No message_sent_at found in latest message - creating new session")
        return str(uuid.uuid4())

    # Parse the timestamp (it's already a datetime string from Supabase)
    if isinstance(latest_sent_at, str):
        latest_datetime = datetime.fromisoformat(latest_sent_at.replace('Z', '+00:00'))
    else:
        latest_datetime = latest_sent_at

    time_diff = datetime.now(latest_datetime.tzinfo) - latest_datetime

    # Case 2: Last message was >24 hours ago - create new session
    if time_diff > timedelta(hours=24):
        logger.info(f"Last message was {time_diff} ago - creating new session")
        return str(uuid.uuid4())

    # Case 3: Only agent messages so far - continue same session
    # (Agent might be following up, waiting for user response)
    if all(msg["origin"] == "agent" for msg in recent_messages):
        logger.info("Only agent messages found - continuing same session")
        return latest_message["session_id"]

    # Case 4: Get messages from current session and ask LLM to determine if same topic
    current_session_id = latest_message["session_id"]

    # Filter messages that belong to the current session, take last 10
    session_messages = [msg for msg in recent_messages if msg.get("session_id") == current_session_id][:10]

    logger.info(f"Analyzing {len(session_messages)} messages from current session {current_session_id}")

    try:
        same_topic = call_llm_for_session_detection(
            session_messages,
            message_content
        )

        if same_topic:
            logger.info("LLM detected same topic - continuing session")
            return current_session_id
        else:
            logger.info("LLM detected new topic - creating new session")
            return str(uuid.uuid4())

    except Exception as e:
        logger.error(f"Error in LLM session detection: {str(e)}")
        # Fallback: continue same session on error
        logger.info("Falling back to continuing same session due to error")
        return current_session_id
