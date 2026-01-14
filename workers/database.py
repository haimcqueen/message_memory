"""Supabase database operations with retry logic."""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)
from utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def get_user_id_by_phone(phone_number: str) -> Optional[str]:
    """
    Look up internal user_id by phone number in users table.

    Args:
        phone_number: Phone number from WhatsApp (e.g., "5551234567890")

    Returns:
        Internal user_id if found, None otherwise
    """
    supabase = get_supabase()

    logger.info(f"Looking up user_id for phone number: {phone_number}")

    try:
        response = supabase.table("users") \
            .select("id") \
            .eq("phone", phone_number) \
            .limit(1) \
            .execute()

        if response.data and len(response.data) > 0:
            user_id = response.data[0]["id"]
            logger.info(f"Found user_id: {user_id} for phone: {phone_number}")
            return user_id
        else:
            logger.warning(f"No user found for phone number: {phone_number}")
            return None

    except Exception as e:
        logger.error(f"Error looking up user by phone: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def get_subscription_status_by_phone(phone_number: str) -> Optional[str]:
    """
    Look up subscription_status by phone number in users table.

    Args:
        phone_number: Phone number from WhatsApp (e.g., "5551234567890")

    Returns:
        subscription_status if found, None otherwise
    """
    supabase = get_supabase()

    logger.info(f"Looking up subscription_status for phone number: {phone_number}")

    try:
        response = supabase.table("users") \
            .select("subscription_status") \
            .eq("phone", phone_number) \
            .limit(1) \
            .execute()

        if response.data and len(response.data) > 0:
            status = response.data[0].get("subscription_status")
            logger.info(f"Found subscription_status: {status} for phone: {phone_number}")
            return status
        else:
            logger.warning(f"No user found for phone number: {phone_number}")
            return None

    except Exception as e:
        logger.error(f"Error looking up subscription_status by phone: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def get_chat_id_by_user_id(user_id: str) -> Optional[str]:
    """
    Get the most recent chat_id for a user.

    Args:
        user_id: Internal user ID

    Returns:
        chat_id if found, None otherwise
    """
    supabase = get_supabase()

    logger.info(f"Looking up chat_id for user_id: {user_id}")

    try:
        # Get the most recent message for this user to find their chat_id
        response = supabase.table("messages") \
            .select("chat_id") \
            .eq("user_id", user_id) \
            .order("message_sent_at", desc=True) \
            .limit(1) \
            .execute()

        if response.data and len(response.data) > 0:
            chat_id = response.data[0]["chat_id"]
            logger.info(f"Found chat_id: {chat_id} for user_id: {user_id}")
            return chat_id
        else:
            logger.warning(f"No messages found for user_id: {user_id}")
            return None

    except Exception as e:
        logger.error(f"Error looking up chat_id by user_id: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def insert_message(message_data: Dict[str, Any]) -> None:
    """
    Insert message into Supabase messages table with retry logic.

    Args:
        message_data: Message data to insert

    Expected fields:
        - id: UUID
        - user_id: Internal user ID (from users table lookup)
        - content: Message text/transcription
        - origin: "agent" or "user"
        - type: Message type (text, voice, etc.)
        - message_sent_at: When the message was actually sent
        - chat_id: WhatsApp chat ID
        - media_url: Optional URL to media file
        - whapi_message_id: Original Whapi message ID

    Note: Retry/processing logic is now handled in message_processing_jobs table
    """
    supabase = get_supabase()

    logger.info(f"Inserting message {message_data['id']} into database")

    try:
        response = supabase.table("messages").insert(message_data).execute()
        logger.info(f"Successfully inserted message {message_data['id']}")
    except Exception as e:
        error_str = str(e)

        # Check if this is a duplicate whapi_message_id error
        if "duplicate key value violates unique constraint" in error_str and "whapi_message_id" in error_str:
            logger.warning(f"Message with whapi_message_id={message_data.get('whapi_message_id')} already exists. Skipping duplicate.")
            # Don't raise - this is expected behavior for duplicate messages
            return

        logger.error(f"Error inserting message: {error_str}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def update_message_content(message_id: str, content: str = None, media_url: str = None, extracted_media_content: str = None) -> None:
    """
    Update message content/media_url after processing (e.g. transcription).
    """
    supabase = get_supabase()
    logger.info(f"Updating message {message_id} with new content/media")

    updates = {}
    if content is not None:
        updates["content"] = content
    if media_url is not None:
        updates["media_url"] = media_url
    if extracted_media_content is not None:
        updates["extracted_media_content"] = extracted_media_content
        
    if not updates:
        return

    try:
        supabase.table("messages") \
            .update(updates) \
            .eq("id", message_id) \
            .execute()
        logger.info(f"Successfully updated message {message_id}")
    except Exception as e:
        logger.error(f"Error updating message {message_id}: {e}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def create_processing_job(
    message_id: str,
    webhook_payload: Dict[str, Any],
    error_message: Optional[str] = None
) -> None:
    """
    Create a processing job for a failed message.

    Args:
        message_id: UUID of the message in messages table
        webhook_payload: Original webhook data for retry
        error_message: Optional error message from the failure
    """
    supabase = get_supabase()

    logger.info(f"Creating processing job for message {message_id}")

    job_data = {
        "message_id": message_id,
        "status": "failed",
        "retry_count": 0,
        "max_retries": 3,
        "webhook_payload": webhook_payload,
        "last_attempt_at": datetime.utcnow().isoformat(),
        "next_retry_at": datetime.utcnow().isoformat(),
        "error_message": error_message,
    }

    try:
        response = supabase.table("message_processing_jobs").insert(job_data).execute()
        logger.info(f"Successfully created processing job: {response.data[0]['id']}")
    except Exception as e:
        logger.error(f"Error creating processing job: {str(e)}")
        # Don't raise here - we don't want to fail the message insert if job creation fails
        # The message will still be in the DB without media_url, just won't have a retry job


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def update_processing_job_success(job_id: str) -> None:
    """
    Mark a processing job as completed.

    Args:
        job_id: UUID of the job in message_processing_jobs table
    """
    supabase = get_supabase()

    logger.info(f"Marking job {job_id} as completed")

    try:
        supabase.table("message_processing_jobs") \
            .update({
                "status": "completed",
                "last_attempt_at": datetime.utcnow().isoformat(),
                "webhook_payload": None  # Clear payload on success
            }) \
            .eq("id", job_id) \
            .execute()
        logger.info(f"Successfully marked job {job_id} as completed")
    except Exception as e:
        logger.error(f"Error updating job status: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def update_processing_job_failure(
    job_id: str,
    retry_count: int,
    error_message: Optional[str] = None
) -> None:
    """
    Update a processing job after a failed retry attempt.

    Args:
        job_id: UUID of the job in message_processing_jobs table
        retry_count: New retry count
        error_message: Optional error message from this attempt
    """
    supabase = get_supabase()

    logger.info(f"Updating job {job_id} retry count to {retry_count}")

    try:
        supabase.table("message_processing_jobs") \
            .update({
                "retry_count": retry_count,
                "last_attempt_at": datetime.utcnow().isoformat(),
                "error_message": error_message
            }) \
            .eq("id", job_id) \
            .execute()
        logger.info(f"Successfully updated job {job_id}")
    except Exception as e:
        logger.error(f"Error updating job: {str(e)}")
        raise

def store_memory(user_id: str, content: str, embedding: list[float]):
    """
    Store a new memory (fact) for a user.
    """
    supabase = get_supabase()
    try:
        supabase.table("memories").insert({
            "user_id": user_id,
            "content": content,
            "embedding": embedding
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Error storing memory: {e}")
        return False

def search_memories(user_id: str, query_embedding: list[float], limit: int = 5) -> list[dict]:
    """
    Search for memories similar to the query embedding.
    """
    supabase = get_supabase() # Added this line as it was missing in the snippet
    logger.info(f"Searching memories for user_id: {user_id}") # Added this line for logging

    try:
        response = supabase.rpc("match_memories", {
            "query_embedding": query_embedding,
            "match_threshold": 0.35, # Lowered from 0.5 for better recall
            "match_count": limit,
            "p_user_id": user_id
        }).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error searching memories: {e}")
        return []

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def get_publyc_persona(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the publyc_persona for a user.
    
    Args:
        user_id: Internal user ID
        
    Returns:
        Persona dict if found, None otherwise
    """
    supabase = get_supabase()
    logger.info(f"Fetching publyc_persona for user_id: {user_id}")
    
    try:
        response = supabase.table("publyc_personas") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()
            
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
        
    except Exception as e:
        logger.error(f"Error fetching publyc_persona: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def update_publyc_persona_field(user_id: str, field: str, value: str) -> None:
    """
    Update a specific field in the publyc_personas table.
    
    Args:
        user_id: Internal user ID
        field: The column name to update
        value: The new value
    """
    supabase = get_supabase()
    logger.info(f"Updating publyc_persona field '{field}' for user_id: {user_id}")
    
    try:
        supabase.table("publyc_personas") \
            .update({field: value, "updated_at": datetime.utcnow().isoformat()}) \
            .eq("user_id", user_id) \
            .execute()
        logger.info(f"Successfully updated publyc_persona field '{field}'")
        
    except Exception as e:
        logger.error(f"Error updating publyc_persona: {str(e)}")
        raise
