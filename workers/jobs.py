"""RQ job handlers for processing WhatsApp messages."""
import workers.logging_config  # Initialize logging for worker processes
import logging
import uuid
from datetime import datetime
from typing import Dict, Any
from workers.database import (
    get_user_id_by_phone,
    get_subscription_status_by_phone,
    insert_message,
    get_publyc_persona,
    update_publyc_persona_field
)
from workers.transcription import transcribe_voice_message
from workers.media import process_media_message
from workers.presence import send_presence
from utils.whapi_messaging import send_whatsapp_message
from utils.config import settings
from supadata import Supadata
from utils.llm import classify_message, process_persona_update
import re

logger = logging.getLogger(__name__)

# Initialize Supadata client
supadata_client = Supadata(api_key=settings.supadata_api_key)

# Regex to match YouTube URLs (video ID is group 1)
YOUTUBE_REGEX = r"(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/(?:watch\?v=|shorts/|embed/)?([a-zA-Z0-9_-]{11})"

# Generic URL Regex (simple version to catch most links)
URL_REGEX = r"(?:https?://)?(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)"

# Domains to exclude from generic crawler (YouTube has its own handler)
EXCLUDED_DOMAINS = ["twitter.com", "x.com", "linkedin.com", "tiktok.com", "facebook.com", "instagram.com"]


