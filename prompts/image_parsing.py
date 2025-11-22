"""Image parsing prompt for OpenAI Vision API."""

IMAGE_PARSING_SYSTEM_PROMPT = "You are an image analysis assistant. Extract and describe content directly without any introductory or concluding remarks."

IMAGE_PARSING_USER_PROMPT = """Analyze this image and provide a comprehensive description. Include:
- Any text visible in the image (transcribe it exactly)
- Objects, people, or scenes present
- Colors, composition, and visual elements
- Context or setting
- Any other relevant details
- the most important information should be texts, numbers, charts found in the image

Return the extracted content in the following format:
<image>
Add your detailed description here, including any text found in the image and visual elements.
</image>

IMPORTANT: Return ONLY the extracted content. Do not include any introductory phrases like "Sure! Here's the analysis..." or concluding remarks like "If you need further details...". Start directly with the content."""


def get_image_parsing_messages(base64_image: str) -> list[dict]:
    """
    Get the messages list for image parsing with OpenAI Vision API.

    Args:
        base64_image: Base64 encoded image content

    Returns:
        List of message dictionaries for OpenAI API
    """
    return [{
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": IMAGE_PARSING_USER_PROMPT
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            }
        ]
    }]
