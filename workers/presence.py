"""WhatsApp presence (typing/recording indicators) via Whapi API."""
import logging
import requests
import time
import random
from typing import Literal
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from utils.config import settings

logger = logging.getLogger(__name__)

PresenceType = Literal["typing", "recording", "paused", "available", "unavailable"]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True
)
def send_presence(chat_id: str, presence: PresenceType = "typing", delay: int = None) -> bool:
    """
    Send typing or recording presence to a WhatsApp chat via Whapi API.

    Args:
        chat_id: WhatsApp chat ID (e.g., "4915202618514@s.whatsapp.net")
        presence: Type of presence to send (typing, recording, paused, etc.)
        delay: Duration in seconds to show the presence (default: random between config min/max)

    Returns:
        True if presence was sent successfully, False otherwise
    """
    # Random typing duration if not specified
    if delay is None:
        delay = random.randint(
            settings.presence_typing_min_seconds,
            settings.presence_typing_max_seconds
        )

    url = f"{settings.whapi_api_url}/presences/{chat_id}"

    headers = {
        "Authorization": f"Bearer {settings.whapi_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "presence": presence,
        "delay": delay
    }

    logger.info(f"Sending {presence} presence to {chat_id} for {delay}s")

    try:
        response = requests.put(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()

        logger.info(f"Successfully sent {presence} presence to {chat_id}")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send presence to {chat_id}: {str(e)}")
        raise