def process_whatsapp_message(message_data: Dict[str, Any]):
    """
    Process a WhatsApp message from the webhook.

    Args:
        message_data: Message data from Whapi webhook

    This function:
    1. Determines message origin (agent vs user)
    2. Processes based on message type (text, voice, etc.)
    3. Stores message in Supabase
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

        # Reject messages from unknown phone numbers (not in users table)
        if user_id is None and not from_me:
            logger.warning(
                f"Rejecting message from unknown phone number: {customer_phone}. "
                f"Number not found in users table."
            )
            try:
                send_whatsapp_message(
                    chat_id,
                    "Unfortunately this number is not known to us - please contact the publyc team or sign up for the waitlist at https://www.publyc.app/"
                )
                logger.info(f"Sent rejection message to {customer_phone}")
            except Exception as e:
                logger.error(f"Failed to send rejection message to {customer_phone}: {e}")

            # Exit early - do not insert to database or trigger n8n batching
            return

        # Skip database insertion for agent messages to unknown users
        if user_id is None and from_me:
            logger.info(
                f"Skipping database insertion for agent message to unknown user: {customer_phone}"
            )
            return

        # Get subscription status early for pilot user checks (presence, messages, n8n)
        phone_from_chat = chat_id.split("@")[0]
        subscription_status = None
        try:
            subscription_status = get_subscription_status_by_phone(phone_from_chat)
        except Exception as e:
            logger.warning(f"Could not get subscription status for {phone_from_chat}: {e}")

        is_pilot = subscription_status == "pilot"

        # Send typing presence for user messages (skip for pilot users)
        if origin == "user" and not is_pilot:
            try:
                send_presence(chat_id, presence="typing")
            except Exception as e:
                logger.warning(f"Failed to send typing presence: {str(e)}")

        # Extract message content based on type
        content = None
        media_url = None
        extracted_media_content = None  # For storing parsed PDF content
        skip_n8n_batch = False  # Flag to skip n8n batching for rejected files
        flags = {}  # Initialize flags for message classification/tagging

        if message_type == "text":
            content = message_data.get("text", {}).get("body", "")
            
            # Check for YouTube link in text (ONLY for USER messages)
            if content and origin == "user":
                yt_match = re.search(YOUTUBE_REGEX, content)
                if yt_match:
                    video_id = yt_match.group(1)
                    logger.info(f"Detected YouTube video {video_id} in text message")
                    try:
                        # Send confirmation message
                        send_whatsapp_message(chat_id, "let me check out the youtube video.")

                        # Construct URL (Supadata handles various formats, but standardizing helps)
                        # or just pass the full content if it's just a URL, but using ID is safer
                        yt_url = f"https://www.youtube.com/watch?v={video_id}"
                        logger.info(f"Fetching transcript for {yt_url}")
                        
                        transcript_obj = supadata_client.transcript(url=yt_url, text=True)
                        if transcript_obj and transcript_obj.content:
                            logger.info(f"Successfully extracted transcript for {video_id} ({len(transcript_obj.content)} chars)")
                            extracted_media_content = transcript_obj.content
                        else:
                            logger.warning(f"No transcript content returned for {video_id}")
                    except Exception as e:
                        logger.error(f"Failed to extract YouTube transcript: {e}")
                        # Don't fail the message, just log it
                
                # Check for generic Website link if NOT YouTube
                else:
                    url_match = re.search(URL_REGEX, content)
                    if url_match:
                        raw_url = url_match.group(0)
                        # Check exclusions
                        if not any(domain in raw_url.lower() for domain in EXCLUDED_DOMAINS):
                            logger.info(f"Detected website URL: {raw_url}")
                            try:
                                # Normalize URL: Ensure https://www. prefix as requested
                                # Strip existing protocol and www
                                clean_url = re.sub(r"^https?://", "", raw_url)
                                clean_url = re.sub(r"^www\.", "", clean_url)
                                target_url = f"https://www.{clean_url}"
                                
                                logger.info(f"Scraping website: {target_url}")
                                scrape_data = supadata_client.web.scrape(url=target_url)
                                
                                if scrape_data and scrape_data.content:
                                    logger.info(f"Successfully scraped website ({len(scrape_data.content)} chars)")
                                    extracted_media_content = scrape_data.content
                                else:
                                    # Send failure message
                                    logger.warning(f"Scraping returned empty content for {target_url}")
                                    send_whatsapp_message(chat_id, "I couldn't read that website.")
                            except Exception as e:
                                logger.error(f"Failed to scrape website: {e}")
                                try:
                                    send_whatsapp_message(chat_id, "I couldn't read that website.")
                                except:
                                    pass

                try:
                    # Persona Learning: Classify and update
                    if origin == "user":
                        classification = classify_message(content)
                        flags["classification"] = classification
                        logger.info(f"Message classified as: {classification}")
                        
                        if classification == "persona":
                            # Fetch current persona
                            current_persona = get_publyc_persona(user_id)
                            if current_persona:
                                # Determine update
                                update = process_persona_update(content, current_persona)
                                if update:
                                    # Execute update
                                    field = update["field"]
                                    value = update["value"]
                                    update_publyc_persona_field(user_id, field, value)
                                    logger.info(f"Updated persona field {field} for user {user_id}")
                                    # Add update info to flags for traceability
                                    flags["persona_update"] = update
                            else:
                                logger.warning(f"No persona found for user {user_id}, skipping update.")
                except Exception as e:
                    logger.error(f"Error in persona learning flow: {e}")

        elif message_type == "link_preview":
            # Link preview messages have content in the link_preview.body field
            link_preview_data = message_data.get("link_preview") or {}
            content = link_preview_data.get("body", "")
            
            # Check for YouTube link in link_preview (or the message text itself if available?)
            # Usually the URL is in 'canonicalUrl' or similar in the metadata, but here we scan body
            if content:
                yt_match = re.search(YOUTUBE_REGEX, content)
                if yt_match:
                    video_id = yt_match.group(1)
                    logger.info(f"Detected YouTube video {video_id} in link_preview")
                    try:
                        # Send confirmation message
                        send_whatsapp_message(chat_id, "let me check out the youtube video.")

                        yt_url = f"https://www.youtube.com/watch?v={video_id}"
                        logger.info(f"Fetching transcript for {yt_url}")
                        
                        transcript_obj = supadata_client.transcript(url=yt_url, text=True)
                        if transcript_obj and transcript_obj.content:
                            logger.info(f"Successfully extracted transcript for {video_id} ({len(transcript_obj.content)} chars)")
                            extracted_media_content = transcript_obj.content
                        else:
                            logger.warning(f"No transcript content returned for {video_id}")
                    except Exception as e:
                        logger.error(f"Failed to extract YouTube transcript: {e}")

                # Check for generic Website link if NOT YouTube
                else:
                    url_match = re.search(URL_REGEX, content)
                    if url_match:
                        raw_url = url_match.group(0)
                        # Check exclusions
                        if not any(domain in raw_url.lower() for domain in EXCLUDED_DOMAINS):
                            logger.info(f"Detected website URL in link_preview: {raw_url}")
                            try:
                                # Normalize URL: Ensure https://www. prefix
                                clean_url = re.sub(r"^https?://", "", raw_url)
                                clean_url = re.sub(r"^www\.", "", clean_url)
                                target_url = f"https://www.{clean_url}"
                                
                                logger.info(f"Scraping website: {target_url}")
                                scrape_data = supadata_client.web.scrape(url=target_url)
                                
                                if scrape_data and scrape_data.content:
                                    logger.info(f"Successfully scraped website ({len(scrape_data.content)} chars)")
                                    extracted_media_content = scrape_data.content
                                else:
                                    # Send failure message
                                    logger.warning(f"Scraping returned empty content for {target_url}")
                                    send_whatsapp_message(chat_id, "I couldn't read that website.")
                            except Exception as e:
                                logger.error(f"Failed to scrape website: {e}")
                                try:
                                    send_whatsapp_message(chat_id, "I couldn't read that website.")
                                except:
                                    pass


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

            # Check file size FIRST (before attempting notifications)
            max_size_bytes = settings.max_file_size_mb * 1024 * 1024
            if message_type in ("image", "video", "document", "audio") and file_size > max_size_bytes:
                # File too large - set flags first
                logger.warning(
                    f"{message_type.title()} too large ({file_size / 1024 / 1024:.2f}MB > "
                    f"{settings.max_file_size_mb}MB) for message {message_id}"
                )
                media_url = None
                media_error = f"FILE_TOO_LARGE::{file_size}::{settings.max_file_size_mb}MB_limit"
                content = f"[{message_type.title()} too large: {file_size / 1024 / 1024:.2f}MB]"
                skip_n8n_batch = True  # Don't send to n8n

            # Send notifications for user messages only
            if origin == "user":
                try:
                    # Check if media is too large (applies to all media types)
                    if file_size > max_size_bytes:
                        # Unified rejection message for all oversized media
                        send_whatsapp_message(
                            chat_id,
                            "We don't support media of this size"
                        )
                    elif message_type == "document":
                        # Document is acceptable size - notify processing
                        send_whatsapp_message(chat_id, "Reading the doc you're sending me")
                        logger.info(f"Sent document processing notification to {chat_id}")
                    elif message_type == "video":
                        # Video acknowledgment
                        send_whatsapp_message(chat_id, "Oh we don't support videos yet.")
                        logger.info(f"Sent video acknowledgment to {chat_id}")
                    elif message_type == "image":
                        # Image acknowledgment
                        send_whatsapp_message(chat_id, "Let me check out that image.")
                        logger.info(f"Sent image acknowledgment to {chat_id}")
                    elif message_type == "audio":
                        # Audio acknowledgment
                        send_whatsapp_message(chat_id, "Let me listen to your voice note.")
                        logger.info(f"Sent audio acknowledgment to {chat_id}")
                except Exception as e:
                    # Don't let notification failures block processing
                    logger.warning(f"Failed to send file notification: {str(e)}")

            # Skip processing if file was too large (already handled in notification block)
            if not media_id:
                logger.warning(f"No media_id found for {message_type} message {message_id}")
                media_url = None
                media_error = f"MISSING_DATA::media_id::{message_type}_message_{message_id}"
            elif message_type in ("image", "video", "document", "audio") and file_size > settings.max_file_size_mb * 1024 * 1024:
                # Already notified user, just skip processing
                logger.info(f"Skipping processing for oversized {message_type} {message_id}")
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

                            # Notify user that parsing failed (only for user messages)
                            if origin == "user":
                                try:
                                    send_whatsapp_message(chat_id, "Couldn't parse the document.")
                                    logger.info(f"Sent PDF parsing failure notification to {chat_id}")
                                except Exception as e:
                                    logger.warning(f"Failed to send PDF parsing failure notification: {str(e)}")
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
            "chat_id": chat_id,
            "media_url": media_url,
            "whapi_message_id": message_id,
            "extracted_media_content": extracted_media_content,  # For PDF parsed content
            "flags": flags,  # Message classification info
        }

        # Insert into database
        insert_message(db_message)

        # Add to n8n batch if this is a user message, not a rejected file, and not a pilot user
        if not from_me and not skip_n8n_batch and not is_pilot:
            logger.info(f"User message detected (from_me={from_me}), adding to n8n batch")
            try:
                from workers.batching import add_message_to_batch
                add_message_to_batch(
                    chat_id=chat_id,
                    content=content or "[No content]",
                    user_id=user_id
                )
            except Exception as e:
                # Don't let batching failures block message processing
                logger.error(f"Failed to add message to n8n batch: {e}")
        elif not from_me and skip_n8n_batch:
            logger.info(f"Skipping n8n batch for rejected file (message {message_id})")
        elif not from_me and is_pilot:
            logger.info(f"Skipping n8n batch for pilot user (message {message_id})")

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
