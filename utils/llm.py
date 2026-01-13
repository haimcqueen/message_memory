import logging
import json
from typing import Optional, Dict, Any
from openai import OpenAI
from utils.config import settings
from prompts.persona_learning import CLASSIFY_MESSAGE_SYSTEM_PROMPT, PERSONA_UPDATE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.openai_api_key)

MODEL_NAME = "gpt-5-mini-2025-08-07"

def classify_message(text: str) -> str:
    """
    Classify a message as 'fact', 'persona', or 'neither'.
    
    Args:
        text: The user message text.
        
    Returns:
        One of: "fact", "persona", "neither".
    """
    try:
        response = openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system", 
                    "content": CLASSIFY_MESSAGE_SYSTEM_PROMPT
                },
                {"role": "user", "content": text}
            ],
            # temperature=0,  # Not supported by gpt-5-nano
            max_completion_tokens=256
        )
        result = response.choices[0].message.content.strip().lower()
        if result not in ["fact", "persona", "neither"]:
            return "neither"
        return result
    except Exception as e:
        logger.error(f"Error classifying message: {e}")
        return "neither"

def process_persona_update(text: str, current_persona: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Determine which field to update and the new content.
    
    Args:
        text: The new user message containing persona info.
        current_persona: The current persona data from DB.
        
    Returns:
        A dictionary {"field": "field_name", "value": "new_value"} or None if no update needed.
        Fields are: who_you_serve, value_proposition, your_story, content_pillars, 
        beliefs_positioning, voice_style, business_goals, proof_authority, boundaries.
    """
    fields_list = [
        "who_you_serve", "value_proposition", "your_story", "content_pillars",
        "beliefs_positioning", "voice_style", "business_goals", "proof_authority", "boundaries"
    ]
    
    # Format the prompt with dynamic data
    system_prompt = PERSONA_UPDATE_SYSTEM_PROMPT.format(
        text=text,
        current_persona_json=json.dumps(current_persona, default=str),
        fields_list=", ".join(fields_list)
    )

    try:
        response = openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt}
            ],
            response_format={"type": "json_object"},
            # temperature=0.3  # Not supported by gpt-5-nano
        )
        content = response.choices[0].message.content
        if not content:
            return None
            
        data = json.loads(content)
        field = data.get("field")
        value = data.get("value")
        
        if field in fields_list and value:
            # Try to parse value if it's a JSON string (for nested fields like boundaries)
            if isinstance(value, str):
                try:
                    parsed_value = json.loads(value)
                    # If it parses to a dict/list, use that instead
                    if isinstance(parsed_value, (dict, list)):
                        value = parsed_value
                except json.JSONDecodeError:
                    pass
            
            return {"field": field, "value": value}
        return None
        
        return None
        
    except Exception as e:
        logger.error(f"Error acting on persona update: {e}")
        return None

def generate_embedding(text: str) -> list[float]:
    """
    Generate a vector embedding for the given text.
    Uses text-embedding-3-small (1536 dims).
    """
    try:
        response = openai_client.embeddings.create(
            input=text,
            model="text-embedding-3-large", # Upgraded to Large model
            dimensions=1536 # Clamped to 1536 to match DB schema
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return []

def summarize_fact(text: str) -> str:
    """
    Summarize a user message into a concise factual statement.
    Example: "I ran a marathon btw" -> "User ran a marathon"
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-5-mini-2025-08-07", # Use user-requested cheaper model
            messages=[
                {
                    "role": "system", 
                    "content": "Extract the core factual claim from the user's message. Return ONLY the fact as a concise 3rd person statement. Example: 'I ran a marathon' -> 'User ran a marathon'. If the message is unclear or you cannot extract a fact, return the original message exactly."
                },
                {"role": "user", "content": text}
            ],
            max_completion_tokens=50
        )
        content = response.choices[0].message.content.strip()
        return content if content else text # Fallback if empty
    except Exception as e:
        logger.error(f"Error summarizing fact: {e}")
        return text  # Fallback to original text
