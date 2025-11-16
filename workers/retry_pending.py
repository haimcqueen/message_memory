"""Retry worker for processing failed media messages."""
import logging
from datetime import datetime, timedelta, timezone
from utils.supabase_client import get_supabase
from workers.transcription import transcribe_voice_message
from workers.media import process_media_message, fetch_message_from_whapi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def retry_failed_messages(max_retries: int = 3, max_age_hours: int = 48, min_retry_interval_minutes: int = 25):
    """
    Retry processing failed media messages using the message_processing_jobs table.

    Args:
        max_retries: Maximum number of retry attempts (default 3)
        max_age_hours: Maximum age of failed messages to retry (default 48 hours)
        min_retry_interval_minutes: Minimum time between retries (default 25 minutes)
    """
    supabase = get_supabase()

    logger.info("Starting retry of failed processing jobs...")

    # Calculate time threshold for minimum retry interval
    min_retry_time = (datetime.now(timezone.utc) - timedelta(minutes=min_retry_interval_minutes)).isoformat()

    # Fetch all failed jobs with retry_count < max_retries
    # Filter to only jobs that haven't been retried recently
    response = supabase.table("message_processing_jobs") \
        .select("*, messages(*)") \
        .eq("status", "failed") \
        .lt("retry_count", max_retries) \
        .or_(f"last_attempt_at.is.null,last_attempt_at.lt.{min_retry_time}") \
        .execute()

    failed_jobs = response.data
    logger.info(f"Found {len(failed_jobs)} failed jobs eligible for retry")

    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    success_count = 0
    still_failed_count = 0
    too_old_count = 0
    max_retries_count = 0

    for job in failed_jobs:
        job_id = job["id"]
        message_id = job["message_id"]
        retry_count = job.get("retry_count", 0)
        webhook_payload = job.get("webhook_payload")
        created_at = datetime.fromisoformat(job["created_at"].replace('Z', '+00:00'))

        # Get message data from joined query
        message = job.get("messages")
        if not message:
            logger.warning(f"No message found for job {job_id}, skipping")
            still_failed_count += 1
            continue

        message_type = message["type"]
        chat_id = message["chat_id"]
        whapi_message_id = message["whapi_message_id"]

        # Check if job is too old
        if created_at < cutoff_time:
            logger.warning(f"Job {job_id} is older than {max_age_hours}h, skipping")
            too_old_count += 1
            continue

        # Check if already at max retries
        if retry_count >= max_retries:
            logger.warning(f"Job {job_id} already at max retries ({retry_count}), skipping")
            max_retries_count += 1
            continue

        if not webhook_payload:
            error_msg = f"MISSING_DATA::webhook_payload::job_{job_id}_{message_type}"
            logger.warning(f"No webhook payload for job {job_id}, skipping")
            supabase.table("message_processing_jobs") \
                .update({
                    "retry_count": retry_count + 1,
                    "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                    "error_message": error_msg
                }) \
                .eq("id", job_id) \
                .execute()
            still_failed_count += 1
            continue

        logger.info(f"Retrying {message_type} for job {job_id} (attempt {retry_count + 1}/{max_retries})...")

        try:
            media_url = None
            content = message["content"]  # Keep existing content
            extracted_media_content = None  # For PDF parsed content

            if message_type == "voice":
                voice_data = webhook_payload.get("voice", {})
                voice_url = voice_data.get("link")

                if voice_url:
                    result = transcribe_voice_message(
                        voice_url=voice_url,
                        chat_id=chat_id,
                        message_id=whapi_message_id
                    )
                    content = result["transcription"]
                    media_url = result["storage_url"]
                else:
                    error_msg = f"MISSING_DATA::voice_url::job_{job_id}_message_{whapi_message_id}"
                    logger.warning(f"No voice URL in webhook payload for job {job_id}")
                    supabase.table("message_processing_jobs") \
                        .update({
                            "retry_count": retry_count + 1,
                            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": error_msg
                        }) \
                        .eq("id", job_id) \
                        .execute()
                    still_failed_count += 1
                    continue

            elif message_type in ["image", "video", "document", "audio"]:
                # Get media data from webhook payload
                original_type = webhook_payload.get("type")

                # Try to get media data from the appropriate field
                media_data = None
                if original_type == "short" and webhook_payload.get("short"):
                    media_data = webhook_payload.get("short")
                elif webhook_payload.get(message_type):
                    media_data = webhook_payload.get(message_type)

                if not media_data:
                    media_data = {}

                media_id = media_data.get("id")
                mime_type = media_data.get("mime_type")

                # If no media_id in webhook payload, try fetching from Whapi API
                if not media_id:
                    logger.warning(f"No media_id in webhook payload for job {job_id}, trying Whapi API fallback...")
                    try:
                        # Fetch full message data from Whapi API
                        api_message_data = fetch_message_from_whapi(whapi_message_id)

                        if api_message_data:
                            # Extract media data from API response
                            api_original_type = api_message_data.get("type")
                            if api_original_type == "short":
                                media_data = api_message_data.get("short", {})
                            else:
                                media_data = api_message_data.get(message_type, {})

                            media_id = media_data.get("id")
                            mime_type = media_data.get("mime_type")

                            if media_id:
                                logger.info(f"Successfully fetched media_id from Whapi API: {media_id}")
                            else:
                                logger.warning(f"Whapi API response also missing media_id for job {job_id}")
                        else:
                            logger.warning(f"Whapi API returned None for job {job_id}")

                    except Exception as e:
                        logger.error(f"Failed to fetch from Whapi API for job {job_id}: {str(e)}")

                # Now try to process the media if we have media_id
                if media_id:
                    # process_media_message now returns (media_url, parsed_content)
                    media_url, parsed_content = process_media_message(
                        media_id=media_id,
                        media_type=message_type,
                        chat_id=chat_id,
                        message_id=whapi_message_id,
                        mime_type=mime_type
                    )

                    # For PDFs, store parsed content in extracted_media_content field
                    if parsed_content and mime_type == "application/pdf":
                        logger.info(f"Storing parsed PDF content ({len(parsed_content)} chars) in extracted_media_content")
                        extracted_media_content = parsed_content
                else:
                    error_msg = f"MISSING_DATA::media_id::{message_type}_message_{whapi_message_id}::whapi_api_fallback_failed"
                    logger.warning(f"No media_id available for job {job_id} after all attempts")
                    supabase.table("message_processing_jobs") \
                        .update({
                            "retry_count": retry_count + 1,
                            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                            "error_message": error_msg
                        }) \
                        .eq("id", job_id) \
                        .execute()
                    still_failed_count += 1
                    continue

            # Update message with media_url and mark job as completed
            if media_url:
                # Update the message
                update_data = {
                    "media_url": media_url,
                    "content": content
                }
                # Add extracted_media_content if we have it
                if extracted_media_content is not None:
                    update_data["extracted_media_content"] = extracted_media_content

                supabase.table("messages") \
                    .update(update_data) \
                    .eq("id", message_id) \
                    .execute()

                # Mark job as completed
                supabase.table("message_processing_jobs") \
                    .update({
                        "status": "completed",
                        "retry_count": retry_count + 1,
                        "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                        "webhook_payload": None  # Clear payload on success
                    }) \
                    .eq("id", job_id) \
                    .execute()

                logger.info(f"Successfully retried job {job_id} on attempt {retry_count + 1}")
                success_count += 1
            else:
                logger.warning(f"Media processing returned None for job {job_id}")
                # Increment retry_count but keep status as failed
                supabase.table("message_processing_jobs") \
                    .update({
                        "retry_count": retry_count + 1,
                        "last_attempt_at": datetime.now(timezone.utc).isoformat()
                    }) \
                    .eq("id", job_id) \
                    .execute()
                still_failed_count += 1

        except Exception as e:
            error_msg = f"RETRY_FAILED::{message_type}::attempt_{retry_count + 1}/{max_retries}::{type(e).__name__}::{str(e)}"
            logger.error(f"Failed to retry job {job_id}: {str(e)}")
            # Increment retry_count even on exception
            supabase.table("message_processing_jobs") \
                .update({
                    "retry_count": retry_count + 1,
                    "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                    "error_message": error_msg
                }) \
                .eq("id", job_id) \
                .execute()
            still_failed_count += 1

    logger.info(
        f"Retry complete: {success_count} succeeded, {still_failed_count} still failed, "
        f"{too_old_count} too old, {max_retries_count} at max retries"
    )
    return {
        "success": success_count,
        "still_failed": still_failed_count,
        "too_old": too_old_count,
        "max_retries": max_retries_count
    }


if __name__ == "__main__":
    retry_failed_messages()
