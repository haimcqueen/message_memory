"""PDF parsing prompt for OpenAI API."""

PDF_PARSING_SYSTEM_PROMPT = "You are a document processing assistant. Extract content directly without any introductory or concluding remarks."

PDF_PARSING_USER_PROMPT = """Extract all text from this PDF document. For each page, describe any visual elements like graphs, charts, diagrams, or images that you see, then provide the text content. Preserve structure and formatting.

Return the extracted content in the following format:
<document>
Add your extracted content here, maintaining the structure and formatting of the original PDF.
</document>

IMPORTANT: Return ONLY the extracted content. Do not include any introductory phrases like "Sure! Here's the extraction..." or concluding remarks like "If you need further details...". Start directly with the content from the first page."""


def get_pdf_parsing_messages(filename: str, base64_string: str) -> list[dict]:
    """
    Get the messages list for PDF parsing with OpenAI.

    Note: Uses input_pdf type for gpt-4o PDF processing via Chat Completions API.

    Args:
        filename: Name of the PDF file
        base64_string: Base64 encoded PDF content

    Returns:
        List of message dictionaries for OpenAI API
    """
    return [{
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": PDF_PARSING_USER_PROMPT
            },
            {
                "type": "input_pdf",
                "input_pdf": {
                    "data": base64_string
                }
            }
        ]
    }]
