"""
Fixtures for integration tests.

Provides fixtures for testing with real external APIs (Whapi, OpenAI, Supabase, n8n).
These tests require actual API credentials and should be run separately from unit tests.
"""
import pytest
import os
from typing import Dict, Any


@pytest.fixture
def sample_webhook_reaction() -> Dict[str, Any]:
    """Sample reaction message webhook payload."""
    return {
        "messages": [
            {
                "id": "reaction_msg_123",
                "from": "1234567890",
                "from_me": False,
                "type": "reaction",
                "chat_id": "1234567890@s.whatsapp.net",
                "timestamp": 1700000000,
                "source": "mobile",
                "reaction": {
                    "message_id": "original_msg_123",
                    "text": "👍"
                }
            }
        ],
        "event": {
            "type": "messages",
            "event": "message"
        },
        "channel_id": "channel123"
    }


@pytest.fixture
def sample_webhook_link_preview() -> Dict[str, Any]:
    """Sample link preview message webhook payload."""
    return {
        "messages": [
            {
                "id": "link_msg_123",
                "from": "1234567890",
                "from_me": False,
                "type": "link_preview",
                "chat_id": "1234567890@s.whatsapp.net",
                "timestamp": 1700000000,
                "source": "mobile",
                "link_preview": {
                    "body": "Check out this awesome website: https://example.com",
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "description": "This domain is for use in illustrative examples",
                    "thumbnail": "base64_encoded_thumbnail..."
                }
            }
        ],
        "event": {
            "type": "messages",
            "event": "message"
        },
        "channel_id": "channel123"
    }


@pytest.fixture
def sample_webhook_short_video() -> Dict[str, Any]:
    """Sample short (reels) video message webhook payload."""
    return {
        "messages": [
            {
                "id": "short_msg_123",
                "from": "1234567890",
                "from_me": False,
                "type": "short",
                "chat_id": "1234567890@s.whatsapp.net",
                "timestamp": 1700000000,
                "source": "mobile",
                "short": {
                    "id": "short_vid_123",
                    "mime_type": "video/mp4",
                    "file_size": 5000000,  # 5MB
                    "sha256": "abc123def456",
                    "link": "https://whapi.cloud/media/short_vid_123"
                }
            }
        ],
        "event": {
            "type": "messages",
            "event": "message"
        },
        "channel_id": "channel123"
    }


@pytest.fixture
def sample_media_bytes() -> Dict[str, bytes]:
    """Sample media file bytes for testing uploads."""
    return {
        # Minimal valid PDF (PDF-1.4 header)
        "pdf": b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/Resources <<\n/Font <<\n/F1 4 0 R\n>>\n>>\n/MediaBox [0 0 612 792]\n/Contents 5 0 R\n>>\nendobj\n4 0 obj\n<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>\nendobj\n5 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test PDF) Tj\nET\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000262 00000 n\n0000000341 00000 n\ntrailer\n<<\n/Size 6\n/Root 1 0 R\n>>\nstartxref\n433\n%%EOF",

        # Minimal valid JPEG (1x1 red pixel)
        "jpg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\t\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\x9f\xff\xd9",

        # Minimal valid PNG (1x1 red pixel)
        "png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x9a|\xc8\x05\x00\x00\x00\x00IEND\xaeB`\x82",

        # Minimal valid GIF (1x1 white pixel)
        "gif": b"GIF89a\x01\x00\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;",

        # Minimal valid WebP (1x1 white pixel)
        "webp": b"RIFF$\x00\x00\x00WEBPVP8 \x18\x00\x00\x000\x01\x00\x9d\x01*\x01\x00\x01\x00\x01@%\xa4\x00\x03p\x00\xfe\xfb\x94\x00\x00",

        # Minimal OGG audio file (empty Vorbis stream)
        "ogg": b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00",

        # Minimal MP3 file (ID3 tag only)
        "mp3": b"ID3\x04\x00\x00\x00\x00\x00\x00"
    }


@pytest.fixture
def mock_openai_whisper_response() -> Dict[str, Any]:
    """Mock successful Whisper API response."""
    return {
        "text": "This is a transcribed voice message."
    }


