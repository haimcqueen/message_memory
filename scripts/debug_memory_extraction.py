import sys
import os
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.getcwd())

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from utils.llm import classify_message, summarize_fact, generate_embedding
    
    test_messages = [
        "I just ran a marathon in 3 hours",
        "My goal is to reach 10k MRR by end of year",
        "I like cats",
        "Hello there",
        "joo my writing style is all small caps"
    ]
    
    print("\n--- Testing LLM Functions ---\n")
    
    for msg in test_messages:
        print(f"Input: '{msg}'")
        
        # Test Classification
        classification = classify_message(msg)
        print(f"Classification: {classification}")
        
        # Test Fact Summarization (if fact)
        if classification == "fact":
            summary = summarize_fact(msg)
            print(f"Fact Summary: '{summary}' (Is original? {summary == msg})")
            
            # Test Embedding
            embedding = generate_embedding(summary)
            print(f"Embedding length: {len(embedding)}")
            
        elif classification == "persona":
            from utils.llm import process_persona_update
            # Mock current persona with empty fields
            current_persona = {
                "business_goals": "Reach 1k MRR",
                "voice_style": {"tone": "casual"},
                "who_you_serve": "Developers"
            }
            update = process_persona_update(msg, current_persona)
            print(f"Persona Update: {update}")
            
        print("-" * 30)

except Exception as e:
    logger.error(f"Debug script failed: {e}", exc_info=True)
