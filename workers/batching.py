"""Message batching logic for n8n webhook forwarding."""
import logging
from datetime import timedelta
from typing import Optional
from redis import Redis
from rq import Queue
from rq.job import Job
from utils.config import settings

logger = logging.getLogger(__name__)

# Redis keys
BATCH_COUNT_PREFIX = "n8n_count:"
BATCH_USER_ID_PREFIX = "n8n_user:"
BATCH_JOB_ID_PREFIX = "n8n_job:"

# Batch delay in seconds (1 minute)
BATCH_DELAY_SECONDS = 60


def get_redis_connection() -> Redis:
    """Get Redis connection."""
    return Redis.from_url(settings.redis_url)


def add_message_to_batch(
    chat_id: str,
    content: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> None:
    """
    Increment message counter and schedule/reschedule the batch processing job.

    Only user messages (from_me != true) should call this function.

    Args:
        chat_id: WhatsApp chat ID
        content: Message content (not used, kept for backward compatibility)
        user_id: User ID from database
        session_id: Session ID from database (not used, kept for backward compatibility)
    """
    redis_conn = get_redis_connection()
    count_key = f"{BATCH_COUNT_PREFIX}{chat_id}"
    user_id_key = f"{BATCH_USER_ID_PREFIX}{chat_id}"
    job_id_key = f"{BATCH_JOB_ID_PREFIX}{chat_id}"

    try:
        # Increment message counter
        redis_conn.incr(count_key)
        logger.info(f"Incremented message count for chat_id: {chat_id}")

        # Store user_id
        if user_id:
            redis_conn.set(user_id_key, user_id)

        # Cancel existing scheduled job if it exists
        existing_job_id = redis_conn.get(job_id_key)
        if existing_job_id:
            try:
                existing_job = Job.fetch(existing_job_id.decode(), connection=redis_conn)
                if existing_job and existing_job.get_status() in ['queued', 'scheduled']:
                    existing_job.cancel()
                    logger.info(f"Cancelled existing batch job {existing_job_id.decode()} for chat_id: {chat_id}")
            except Exception as e:
                logger.warning(f"Could not cancel existing job: {e}")

        # Schedule new batch processing job
        queue = Queue("whatsapp-messages", connection=redis_conn)
        job = queue.enqueue_in(
            timedelta(seconds=BATCH_DELAY_SECONDS),
            process_and_forward_batch,
            chat_id,
            job_timeout="5m"
        )

        # Store new job ID
        redis_conn.set(job_id_key, job.id)
        logger.info(
            f"Scheduled batch processing job {job.id} for chat_id: {chat_id} "
            f"(will fire in {BATCH_DELAY_SECONDS} seconds)"
        )

    except Exception as e:
        logger.error(f"Error adding message to batch for chat_id {chat_id}: {e}")
        raise


def process_and_forward_batch(chat_id: str) -> None:
    """
    Process and forward the batch to n8n with message count and user_id.

    This is the RQ job that fires after the delay period.

    Args:
        chat_id: WhatsApp chat ID
    """
    redis_conn = get_redis_connection()
    count_key = f"{BATCH_COUNT_PREFIX}{chat_id}"
    user_id_key = f"{BATCH_USER_ID_PREFIX}{chat_id}"
    job_id_key = f"{BATCH_JOB_ID_PREFIX}{chat_id}"

    try:
        # Get message count
        message_count = redis_conn.get(count_key)
        if not message_count:
            logger.warning(f"No message count in batch for chat_id: {chat_id}")
            return

        message_count = int(message_count.decode())

        # Get user_id
        user_id = redis_conn.get(user_id_key)
        user_id = user_id.decode() if user_id else None

        logger.info(
            f"Processing batch for chat_id: {chat_id} "
            f"({message_count} messages, user_id: {user_id})"
        )

        # Prepare simplified payload for n8n
        payload = {
            "user_id": user_id,
            "batched_message_count": message_count
        }

        # Forward to n8n
        from workers.n8n_forwarder import safe_forward_to_n8n
        safe_forward_to_n8n(payload)

        # Clear the batch from Redis
        redis_conn.delete(count_key)
        redis_conn.delete(user_id_key)
        redis_conn.delete(job_id_key)

        logger.info(f"Successfully processed and cleared batch for chat_id: {chat_id}")

    except Exception as e:
        logger.error(f"Error processing batch for chat_id {chat_id}: {e}")
        # Don't re-raise - we don't want RQ to retry this job
        # The batch will remain in Redis and can be manually inspected/cleared