@pytest.fixture
def mock_openai_vision_response() -> Dict[str, Any]:
    """Mock successful Vision API response."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "This image shows a document with the following text: Sample Document Content. The document appears to be a business letter."
                }
            }
        ]
    }


@pytest.fixture
def mock_openai_files_response() -> Dict[str, Any]:
    """Mock successful Files API upload response."""
    return {
        "id": "file-abc123def456",
        "object": "file",
        "bytes": 12345,
        "created_at": 1700000000,
        "filename": "document.pdf",
        "purpose": "assistants"
    }


@pytest.fixture
def mock_http_error_responses() -> Dict[int, Dict[str, Any]]:
    """Mock HTTP error responses for various status codes."""
    return {
        400: {"error": "Bad Request", "message": "Invalid parameters"},
        401: {"error": "Unauthorized", "message": "Invalid API key"},
        403: {"error": "Forbidden", "message": "Access denied"},
        404: {"error": "Not Found", "message": "Resource not found"},
        429: {"error": "Too Many Requests", "message": "Rate limit exceeded", "retry_after": 60},
        500: {"error": "Internal Server Error", "message": "Server error occurred"},
        503: {"error": "Service Unavailable", "message": "Service temporarily unavailable"}
    }


@pytest.fixture
def mock_supabase_insert_response() -> Dict[str, Any]:
    """Mock successful Supabase insert response."""
    return {
        "data": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "user-123",
                "content": "Test message",
                "origin": "user",
                "type": "text",
                "message_sent_at": "2024-01-01T12:00:00+00:00",
                "chat_id": "1234567890@s.whatsapp.net",
                "created_at": "2024-01-01T12:00:00+00:00"
            }
        ],
        "error": None
    }


@pytest.fixture
def mock_supabase_unique_constraint_error() -> Dict[str, Any]:
    """Mock Supabase unique constraint violation error."""
    return {
        "data": None,
        "error": {
            "message": 'duplicate key value violates unique constraint "messages_whapi_message_id_key"',
            "details": "Key (whapi_message_id)=(msg_123) already exists.",
            "hint": None,
            "code": "23505"
        }
    }


@pytest.fixture
def mock_supabase_select_response() -> Dict[str, Any]:
    """Mock successful Supabase select response."""
    return {
        "data": {
            "id": "user-123",
            "phone": "+1234567890",
            "created_at": "2024-01-01T00:00:00+00:00"
        },
        "error": None
    }


@pytest.fixture
def mock_supabase_not_found_response() -> Dict[str, Any]:
    """Mock Supabase not found response (empty result, not an error)."""
    return {
        "data": None,
        "error": None
    }


@pytest.fixture
def mock_supabase_storage_upload_response() -> Dict[str, str]:
    """Mock successful Supabase Storage upload response."""
    return {
        "Key": "voice/1234567890/msg123.ogg",
        "path": "voice/1234567890/msg123.ogg"
    }


@pytest.fixture
def mock_n8n_success_response() -> Dict[str, Any]:
    """Mock successful n8n webhook response."""
    return {
        "status": "success",
        "message": "Batch processed successfully"
    }


@pytest.fixture
def mock_n8n_error_response() -> Dict[str, Any]:
    """Mock n8n webhook error response."""
    return {
        "status": "error",
        "message": "Workflow execution failed",
        "details": "Node 'HTTP Request' failed: Connection timeout"
    }


@pytest.fixture
def integration_test_env_check():
    """
    Check if integration test environment variables are set.
    Skip tests if required credentials are missing.
    """
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "OPENAI_API_KEY",
        "WHAPI_API_URL",
        "WHAPI_TOKEN",
        "N8N_WEBHOOK_URL",
        "N8N_BEARER_TOKEN"
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        pytest.skip(
            f"Integration tests require environment variables: {', '.join(missing_vars)}. "
            "Set these in .env file or environment to run integration tests."
        )


@pytest.fixture
def whapi_api_base_url() -> str:
    """Get Whapi API base URL from environment."""
    return os.getenv("WHAPI_API_URL", "https://gate.whapi.cloud")


@pytest.fixture
def whapi_auth_header() -> Dict[str, str]:
    """Get Whapi authentication header."""
    token = os.getenv("WHAPI_TOKEN", "")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def openai_api_key() -> str:
    """Get OpenAI API key from environment."""
    return os.getenv("OPENAI_API_KEY", "")


@pytest.fixture
def supabase_url() -> str:
    """Get Supabase URL from environment."""
    return os.getenv("SUPABASE_URL", "")


@pytest.fixture
def supabase_service_role_key() -> str:
    """Get Supabase service role key from environment."""
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


@pytest.fixture
def n8n_webhook_url() -> str:
    """Get n8n webhook URL from environment."""
    return os.getenv("N8N_WEBHOOK_URL", "")


@pytest.fixture
def n8n_auth_header() -> Dict[str, str]:
    """Get n8n authentication header."""
    token = os.getenv("N8N_BEARER_TOKEN", "")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_chat_id() -> str:
    """Get test chat ID for integration tests."""
    return os.getenv("TEST_CHAT_ID", "1234567890@s.whatsapp.net")


@pytest.fixture
def test_phone_number() -> str:
    """Get test phone number for integration tests."""
    return os.getenv("TEST_PHONE_NUMBER", "+1234567890")
