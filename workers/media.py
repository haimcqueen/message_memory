"""Media handling for WhatsApp attachments."""
import logging
import requests
import io
import base64
from typing import Optional, Tuple, Dict, Any
from utils.config import settings
from utils.supabase_client import get_supabase
from openai import OpenAI, APIError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from prompts.pdf_parsing import get_pdf_parsing_messages
from prompts.image_parsing import get_image_parsing_messages

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.openai_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def fetch_message_from_whapi(message_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full message data from Whapi API.

    This is a fallback for when webhooks arrive without media objects.
    The API endpoint includes complete message data with media links.

    Args:
        message_id: The Whapi message ID

    Returns:
        Complete message object dict, or None if fetch fails
    """
    url = f"{settings.whapi_api_url}/messages/{message_id}"

    headers = {
        "Authorization": f"Bearer {settings.whapi_token}"
    }

    logger.info(f"Fetching message data from Whapi API: {message_id}")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        message_data = response.json()
        logger.info(f"Successfully fetched message {message_id} from Whapi API")

        return message_data

    except Exception as e:
        logger.error(f"Error fetching message from Whapi API: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def download_media_from_whapi(media_id: str, media_type: str) -> Tuple[bytes, str]:
    """
    Download media file from Whapi API.

    Args:
        media_id: The media ID from Whapi webhook
        media_type: Type of media (image, video, audio, document)

    Returns:
        Tuple of (file_content, mime_type)
    """
    url = f"{settings.whapi_api_url}/media/{media_id}"

    headers = {
        "Authorization": f"Bearer {settings.whapi_token}"
    }

    logger.info(f"Downloading {media_type} from Whapi: {media_id}")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "application/octet-stream")
        logger.info(f"Downloaded {len(response.content)} bytes, content-type: {content_type}")

        return response.content, content_type

    except Exception as e:
        logger.error(f"Error downloading media from Whapi: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
def upload_to_supabase_storage(
    file_content: bytes,
    file_path: str,
    content_type: str
) -> str:
    """
    Upload file to Supabase Storage.

    Args:
        file_content: File bytes
        file_path: Path within bucket (e.g., "images/chat_id/message_id.jpg")
        content_type: MIME type

    Returns:
        Public URL of uploaded file
    """
    supabase = get_supabase()
    bucket_name = settings.media_bucket_name

    logger.info(f"Uploading to Supabase Storage: {bucket_name}/{file_path}")

    try:
        # Upload file
        supabase.storage.from_(bucket_name).upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": content_type}
        )

        # Get public URL
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)

        logger.info(f"Successfully uploaded to: {public_url}")
        return public_url

    except Exception as e:
        logger.error(f"Error uploading to Supabase Storage: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def parse_pdf_with_openai(file_content: bytes, filename: str = "document.pdf") -> str:
    """
    Parse PDF content using OpenAI Files API + Chat Completions with visual descriptions.

    Args:
        file_content: PDF file bytes
        filename: Name of the PDF file (for API context)

    Returns:
        Extracted text and visual descriptions from PDF
    """
    logger.info(f"Parsing PDF with OpenAI ({len(file_content)} bytes, filename: {filename})")

    try:
        # Upload file to OpenAI Files API first
        logger.info("Uploading PDF to OpenAI Files API...")
        file_response = openai_client.files.create(
            file=(filename, file_content, "application/pdf"),
            purpose="assistants"
        )
        file_id = file_response.id
        logger.info(f"PDF uploaded with file_id: {file_id}")

        # Use the file in Chat Completions API
        completion = openai_client.chat.completions.create(
            model=settings.openai_pdf_model,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": get_pdf_parsing_messages(filename, "")[0]["content"][0]["text"]  # Get prompt from helper
                    },
                    {
                        "type": "file",
                        "file": {
                            "file_id": file_id
                        }
                    }
                ]
            }]
        )

        extracted_content = completion.choices[0].message.content
        logger.info(f"PDF parsing completed: {len(extracted_content)} characters extracted")

        # Clean up: delete the uploaded file
        try:
            openai_client.files.delete(file_id)
            logger.info(f"Deleted file {file_id} from OpenAI")
        except Exception as del_error:
            logger.warning(f"Failed to delete file {file_id}: {del_error}")

        return extracted_content if extracted_content else "[PDF - no content extracted]"

    except Exception as e:
        logger.error(f"Failed to parse PDF with OpenAI: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    retry=retry_if_exception_type(APIError),
    reraise=True
)
def parse_image_with_openai(file_content: bytes, filename: str = "image.jpg") -> str:
    """
    Parse image content using OpenAI Vision API.

    Args:
        file_content: Image file bytes
        filename: Name of the image file (for logging context)

    Returns:
        Extracted text and visual descriptions from image
    """
    logger.info(f"Parsing image with OpenAI Vision ({len(file_content)} bytes, filename: {filename})")

    try:
        # Convert image bytes to base64
        base64_image = base64.b64encode(file_content).decode('utf-8')
        logger.info(f"Converted image to base64 ({len(base64_image)} characters)")

        # Use Vision API via Chat Completions
        completion = openai_client.chat.completions.create(
            model=settings.openai_vision_model,
            messages=get_image_parsing_messages(base64_image)
        )

        extracted_content = completion.choices[0].message.content
        logger.info(f"Image parsing completed: {len(extracted_content)} characters extracted")

        return extracted_content if extracted_content else "[Image - no content extracted]"

    except Exception as e:
        logger.error(f"Failed to parse image with OpenAI: {str(e)}")
        raise


def process_media_message(
    media_id: str,
    media_type: str,
    chat_id: str,
    message_id: str,
    mime_type: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Download media from Whapi and upload to Supabase Storage.
    For PDFs and images, also parse the content using OpenAI Vision API.

    Args:
        media_id: Whapi media ID
        media_type: Type (image, video, audio, document)
        chat_id: WhatsApp chat ID
        message_id: Message ID
        mime_type: MIME type from webhook

    Returns:
        Tuple of (public_url, parsed_content)
        - public_url: Public URL of stored media, or None if failed
        - parsed_content: Extracted content for PDFs/images, or None for other media types
    """
    try:
        # Download from Whapi
        file_content, content_type = download_media_from_whapi(media_id, media_type)

        # Parse PDF or image content if applicable
        parsed_content = None
        if content_type == "application/pdf":
            try:
                logger.info(f"Attempting to parse PDF content for {message_id}")
                # Use message_id as filename for better context
                parsed_content = parse_pdf_with_openai(file_content, filename=f"{message_id}.pdf")
            except Exception as e:
                logger.error(f"PDF parsing failed for {message_id}: {str(e)}")
                # Continue with upload even if parsing fails
                parsed_content = None
        elif content_type in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
            try:
                logger.info(f"Attempting to parse image content for {message_id}")
                # Determine file extension for better context
                ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
                extension = ext_map.get(content_type, "jpg")
                parsed_content = parse_image_with_openai(file_content, filename=f"{message_id}.{extension}")
            except Exception as e:
                logger.error(f"Image parsing failed for {message_id}: {str(e)}")
                # Continue with upload even if parsing fails
                parsed_content = None

        # Determine file extension from mime type
        ext_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
            "video/mp4": "mp4",
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "application/pdf": "pdf",
        }
        extension = ext_map.get(content_type, mime_type.split("/")[-1] if mime_type else "bin")

        # Create storage path: media_type/chat_id/message_id.ext
        # Clean chat_id (remove @s.whatsapp.net)
        clean_chat_id = chat_id.split("@")[0]
        file_path = f"{media_type}/{clean_chat_id}/{message_id}.{extension}"

        # Upload to Supabase Storage
        public_url = upload_to_supabase_storage(file_content, file_path, content_type)

        return public_url, parsed_content

    except Exception as e:
        logger.error(f"Failed to process media: {str(e)}")
        return None, None
