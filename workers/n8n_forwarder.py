"""n8n webhook forwarding with retry logic."""
import logging
import httpx
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.config import settings

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=False
)
def forward_to_n8n(payload: Dict[str, Any]) -> bool:
    """
    Forward message batch to n8n webhook with retry logic.

    Args:
        payload: Dictionary containing chat_id, user_id, session_id, messages, message_count

    Returns:
        bool: True if successful, False if all retries failed
    """
    try:
        logger.info(f"Forwarding batch to n8n for chat_id: {payload.get('chat_id')}")

        response = httpx.post(
            settings.n8n_webhook_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.n8n_webhook_api_key}",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )

        response.raise_for_status()

        logger.info(
            f"Successfully forwarded {payload.get('message_count')} messages to n8n "
            f"for chat_id: {payload.get('chat_id')}"
        )
        return True

    except httpx.HTTPError as e:
        logger.error(f"HTTP error forwarding to n8n: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error forwarding to n8n: {e}")
        raise


def safe_forward_to_n8n(payload: Dict[str, Any]) -> None:
    """
    Non-blocking wrapper for forward_to_n8n that logs failures but doesn't raise exceptions.

    This ensures that n8n forwarding failures don't block message processing.

    Args:
        payload: Dictionary containing chat_id, user_id, session_id, messages, message_count
    """
    logger.info(f"🔵 safe_forward_to_n8n called with payload: {payload}")
    try:
        logger.info(f"🔵 Calling forward_to_n8n...")
        success = forward_to_n8n(payload)
        logger.info(f"🔵 forward_to_n8n returned: {success}")
        if not success:
            logger.warning(
                f"Failed to forward batch to n8n after retries for chat_id: {payload.get('chat_id')}"
            )
    except Exception as e:
        logger.error(
            f"All retry attempts failed for n8n forwarding (chat_id: {payload.get('chat_id')}): {e}",
            exc_info=True
        )
