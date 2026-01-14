
import pytest
from unittest.mock import patch, MagicMock
from workers.jobs import process_whatsapp_message, YOUTUBE_REGEX
import re

# Mock Settings
@pytest.fixture
def mock_settings():
    with patch("workers.jobs.settings") as mock:
        mock.max_file_size_mb = 10
        yield mock

# Mock Supadata
@pytest.fixture
def mock_supadata():
    with patch("workers.jobs.supadata_client") as mock:
        yield mock

# Mock DB functions to avoid side effects
@pytest.fixture
def mock_db_functions():
    with patch("workers.jobs.get_subscription_status_by_phone") as mock_sub, \
         patch("workers.jobs.get_user_id_by_phone") as mock_user, \
         patch("workers.jobs.insert_message") as mock_insert, \
         patch("workers.jobs.send_presence") as mock_presence, \
         patch("workers.database.update_message_content") as mock_update, \
         patch("workers.jobs.send_whatsapp_message") as mock_whatsapp:
        
        mock_sub.return_value = "active"
        mock_user.return_value = "user-123"
        yield {
            "sub": mock_sub,
            "user": mock_user,
            "insert": mock_insert,
            "update": mock_update,
            "presence": mock_presence,
            "whatsapp": mock_whatsapp
        }

def test_regex_matching():
    """Test YouTube URL regex."""
    assert re.search(YOUTUBE_REGEX, "https://www.youtube.com/watch?v=dQw4w9WgXcQ").group(1) == "dQw4w9WgXcQ"
    assert re.search(YOUTUBE_REGEX, "https://youtu.be/dQw4w9WgXcQ").group(1) == "dQw4w9WgXcQ"
    assert re.search(YOUTUBE_REGEX, "Check this: https://www.youtube.com/shorts/abc-123_DEF").group(1) == "abc-123_DEF"
    assert re.search(YOUTUBE_REGEX, "No link here") is None

def test_youtube_extraction_text(mock_db_functions, mock_supadata, mock_settings):
    """Test transcript extraction from text message."""
    
    # Mock successful transcript
    mock_transcript = MagicMock()
    mock_transcript.content = "This is a transcript."
    mock_supadata.transcript.return_value = mock_transcript
    
    message_data = {
        "id": "msg-1",
        "type": "text",
        "chat_id": "123456@s.whatsapp.net",
        "from_me": False,
        "timestamp": 1234567890,
        "text": {"body": "Check this video https://youtu.be/dQw4w9WgXcQ"},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Verify confirmation message sent
    mock_db_functions["whatsapp"].assert_any_call("123456@s.whatsapp.net", "let me check out the youtube video.")
    
    # Verify Supadata called
    mock_supadata.transcript.assert_called_with(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", text=True)
    
    # Verify DB insertion includes extracted content
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["extracted_media_content"] is None

    # Verify usage of update_message_content
    assert mock_db_functions["update"].called
    # args: id, content, media_url, extracted, flags
    update_args = mock_db_functions["update"].call_args[0]
    assert update_args[3] == "This is a transcript."

def test_youtube_extraction_link_preview(mock_db_functions, mock_supadata, mock_settings):
    """Test transcript extraction from link_preview message."""
    
    # Mock successful transcript
    mock_transcript = MagicMock()
    mock_transcript.content = "Preview transcript."
    mock_supadata.transcript.return_value = mock_transcript
    
    message_data = {
        "id": "msg-2",
        "type": "link_preview",
        "chat_id": "123456@s.whatsapp.net",
        "from_me": False,
        "timestamp": 1234567890,
        "link_preview": {"body": "https://www.youtube.com/watch?v=xyz123abc45"},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Verify confirmation message sent
    mock_db_functions["whatsapp"].assert_any_call("123456@s.whatsapp.net", "let me check out the youtube video.")
    
    # Verify Supadata called
    mock_supadata.transcript.assert_called_with(url="https://www.youtube.com/watch?v=xyz123abc45", text=True)
    
    # Verify DB insertion in place
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["extracted_media_content"] is None

    # Verify usage of update_message_content
    assert mock_db_functions["update"].called
    update_args = mock_db_functions["update"].call_args[0]
    assert update_args[3] == "Preview transcript."

def test_youtube_no_transcript_found(mock_db_functions, mock_supadata, mock_settings):
    """Test handling when no transcript is found."""
    
    # Mock empty transcript
    mock_supadata.transcript.return_value = None
    
    message_data = {
        "id": "msg-3",
        "type": "text",
        "chat_id": "123456@s.whatsapp.net",
        "from_me": False,
        "timestamp": 1234567890,
        "text": {"body": "https://youtu.be/silentvideo"},
        "from": "123456"
    }

    process_whatsapp_message(message_data)

    # Confirmation still sent
    mock_db_functions["whatsapp"].assert_any_call("123456@s.whatsapp.net", "let me check out the youtube video.")
    
    # DB insertion should have None for extracted content
    args, _ = mock_db_functions["insert"].call_args
    assert args[0]["extracted_media_content"] is None

