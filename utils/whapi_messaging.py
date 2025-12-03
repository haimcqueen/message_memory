"""WhatsApp message sending via Whapi API."""
import logging
import requests
from typing import Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from utils.config import settings
from workers.database import get_subscription_status_by_phone

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True
)
def send_whatsapp_message(chat_id: str, message: str) -> bool:
    """
    Send a text message to a WhatsApp chat via Whapi API.

    Args:
        chat_id: WhatsApp chat ID (e.g., "4915202618514@s.whatsapp.net")
        message: Text message to send

    Returns:
        True if message was sent successfully, False otherwise
    """
    # Check if user is a pilot user - skip sending if so
    phone = chat_id.split("@")[0]
    try:
        subscription_status = get_subscription_status_by_phone(phone)
        if subscription_status == "pilot":
            logger.info(f"Skipping message to pilot user {chat_id}: {message[:50]}...")
            return True  # Pretend success so callers don't treat as failure
    except Exception as e:
        # If we can't check subscription status, proceed with sending
        logger.warning(f"Could not check subscription status for {phone}: {e}")

    url = f"{settings.whapi_api_url}/messages/text"

    headers = {
        "Authorization": f"Bearer {settings.whapi_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "to": chat_id,
        "body": message
    }

    logger.info(f"Sending WhatsApp message to {chat_id}: {message[:50]}...")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()

        logger.info(f"Successfully sent message to {chat_id}")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send message to {chat_id}: {str(e)}")
        raise
