"""Shared pytest fixtures for all tests."""
import pytest
from unittest.mock import Mock, MagicMock


@pytest.fixture
def mock_redis():
    """Mock Redis connection."""
    redis_mock = Mock()
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.exists.return_value = False
    redis_mock.incr.return_value = 1
    redis_mock.delete.return_value = 1
    return redis_mock


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    supabase_mock = Mock()

    # Mock table operations
    table_mock = Mock()
    table_mock.insert.return_value.execute.return_value = Mock(data=[{"id": "test-id"}])
    table_mock.select.return_value.execute.return_value = Mock(data=[])
    table_mock.update.return_value.execute.return_value = Mock(data=[])

    supabase_mock.table.return_value = table_mock

    # Mock storage operations
    storage_mock = Mock()
    storage_mock.upload.return_value = {"path": "test-path"}
    supabase_mock.storage.from_.return_value = storage_mock

    return supabase_mock


@pytest.fixture
def mock_openai():
    """Mock OpenAI client."""
    openai_mock = Mock()

    # Mock chat completions
    chat_mock = Mock()
    chat_mock.create.return_value = Mock(
        choices=[Mock(message=Mock(content="Test response"))]
    )
    openai_mock.chat.completions = chat_mock

    # Mock Whisper transcriptions
    audio_mock = Mock()
    audio_mock.transcriptions.create.return_value = Mock(text="Test transcription")
    openai_mock.audio = audio_mock

    return openai_mock


@pytest.fixture
def mock_whapi_response():
    """Mock successful Whapi API response."""
    response_mock = Mock()
    response_mock.status_code = 200
    response_mock.json.return_value = {"success": True}
    response_mock.raise_for_status.return_value = None
    return response_mock


@pytest.fixture
def sample_webhook_text():
    """Sample text message webhook data."""
    return {
        "id": "test-msg-001",
        "type": "text",
        "chat_id": "1234567890@s.whatsapp.net",
        "from_me": False,
        "from": "1234567890",
        "timestamp": 1700000000,
        "text": {"body": "Hello, this is a test message"}
    }


@pytest.fixture
def sample_webhook_document():
    """Sample document message webhook data."""
    return {
        "id": "test-msg-doc-001",
        "type": "document",
        "chat_id": "1234567890@s.whatsapp.net",
        "from_me": False,
        "from": "1234567890",
        "timestamp": 1700000000,
        "document": {
            "id": "media-doc-001",
            "mime_type": "application/pdf",
            "caption": "Test document",
            "file_size": 10 * 1024 * 1024  # 10MB
        }
    }


@pytest.fixture
def sample_webhook_oversized_document():
    """Sample oversized document webhook data (>50MB)."""
    return {
        "id": "test-msg-doc-large-001",
        "type": "document",
        "chat_id": "1234567890@s.whatsapp.net",
        "from_me": False,
        "from": "1234567890",
        "timestamp": 1700000000,
        "document": {
            "id": "media-doc-large-001",
            "mime_type": "application/pdf",
            "caption": "Large document",
            "file_size": 100 * 1024 * 1024  # 100MB
        }
    }


@pytest.fixture
def sample_webhook_video():
    """Sample video message webhook data."""
    return {
        "id": "test-msg-video-001",
        "type": "video",
        "chat_id": "1234567890@s.whatsapp.net",
        "from_me": False,
        "from": "1234567890",
        "timestamp": 1700000000,
        "video": {
            "id": "media-video-001",
            "mime_type": "video/mp4",
            "caption": "Test video",
            "file_size": 5 * 1024 * 1024  # 5MB
        }
    }


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    settings_mock = Mock()
    settings_mock.max_file_size_mb = 50
    settings_mock.supabase_url = "https://test.supabase.co"
    settings_mock.supabase_key = "test-key"
    settings_mock.whapi_token = "test-token"
    settings_mock.whapi_api_url = "https://test.whapi.cloud"
    settings_mock.openai_api_key = "test-openai-key"
    settings_mock.redis_url = "redis://localhost:6379"
    settings_mock.n8n_webhook_url = "https://test.n8n.cloud/webhook"
    settings_mock.n8n_webhook_api_key = "test-n8n-key"
    settings_mock.n8n_batch_delay_seconds = 60
    settings_mock.presence_typing_min_seconds = 13
    settings_mock.presence_typing_max_seconds = 18
    return settings_mock
