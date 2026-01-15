
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

def backfill_memory(target_user_id: str, limit: int, dry_run: bool = False):
    logger.info(f"Starting backfill for user: {target_user_id} (Limit: {limit}, Dry Run: {dry_run})")
    
    supabase = get_supabase()
    
    # 1. Fetch last N User messages
    # origin = 'user' is critical
    response = supabase.table("messages") \
        .select("id, content, created_at, origin, type") \
        .eq("user_id", target_user_id) \
        .eq("origin", "user") \
        .in_("type", ["text", "voice"]) \
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

    results_summary = []

    for msg in messages:
        content = msg.get("content")
        msg_id = msg.get("id")
        
        if not content:
            continue
            
        logger.info(f"--- Processing Msg {msg_id} ---")
        logger.info(f"Content: {content[:50]}...")
        
        row_result = {
            "content_snippet": content[:50] + "..." if len(content) > 50 else content,
            "category": "UNKNOWN",
            "action": "NONE",
            "details": ""
        }

        try:
            # Classification
            classification = classify_message(content)
            logger.info(f"Classified as: {classification}")
            row_result["category"] = classification.upper()
            
            if classification == "persona":
                current_persona = get_publyc_persona(target_user_id)
                if current_persona:
                    # For dry run, we use the current persona state but don't save
                    update = process_persona_update(content, current_persona)
                    if update:
                        field = update["field"]
                        value = update["value"]
                        row_result["details"] = f"Field: {field}, Value: {value}"
                        
                        if not dry_run:
                            update_publyc_persona_field(target_user_id, field, value)
                            logger.info(f"✅ Updated PERSONA field: {field}")
                            row_result["action"] = "UPDATED"
                        else:
                            logger.info(f"🚫 [DRY RUN] Would update PERSONA field: {field} -> {value}")
                            row_result["action"] = "WOULD UPDATE"
                    else:
                        logger.info("No update extracted from persona message.")
                        row_result["details"] = "No update extracted"
                        row_result["action"] = "SKIPPED"
                else:
                    logger.warning("User has no persona record.")
                    row_result["details"] = "No persona record"
                    row_result["action"] = "SKIPPED"

            elif classification == "fact":
                summary = summarize_fact(content)
                row_result["details"] = f"Summary: {summary}"
                if not dry_run:
                    embedding = generate_embedding(summary)
                    if embedding:
                        success = store_memory(target_user_id, summary, embedding)
                        if success:
                             logger.info(f"✅ Stored FACT: {summary}")
                             row_result["action"] = "STORED"
                        else:
                             logger.error("Failed to store memory.")
                             row_result["action"] = "FAILED"
                else:
                    logger.info(f"🚫 [DRY RUN] Would store FACT: {summary}")
                    row_result["action"] = "WOULD STORE"
            else:
                logger.info("Ignored (neither).")
                row_result["action"] = "IGNORED"
                
            results_summary.append(row_result)
                
        except Exception as e:
            logger.error(f"Error processing message {msg_id}: {e}")
            row_result["action"] = "ERROR"
            row_result["details"] = str(e)
            results_summary.append(row_result)

    # Print Summary Table
    print("\n" + "="*80)
    print(f"{'CATEGORY':<10} | {'ACTION':<15} | {'CONTENT':<30} | {'DETAILS'}")
    print("-" * 80)
    for res in results_summary:
        print(f"{res['category']:<10} | {res['action']:<15} | {res['content_snippet']:<30} | {res['details']}")
    print("="*80 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill AI memory/persona for a user.")
    parser.add_argument("user_id", help="The UUID of the user to process")
    parser.add_argument("--limit", "-l", type=int, default=20, help="Number of recent messages to process")
    parser.add_argument("--dry-run", action="store_true", help="Run without making changes to DB")
    
    args = parser.parse_args()
    
    backfill_memory(args.user_id, args.limit, args.dry_run)
