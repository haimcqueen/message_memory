import logging
import json
from typing import Optional, Dict, Any
from openai import OpenAI
from utils.config import settings
from prompts.persona_learning import CLASSIFY_MESSAGE_SYSTEM_PROMPT, PERSONA_UPDATE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=settings.openai_api_key)

MODEL_NAME = "gpt-5-nano-2025-08-07"

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
            temperature=0,
            max_tokens=10
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
            temperature=0.3
        )
        content = response.choices[0].message.content
        if not content:
            return None
            
        data = json.loads(content)
        field = data.get("field")
        value = data.get("value")
        
        if field in fields_list and value:
            return {"field": field, "value": value}
        return None
        
    except Exception as e:
        logger.error(f"Error acting on persona update: {e}")
        return None
