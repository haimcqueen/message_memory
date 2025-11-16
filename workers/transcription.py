"""Voice transcription using OpenAI Whisper API with retry logic."""
import logging
import httpx
from pathlib import Path
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from openai import OpenAI, APIError
from utils.config import settings
from utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.openai_api_key)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=32),
    retry=retry_if_exception_type((APIError, httpx.HTTPError)),
    reraise=True
)
def download_voice_file(voice_url: str, output_path: Path) -> None:
    """
    Download voice file from Whapi URL with retry logic.

    Args:
        voice_url: URL to download voice file from
        output_path: Local path to save the file
    """
    logger.info(f"Downloading voice file from {voice_url}")

    response = httpx.get(voice_url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    logger.info(f"Downloaded voice file to {output_path}")


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=32),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def transcribe_audio_with_whisper(audio_file_path: Path) -> str:
    """
    Transcribe audio file using OpenAI Whisper API with retry logic.

    Args:
        audio_file_path: Path to audio file

    Returns:
        Transcription text
    """
    logger.info(f"Transcribing audio file: {audio_file_path}")

    with open(audio_file_path, "rb") as audio_file:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text"
        )

    logger.info(f"Transcription completed: {transcript[:100]}...")
    return transcript


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def upload_to_supabase_storage(
    file_path: Path,
    bucket_name: str,
    storage_path: str
) -> str:
    """
    Upload file to Supabase Storage with retry logic.

    Args:
        file_path: Local file path
        bucket_name: Supabase storage bucket name
        storage_path: Path in bucket (e.g., "chat_id/message_id.ogg")

    Returns:
        Public URL of uploaded file
    """
    logger.info(f"Uploading {file_path} to Supabase Storage at {storage_path}")

    supabase = get_supabase()

    with open(file_path, "rb") as f:
        file_content = f.read()

    # Upload file
    supabase.storage.from_(bucket_name).upload(
        path=storage_path,
        file=file_content,
        file_options={"content-type": "audio/ogg"}
    )

    # Get public URL
    public_url = supabase.storage.from_(bucket_name).get_public_url(storage_path)

    logger.info(f"File uploaded successfully: {public_url}")
    return public_url


def transcribe_voice_message(
    voice_url: str,
    chat_id: str,
    message_id: str
) -> dict:
    """
    Download, transcribe, and upload voice message.

    Args:
        voice_url: Whapi voice file URL
        chat_id: WhatsApp chat ID
        message_id: Message ID

    Returns:
        Dictionary with transcription and storage_url
    """
    # Create temp directory for downloads
    temp_dir = Path("/tmp/whatsapp_voice")
    temp_dir.mkdir(exist_ok=True)

    # Download voice file
    local_file_path = temp_dir / f"{message_id}.ogg"
    download_voice_file(voice_url, local_file_path)

    # Transcribe
    transcription = transcribe_audio_with_whisper(local_file_path)

    # Upload to Supabase Storage
    storage_path = f"{chat_id}/{message_id}.ogg"
    storage_url = upload_to_supabase_storage(
        local_file_path,
        settings.media_bucket_name,
        storage_path
    )

    # Clean up local file
    local_file_path.unlink()

    return {
        "transcription": transcription,
        "storage_url": storage_url
    }
