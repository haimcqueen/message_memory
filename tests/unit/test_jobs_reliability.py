
import pytest
from unittest.mock import patch, MagicMock
from workers.jobs import process_whatsapp_message

# Reuse basic mocks
@pytest.fixture
def mock_db_basic():
    with patch("workers.jobs.get_subscription_status_by_phone") as mock_sub, \
         patch("workers.jobs.get_user_id_by_phone") as mock_user, \
         patch("workers.jobs.insert_message") as mock_insert, \
         patch("workers.jobs.send_presence") as mock_presence, \
         patch("workers.database.update_message_content") as mock_update_msg, \
         patch("workers.jobs.send_whatsapp_message") as mock_whatsapp, \
         patch("workers.jobs.classify_message") as mock_classify:
        
        mock_sub.return_value = "active"
        mock_user.return_value = "user-123"
        mock_classify.return_value = "neithere" 
        
        yield {
            "sub": mock_sub,
            "user": mock_user,
            "insert": mock_insert,
            "update_msg": mock_update_msg
        }

def test_process_message_with_null_text_field(mock_db_basic):
    """
    Test that process_whatsapp_message handles 'text': None gracefully.
    This was the cause of a production AttributeError.
    """
    message_data = {
        "id": "msg-link-preview-null-text",
        "type": "link_preview",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "text": None,  # EXPLICIT NULL, previously caused crash
        "link_preview": {
            "body": "http://example.com"
        },
        "from": "123456"
    }

    # Should not raise exception
    process_whatsapp_message(message_data)
    
    # Verify insert was called (meaning we got past extraction)
    mock_db_basic["insert"].assert_called_once()
    
    # Verify content extracted correctly from link_preview
    args, _ = mock_db_basic["insert"].call_args
    inserted_msg = args[0]
    assert inserted_msg["content"] == "http://example.com"

def test_process_message_with_null_voice_field(mock_db_basic):
    """Test 'voice': None gracefully."""
    message_data = {
        "id": "msg-voice-null",
        "type": "voice",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "voice": None, # EXPLICIT NULL
        "from": "123456"
    }

    # Should not raise exception
    process_whatsapp_message(message_data)
    
    mock_db_basic["insert"].assert_called_once()
    args, _ = mock_db_basic["insert"].call_args
    assert args[0]["content"] == "[Transcribing voice (msg-voice-null)...]"

def test_process_message_with_null_media_fields(mock_db_basic):
    """Test 'image': None gracefully."""
    message_data = {
        "id": "msg-image-null",
        "type": "image",
        "chat_id": "123@s.whatsapp.net",
        "from_me": False,
        "timestamp": 123456,
        "image": None, # EXPLICIT NULL
        "from": "123456"
    }

    # Should not raise exception
    process_whatsapp_message(message_data)
    
    args, _ = mock_db_basic["insert"].call_args
    assert args[0]["content"] == "[Image message pending processing...]"
