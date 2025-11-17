"""Session detection prompt for OpenAI API."""

SESSION_DETECTION_SYSTEM_PROMPT = "You are a conversation analysis assistant. Answer only with 'yes' or 'no'."


def get_session_detection_prompt(recent_messages: list[dict], new_message_content: str) -> str:
    """
    Generate the session detection prompt.

    Args:
        recent_messages: List of recent messages from the current session
        new_message_content: Content of the new message

    Returns:
        Formatted prompt string
    """
    # Format recent messages for the prompt (reverse to show chronological order)
    conversation_context = "\n".join([
        f"- [{msg['origin']}]: {msg['content'][:100]}"
        for msg in reversed(recent_messages)  # Show oldest to newest
    ])

    return f"""You are analyzing a WhatsApp conversation to determine if a new message continues the same conversation topic or starts a new one.

Previous messages in this chat:
{conversation_context}

New message:
- {new_message_content[:100]}

Question: Does this new message continue the same conversation topic as the previous messages?

Answer with ONLY "yes" or "no"."""


def get_session_detection_messages(recent_messages: list[dict], new_message_content: str) -> list[dict]:
    """
    Get the messages list for session detection with OpenAI.

    Args:
        recent_messages: List of recent messages from the current session
        new_message_content: Content of the new message

    Returns:
        List of message dictionaries for OpenAI API
    """
    prompt = get_session_detection_prompt(recent_messages, new_message_content)

    return [
        {
            "role": "system",
            "content": SESSION_DETECTION_SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
