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
        - session_id: UUID
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
