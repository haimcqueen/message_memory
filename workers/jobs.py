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
    update_publyc_persona_field,
    store_memory
)
from workers.transcription import transcribe_voice_message
from workers.media import process_media_message
from workers.presence import send_presence
from utils.whapi_messaging import send_whatsapp_message
from utils.config import settings
from supadata import Supadata
from utils.llm import classify_message, process_persona_update, summarize_fact, generate_embedding
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
    2. Stores message in Supabase matches as "Pending" (CRITICAL SAFETY STEP)
    3. Processes based on message type (text, voice, scraping)
    4. Updates message content in Supabase
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
        if from_me:
            customer_phone = chat_id.split("@")[0]
            logger.info(f"Agent message - looking up receiver: {customer_phone}")
        else:
            customer_phone = message_data.get("from")
            logger.info(f"User message - looking up sender: {customer_phone}")

        user_id = get_user_id_by_phone(customer_phone)

        # Reject messages from unknown phone numbers (not in users table)
        if user_id is None and not from_me:
            logger.warning(f"Rejecting message from unknown phone number: {customer_phone}")
            try:
                send_whatsapp_message(
                    chat_id,
                    "Unfortunately this number is not known to us - please contact the publyc team or sign up for the waitlist at https://www.publyc.app/"
                )
            except Exception as e:
                logger.error(f"Failed to send rejection message: {e}")
            return

        # Skip database insertion for agent messages to unknown users
        if user_id is None and from_me:
            logger.info(f"Skipping database insertion for agent message to unknown user: {customer_phone}")
            return

        # Get subscription status early
        phone_from_chat = chat_id.split("@")[0]
        subscription_status = None
        try:
            subscription_status = get_subscription_status_by_phone(phone_from_chat)
        except Exception:
            pass # already logged in func

        is_pilot = subscription_status == "pilot"

        # Send typing presence for user messages (skip for pilot users)
        if origin == "user" and not is_pilot:
            try:
                send_presence(chat_id, presence="typing")
            except Exception as e:
                logger.warning(f"Failed to send typing presence: {str(e)}")

        # --- PREPARE & INSERT MESSAGE IMMEDIATELY (SAFEGUARD) ---
        message_sent_at = datetime.fromtimestamp(timestamp).isoformat()
        message_db_id = str(uuid.uuid4())
        
        # Initial content/flags
        initial_content = None
        
        # Extract basic text body if available (for text/link_preview)
        # For media, use caption or pending placeholder
        raw_text_body = (message_data.get("text") or {}).get("body", "")
        
        if message_type == "text":
            initial_content = raw_text_body
        elif message_type == "link_preview":
             # link_preview body is usually the description/content
             initial_content = (message_data.get("link_preview") or {}).get("body", "")
        elif message_type in ["voice", "audio"]:
            initial_content = f"[Transcribing {message_type} ({message_id})...]"
        elif message_type in ["image", "video", "document"]:
             caption = (message_data.get(message_type) or {}).get("caption", "")
             if not caption and message_type == "short":
                 caption = (message_data.get("short") or {}).get("caption", "")
             
             initial_content = caption if caption else f"[{message_type.title()} message pending processing...]"
        else:
            initial_content = f"[{message_type} message]"

        db_message = {
            "id": message_db_id,
            "user_id": user_id,
            "content": initial_content, # Will be updated later if changed
            "origin": origin,
            "type": message_type,
            "message_sent_at": message_sent_at,
            "chat_id": chat_id,
            "media_url": None, # Will be updated
            "whapi_message_id": message_id,
            "extracted_media_content": None,
            "flags": {},
        }

        # CRITICAL: Insert NOW so we never lose it
        insert_message(db_message)


        # --- PROCESS CONTENT & MEDIA ---
        
        final_content = initial_content
        media_url = None
        extracted_media_content = None
        flags = {}
        skip_n8n_batch = False
        media_error = None
        pdf_parsing_error = None
        transcription_error = None

        # TEXT Processing (YouTube/Web Scraping)
        if message_type == "text":
            content = raw_text_body
            if content and origin == "user":
                yt_match = re.search(YOUTUBE_REGEX, content)
                url_match = re.search(URL_REGEX, content)
                
                if yt_match:
                    video_id = yt_match.group(1)
                    logger.info(f"Detected YouTube video {video_id}")
                    try:
                        send_whatsapp_message(chat_id, "let me check out the youtube video.")
                        yt_url = f"https://www.youtube.com/watch?v={video_id}"
                        transcript_obj = supadata_client.transcript(url=yt_url, text=True)
                        if transcript_obj and transcript_obj.content:
                            extracted_media_content = transcript_obj.content
                            logger.info(f"Extracted YT transcript ({len(extracted_media_content)} chars)")
                    except Exception as e:
                        logger.error(f"Failed to extract YouTube transcript: {e}")

                elif url_match:
                     raw_url = url_match.group(0)
                     if not any(domain in raw_url.lower() for domain in EXCLUDED_DOMAINS):
                        logger.info(f"Detected website URL: {raw_url}")
                        try:
                            clean_url = re.sub(r"^https?://", "", raw_url)
                            clean_url = re.sub(r"^www\.", "", clean_url)
                            target_url = f"https://www.{clean_url}"
                            scrape_data = supadata_client.web.scrape(url=target_url)
                            if scrape_data and scrape_data.content:
                                extracted_media_content = scrape_data.content
                                logger.info(f"Scraped website ({len(extracted_media_content)} chars)")
                            else:
                                send_whatsapp_message(chat_id, "I couldn't read that website.")
                        except Exception as e:
                            logger.error(f"Failed to scrape website: {e}")
                            try:
                                send_whatsapp_message(chat_id, "I couldn't read that website.")
                            except:
                                pass
            final_content = content
        
        # LINK PREVIEW Processing
        elif message_type == "link_preview":
             # Same logic as text mostly, but already extracted
             # Simplified: just keep content as is unless we want to scrape inside link_preview too?
             # Original code had copy-paste scraping logic here. Let's keep it minimal for now or replicate if needed.
             # Replicating original logic concisely:
             content = initial_content
             if content:
                yt_match = re.search(YOUTUBE_REGEX, content)
                url_match = re.search(URL_REGEX, content)
                if yt_match:
                     # YouTube logic...
                     video_id = yt_match.group(1)
                     try:
                        send_whatsapp_message(chat_id, "let me check out the youtube video.")
                        transcript_obj = supadata_client.transcript(url=f"https://www.youtube.com/watch?v={video_id}", text=True)
                        if transcript_obj and transcript_obj.content:
                            extracted_media_content = transcript_obj.content
                     except Exception as e:
                        logger.error(f"LinkPreview YT Error: {e}")
                elif url_match:
                     # Website logic...
                     raw_url = url_match.group(0)
                     if not any(d in raw_url.lower() for d in EXCLUDED_DOMAINS):
                        try:
                            clean_url = re.sub(r"^https?://", "", raw_url).replace("www.", "")
                            scrape_data = supadata_client.web.scrape(url=f"https://www.{clean_url}")
                            if scrape_data and scrape_data.content:
                                extracted_media_content = scrape_data.content
                            else:
                                send_whatsapp_message(chat_id, "I couldn't read that website.")
                        except Exception as e:
                             pass
             final_content = content

        # VOICE Processing
        elif message_type == "voice":
            voice_data = message_data.get("voice") or {}
            voice_url = voice_data.get("link")
            
            if not voice_url:
                final_content = "[Voice message - no URL available]"
                transcription_error = "MISSING_DATA::voice_url"
            else:
                try:
                    logger.info(f"Transcribing voice message from {voice_url}")
                    result = transcribe_voice_message(voice_url, chat_id, message_id)
                    final_content = result["transcription"]
                    media_url = result["storage_url"]
                    logger.info("Voice transcription success")
                except Exception as e:
                    logger.error(f"Voice transcription failed: {e}")
                    final_content = "[Voice message - transcription failed]"
                    transcription_error = f"TRANSCRIPTION::{type(e).__name__}::{str(e)}"

        # MEDIA Processing (Image, Video, Document, Audio)
        elif message_type in ["image", "video", "document", "audio"]:
            # Logic for media download/upload
            media_data = message_data.get(message_type)
            # Check both the message_type field and "short" for videos
            media_data = None
            if message_data.get("type") == "short" and message_data.get("short"):
                media_data = message_data.get("short")
            elif message_data.get(message_type):
                media_data = message_data.get(message_type)
            
            # If media_data is None or empty dict, default to empty dict
            if not media_data:
                media_data = {}
            
            media_id = media_data.get("id")
            mime_type = media_data.get("mime_type")
            file_size = media_data.get("file_size", 0)
            
            # Use caption as content
            final_content = media_data.get("caption", "") or f"[{message_type.title()} message]"
            
            # Size check
            max_size_bytes = settings.max_file_size_mb * 1024 * 1024
            if file_size > max_size_bytes:
                 logger.warning(f"File too large: {file_size}")
                 final_content = f"[{message_type.title()} too large: {file_size / 1024 / 1024:.2f}MB]"
                 media_error = "FILE_TOO_LARGE"
                 skip_n8n_batch = True
                 if origin == "user":
                     try:
                        send_whatsapp_message(chat_id, "We don't support media of this size")
                     except: pass
            elif not media_id:
                 media_error = "MISSING_DATA::media_id"
            else:
                 # Ack messages
                 if origin == "user":
                     try:
                        if message_type == "document": send_whatsapp_message(chat_id, "Reading the doc you're sending me")
                        elif message_type == "video": send_whatsapp_message(chat_id, "Oh we don't support videos yet.")
                        elif message_type == "image": send_whatsapp_message(chat_id, "Let me check out that image.")
                        elif message_type == "audio": send_whatsapp_message(chat_id, "Let me listen to your voice note.")
                     except: pass
                 
                 # Process Media
                 try:
                    m_url, parsed_pdf = process_media_message(media_id, message_type, chat_id, message_id, mime_type)
                    media_url = m_url
                    if parsed_pdf:
                        extracted_media_content = parsed_pdf
                    elif mime_type == "application/pdf" and not parsed_pdf:
                        pdf_parsing_error = "PDF_PARSING_FAILED"
                        if origin == "user": send_whatsapp_message(chat_id, "Couldn't parse the document.")
                 except Exception as e:
                    logger.error(f"Media processing failed: {e}")
                    media_error = f"MEDIA_PROCESSING::{type(e).__name__}"

        else:
             final_content = f"Unsupported message type: {message_type}"




        
        # --- PERSONA & MEMORY LEARNING (Post-Processing) ---
        if origin == "user":
            try:
                # Use final_content for classification
                classification = classify_message(final_content)
                flags["classification"] = classification
                
                if classification == "persona":
                    current_persona = get_publyc_persona(user_id)
                    if current_persona:
                        update = process_persona_update(final_content, current_persona)
                        if update:
                            update_publyc_persona_field(user_id, update["field"], update["value"])
                            flags["persona_update"] = update
                
                elif classification == "fact":
                     summary = summarize_fact(final_content)
                     embedding = generate_embedding(summary)
                     if embedding:
                         store_memory(user_id, summary, embedding)
                         flags["fact_memory"] = "stored"
                         
                # Check for YouTube transcript summarization logic from original code?
                # Original code didn't seem to do anything specific with YT transcripts in persona flow 
                # other than logging and storing in 'extracted_media_content'.
                
                # Update flags in DB (since we are using flags dict locally)
                # We need to update flags column? creating update_message_flags?
                # Actually, duplicate insertion check handled update? No.
                # Ideally we should update flags too.
                # For now, let's leave flags update out or add to update_message_content if critical. 
                # (You requested "insert first", flags are generated late).
                # Simpler: The original code inserted flags at the end. 
                # We can update flags in DB if we want, but currently update_message_content only supports content/media.
                # Let's trust that flags are less critical, or add flags to update_message_content signature in next step if needed.

            except Exception as e:
                logger.error(f"Persona flow error: {e}")


        # --- UPDATE DATABASE WITH RESULTS ---
        # Update content, media_url, extracted content, and flags
        if final_content != initial_content or media_url or extracted_media_content or flags:
             from workers.database import update_message_content
             update_message_content(message_db_id, final_content, media_url, extracted_media_content, flags)


        # --- N8N HANDOFF ---
        if not from_me and not skip_n8n_batch and not is_pilot:
            try:
                from workers.batching import add_message_to_batch
                add_message_to_batch(chat_id, final_content or "[No content]", user_id)
            except Exception as e:
                logger.error(f"N8N batch error: {e}")


        # --- ERROR JOB CREATION ---
        # If media failed
        if message_type in ["voice", "image", "video", "document", "audio"] and not media_url:
             error_msg = transcription_error or media_error or pdf_parsing_error or "Unknown media failure"
             from workers.database import create_processing_job
             create_processing_job(message_db_id, message_data, error_msg)

        logger.info(f"Successfully processed message {message_id}")

    except Exception as e:
        logger.error(f"Failed to process message: {str(e)}", exc_info=True)
        raise


