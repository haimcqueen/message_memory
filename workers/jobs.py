"""RQ job handlers for processing WhatsApp messages."""
import logging
import uuid
from datetime import datetime
from typing import Dict, Any
from workers.database import insert_message, create_processing_job, get_user_id_by_phone
from workers.transcription import transcribe_voice_message
from workers.session import detect_session
from workers.media import process_media_message
from workers.presence import send_presence
from utils.whapi_messaging import send_whatsapp_message
from utils.config import settings

logger = logging.getLogger(__name__)


def process_whatsapp_message(message_data: Dict[str, Any]):
    """
    Process a WhatsApp message from the webhook.

    Args:
        message_data: Message data from Whapi webhook

    This function:
    1. Determines message origin (agent vs user)
    2. Processes based on message type (text, voice, etc.)
    3. Detects or assigns session_id
    4. Stores message in Supabase
    """
    try:
        message_id = message_data["id"]
        message_type = message_data["type"]
        chat_id = message_data["chat_id"]
        from_me = message_data["from_me"]
        timestamp = message_data["timestamp"]

        # Map "short" (WhatsApp reels) to "video" for storage
        if message_type == "short":
            logger.info(f"Mapping short video to video type for message {message_id}")
            message_type = "video"

        logger.info(f"Processing message {message_id} of type {message_type}")

        # Determine origin
        origin = "agent" if from_me else "user"

        # Send typing presence for user messages
        if origin == "user":
            try:
                send_presence(chat_id, presence="typing")
            except Exception as e:
                logger.warning(f"Failed to send typing presence: {str(e)}")

        # Extract message content based on type
        content = None
        media_url = None
        extracted_media_content = None  # For storing parsed PDF content

        if message_type == "text":
            content = message_data.get("text", {}).get("body", "")

        elif message_type == "voice":
            # Transcribe voice message
            voice_data = message_data.get("voice", {})
            voice_url = voice_data.get("link")
            transcription_error = None

            if not voice_url:
                logger.warning(f"No voice URL found for voice message {message_id}")
                content = "[Voice message - no URL available]"
                media_url = None
                transcription_error = "MISSING_DATA::voice_url::no_voice_url_in_webhook"
            else:
                try:
                    logger.info(f"Transcribing voice message from {voice_url}")

                    import time
                    start_time = time.time()

                    result = transcribe_voice_message(
                        voice_url=voice_url,
                        chat_id=chat_id,
                        message_id=message_id
                    )

                    end_time = time.time()
                    duration = end_time - start_time
                    logger.info(f"Voice transcription completed in {duration:.2f} seconds")

                    content = result["transcription"]
                    media_url = result["storage_url"]
                except Exception as e:
                    logger.error(f"Failed to transcribe voice message {message_id}: {str(e)}")
                    content = "[Voice message - transcription failed]"
                    media_url = None
                    transcription_error = f"TRANSCRIPTION::{type(e).__name__}::{str(e)}"

        elif message_type in ["image", "video", "document", "audio"]:
            # Download media from Whapi and upload to Supabase Storage
            # For "short" videos, get data from the "short" field
            original_type = message_data.get("type")
            media_error = None
            pdf_parsing_error = None

            # Try to get media data from the appropriate field
            # Check both the message_type field and "short" for videos
            media_data = None
            if original_type == "short" and message_data.get("short"):
                media_data = message_data.get("short")
            elif message_data.get(message_type):
                media_data = message_data.get(message_type)

            # If media_data is None or empty dict, default to empty dict
            if not media_data:
                media_data = {}

            media_id = media_data.get("id")
            mime_type = media_data.get("mime_type")
            caption = media_data.get("caption", "")
            file_size = media_data.get("file_size", 0)  # File size in bytes

            # Default content to caption or placeholder
            content = caption if caption else f"[{message_type.title()} message]"

            # Send notifications for user messages only
            if origin == "user":
                try:
                    # Check file size and send appropriate notification
                    max_size_bytes = settings.max_file_size_mb * 1024 * 1024

                    if message_type == "video":
                        # Notify user we cannot process videos yet
                        send_whatsapp_message(chat_id, "We cannot watch videos yet.")
                        logger.info(f"Sent video notification to {chat_id}")
                    elif message_type == "document":
                        if file_size > max_size_bytes:
                            # File too large - notify and skip processing
                            send_whatsapp_message(
                                chat_id,
                                "Sorry, the file is too big, can you compress it or delete unneeded parts?"
                            )
                            logger.warning(
                                f"Document too large ({file_size / 1024 / 1024:.2f}MB > "
                                f"{settings.max_file_size_mb}MB) for message {message_id}"
                            )
                            # Set media_url to None to skip processing but still save message
                            media_url = None
                            media_error = f"FILE_TOO_LARGE::{file_size}::{settings.max_file_size_mb}MB_limit"
                            content = f"[Document too large: {file_size / 1024 / 1024:.2f}MB]"
                        else:
                            # Document is acceptable - notify processing
                            send_whatsapp_message(chat_id, "Reading the doc you're sending me")
                            logger.info(f"Sent document processing notification to {chat_id}")
                except Exception as e:
                    # Don't let notification failures block processing
                    logger.warning(f"Failed to send file notification: {str(e)}")

            # Skip processing if file was too large (already handled in notification block)
            if not media_id:
                logger.warning(f"No media_id found for {message_type} message {message_id}")
                media_url = None
                media_error = f"MISSING_DATA::media_id::{message_type}_message_{message_id}"
            elif message_type == "document" and file_size > settings.max_file_size_mb * 1024 * 1024:
                # Already notified user, just skip processing
                logger.info(f"Skipping processing for oversized document {message_id}")
            else:
                try:
                    logger.info(f"Processing {message_type} media: {media_id}")

                    # process_media_message now returns (media_url, parsed_content)
                    media_url, parsed_content = process_media_message(
                        media_id=media_id,
                        media_type=message_type,
                        chat_id=chat_id,
                        message_id=message_id,
                        mime_type=mime_type
                    )

                    if media_url:
                        logger.info(f"Successfully processed media: {media_url}")

                        # For PDFs with parsed content, store in extracted_media_content field
                        if parsed_content:
                            logger.info(f"Storing parsed PDF content ({len(parsed_content)} chars) in extracted_media_content")
                            extracted_media_content = parsed_content
                            # Keep caption in content field unchanged
                        elif mime_type == "application/pdf" and not parsed_content:
                            # PDF parsing was attempted but failed
                            logger.warning(f"PDF parsing failed or returned empty for {message_id}")
                            pdf_parsing_error = "PDF_PARSING::failed_or_empty::see_logs"
                            # Keep caption as content
                    else:
                        logger.warning(f"Media processing returned None for {message_id}")
                        media_error = f"MEDIA_PROCESSING::returned_none::{message_type}_{media_id}"
                except Exception as e:
                    logger.error(f"Failed to process {message_type} for message {message_id}: {str(e)}")
                    media_url = None
                    media_error = f"MEDIA_PROCESSING::{type(e).__name__}::{str(e)}"

        else:
            logger.warning(f"Unsupported message type: {message_type}")
            content = f"Unsupported message type: {message_type}"

        # Look up internal user_id by phone number
        # For user messages: user_id = sender (the customer)
        # For agent messages: user_id = receiver (extracted from chat_id)
        if from_me:
            # Agent message: get customer phone from chat_id
            # chat_id format: "4915202618514@s.whatsapp.net"
            customer_phone = chat_id.split("@")[0]
            logger.info(f"Agent message - looking up receiver: {customer_phone}")
        else:
            # User message: get customer phone from "from" field
            customer_phone = message_data.get("from")
            logger.info(f"User message - looking up sender: {customer_phone}")

        user_id = get_user_id_by_phone(customer_phone)

        if user_id is None:
            logger.warning(
                f"Phone number {customer_phone} not found in users table. "
                f"Message will be saved with NULL user_id."
            )

        # Detect session
        session_id = detect_session(chat_id=chat_id, message_content=content, origin=origin)

        # Convert Unix timestamp to ISO format string for Supabase
        # WhatsApp timestamp is in seconds since epoch
        message_sent_at = datetime.fromtimestamp(timestamp).isoformat()

        # Prepare message for database
        message_db_id = str(uuid.uuid4())  # Generate new UUID for our database
        db_message = {
            "id": message_db_id,
            "user_id": user_id,  # Internal user_id (from users table lookup)
            "content": content,
            "origin": origin,
            "type": message_type,
            "message_sent_at": message_sent_at,  # When the message was actually sent
            "session_id": session_id,
            "chat_id": chat_id,
            "media_url": media_url,
            "whapi_message_id": message_id,
            "extracted_media_content": extracted_media_content,  # For PDF parsed content
        }

        # Insert into database
        insert_message(db_message)

        # Add to n8n batch if this is a user message
        if not from_me:  # Only batch user messages
            logger.info(f"User message detected (from_me={from_me}), adding to n8n batch")
            try:
                from workers.batching import add_message_to_batch
                add_message_to_batch(
                    chat_id=chat_id,
                    content=content or "[No content]",
                    user_id=user_id,
                    session_id=session_id
                )
            except Exception as e:
                # Don't let batching failures block message processing
                logger.error(f"Failed to add message to n8n batch: {e}")

        # If processing failed (no media_url for media types), create a processing job
        if message_type in ["voice", "image", "video", "document", "audio"] and not media_url:
            logger.info(f"Creating processing job for failed message {message_id}")

            # Determine which error message to use
            if message_type == "voice":
                error_msg = transcription_error or f"Failed to process {message_type}: no media_url"
            else:
                # For PDFs, combine media and parsing errors if both exist
                if pdf_parsing_error and media_error:
                    error_msg = f"{media_error}||{pdf_parsing_error}"
                else:
                    error_msg = pdf_parsing_error or media_error or f"Failed to process {message_type}: no media_url"

            create_processing_job(
                message_id=message_db_id,
                webhook_payload=message_data,
                error_message=error_msg
            )

        logger.info(f"Successfully processed message {message_id}")

    except Exception as e:
        logger.error(f"Failed to process message: {str(e)}", exc_info=True)
        raise  # Re-raise to mark job as failed in RQ
