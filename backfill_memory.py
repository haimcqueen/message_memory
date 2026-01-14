
import os
import sys
sys.path.append(os.getcwd())
import logging
from workers.database import get_supabase, get_publyc_persona, update_publyc_persona_field, store_memory
from utils.llm import classify_message, process_persona_update, summarize_fact, generate_embedding

import argparse

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backfill_memory(target_user_id: str, limit: int):
    logger.info(f"Starting backfill for user: {target_user_id} (Limit: {limit})")
    
    supabase = get_supabase()
    
    # 1. Fetch last N User messages
    # origin = 'user' is critical
    response = supabase.table("messages") \
        .select("id, content, created_at, origin, type") \
        .eq("user_id", target_user_id) \
        .eq("origin", "user") \
        .in_("type", ["text", "voice", "audio"]) \
        .order("created_at", desc=True) \
        .limit(limit) \
        .execute()
        
    messages = response.data
    
    if not messages:
        logger.info("No messages found for user.")
        return

    # Process oldest first to build persona/memory logically
    messages.reverse()
    
    logger.info(f"Found {len(messages)} messages. Processing...")

    for msg in messages:
        content = msg.get("content")
        msg_id = msg.get("id")
        
        if not content:
            continue
            
        logger.info(f"--- Processing Msg {msg_id} ---")
        logger.info(f"Content: {content[:50]}...")
        
        try:
            # Classification
            classification = classify_message(content)
            logger.info(f"Classified as: {classification}")
            
            if classification == "persona":
                current_persona = get_publyc_persona(target_user_id)
                if current_persona:
                    update = process_persona_update(content, current_persona)
                    if update:
                        field = update["field"]
                        value = update["value"]
                        update_publyc_persona_field(target_user_id, field, value)
                        logger.info(f"✅ Updated PERSONA field: {field}")
                    else:
                        logger.info("No update extracted from persona message.")
                else:
                    logger.warning("User has no persona record.")

            elif classification == "fact":
                summary = summarize_fact(content)
                embedding = generate_embedding(summary)
                if embedding:
                    success = store_memory(target_user_id, summary, embedding)
                    if success:
                         logger.info(f"✅ Stored FACT: {summary}")
                    else:
                         logger.error("Failed to store memory.")
            else:
                logger.info("Ignored (neither).")
                
        except Exception as e:
            logger.error(f"Error processing message {msg_id}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill AI memory/persona for a user.")
    parser.add_argument("user_id", help="The UUID of the user to process")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Number of recent messages to process (default: 20)")
    
    args = parser.parse_args()
    
    backfill_memory(args.user_id, args.limit)
