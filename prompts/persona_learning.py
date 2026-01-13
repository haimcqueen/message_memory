"""Prompts for Persona Learning feature."""

CLASSIFY_MESSAGE_SYSTEM_PROMPT = """You are a classifier. Classify the user's message into exactly one of these categories:
- 'persona': Information about the user's identity, business, goals, story, target audience, beliefs, or style.
- 'fact': Specific factual statements about events or things, but not core identity/business info.
- 'neither': Conversational, chit-chat, questions, or unclear.

Return ONLY the category name."""

PERSONA_UPDATE_SYSTEM_PROMPT = """You are a profile manager. The user has sent: '{text}'.
Current profile data: {current_persona_json}

Your task:
1. Identify which SINGLE field from the list below this new info belongs to.
   Fields: {fields_list}
2. Integrate the new info into the EXISTING value of that field (summarize or append logically). Do NOT replace the whole field unless the new info completely supersedes it. Keep it concise.
3. Return a JSON object: {{"field": "field_name", "value": "updated_full_text_for_that_field"}}
4. If the info doesn't fit well or is trivial, return empty JSON {{}}.
"""
