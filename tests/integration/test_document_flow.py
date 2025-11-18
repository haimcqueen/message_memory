"""
Integration tests for document processing flow and n8n batching.

This module tests three critical scenarios:
1. Normal PDF document (<50MB) - should trigger n8n batching
2. Oversized document (>50MB) - should NOT trigger n8n batching
3. Video message - should trigger n8n with notification
"""

import pytest
from unittest.mock import patch
from workers.jobs import process_whatsapp_message


@pytest.fixture
def normal_document_webhook():
    """Webhook data for normal-sized document (10MB)."""
    file_size_bytes = int(10.0 * 1024 * 1024)
    return {
        "id": "test_msg_10mb",
        "type": "document",
        "chat_id": "1234567890@s.whatsapp.net",
        "from_me": False,
        "from": "1234567890",
        "timestamp": 1700000000,
        "document": {
            "id": "media_id_10mb",
            "mime_type": "application/pdf",
            "caption": "Test document",
            "file_size": file_size_bytes
        }
    }


@pytest.fixture
def oversized_document_webhook():
    """Webhook data for oversized document (100MB)."""
    file_size_bytes = int(100.0 * 1024 * 1024)
    return {
        "id": "test_msg_100mb",
        "type": "document",
        "chat_id": "1234567890@s.whatsapp.net",
        "from_me": False,
        "from": "1234567890",
        "timestamp": 1700000000,
        "document": {
            "id": "media_id_100mb",
            "mime_type": "application/pdf",
            "caption": "Large document",
            "file_size": file_size_bytes
        }
    }


@pytest.fixture
def video_webhook():
    """Webhook data for video message (5MB)."""
    file_size_bytes = int(5.0 * 1024 * 1024)
    return {
        "id": "test_msg_5mb_video",
        "type": "video",
        "chat_id": "1234567890@s.whatsapp.net",
        "from_me": False,
        "from": "1234567890",
        "timestamp": 1700000000,
        "video": {
            "id": "media_id_5mb",
            "mime_type": "video/mp4",
            "caption": "Test video",
            "file_size": file_size_bytes
        }
    }


@pytest.mark.integration
@pytest.mark.external_api
def test_normal_document_triggers_n8n(normal_document_webhook):
    """
    Test that normal-sized documents (<50MB) trigger n8n batching.

    Expected behavior:
    - Typing presence is sent
    - "Reading the doc" notification is sent to user
    - Media is processed (downloaded and parsed)
    - Message is inserted to database
    - Message is added to n8n batch
    """
    with patch('workers.jobs.send_presence') as mock_presence, \
         patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
         patch('workers.jobs.process_media_message') as mock_media, \
         patch('workers.jobs.insert_message') as mock_insert, \
         patch('workers.jobs.get_user_id_by_phone') as mock_user_id, \
         patch('workers.jobs.detect_session') as mock_session, \
         patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

        # Setup mocks
        mock_user_id.return_value = "user-123"
        mock_session.return_value = "session-456"
        mock_media.return_value = ("https://storage.url/file.pdf", "parsed content")

        # Execute
        process_whatsapp_message(normal_document_webhook)

        # Assertions
        assert mock_presence.called, "Typing presence should be sent"
        assert mock_send_msg.called, "Document notification should be sent"
        assert "Reading the doc" in mock_send_msg.call_args[0][1], \
            "Notification should indicate document is being read"
        assert mock_media.called, "Media should be processed"
        assert mock_insert.called, "Message should be inserted to database"
        assert mock_n8n_batch.called, "Normal document SHOULD trigger n8n batching"


@pytest.mark.integration
@pytest.mark.external_api
def test_oversized_document_skips_n8n(oversized_document_webhook):
    """
    Test that oversized documents (>50MB) do NOT trigger n8n batching.

    Expected behavior:
    - Typing presence is sent
    - Rejection notification is sent to user
    - Media is NOT processed (file too large)
    - Message is inserted to database with error flag
    - Message is NOT added to n8n batch (critical requirement)
    """
    with patch('workers.jobs.send_presence') as mock_presence, \
         patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
         patch('workers.jobs.insert_message') as mock_insert, \
         patch('workers.jobs.get_user_id_by_phone') as mock_user_id, \
         patch('workers.jobs.detect_session') as mock_session, \
         patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

        # Setup mocks
        mock_user_id.return_value = "user-123"
        mock_session.return_value = "session-456"

        # Execute
        process_whatsapp_message(oversized_document_webhook)

        # Assertions
        assert mock_presence.called, "Typing presence should be sent"
        assert mock_send_msg.called, "Rejection notification should be sent"
        assert "too big" in mock_send_msg.call_args[0][1].lower(), \
            "Notification should indicate file is too large"
        assert mock_insert.called, "Message should be inserted to database"
        assert not mock_n8n_batch.called, \
            "Oversized document should NOT trigger n8n batching (critical requirement)"


@pytest.mark.integration
@pytest.mark.external_api
def test_video_message_triggers_n8n(video_webhook):
    """
    Test that video messages trigger n8n batching with notification.

    Expected behavior:
    - Typing presence is sent
    - "Cannot watch videos yet" notification is sent
    - Media is processed (downloaded but not transcribed)
    - Message is inserted to database
    - Message is added to n8n batch
    """
    with patch('workers.jobs.send_presence') as mock_presence, \
         patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
         patch('workers.jobs.process_media_message') as mock_media, \
         patch('workers.jobs.insert_message') as mock_insert, \
         patch('workers.jobs.get_user_id_by_phone') as mock_user_id, \
         patch('workers.jobs.detect_session') as mock_session, \
         patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

        # Setup mocks
        mock_user_id.return_value = "user-123"
        mock_session.return_value = "session-456"
        mock_media.return_value = ("https://storage.url/video.mp4", None)

        # Execute
        process_whatsapp_message(video_webhook)

        # Assertions
        assert mock_presence.called, "Typing presence should be sent"
        assert mock_send_msg.called, "Video notification should be sent"
        assert "cannot watch videos" in mock_send_msg.call_args[0][1].lower(), \
            "Notification should indicate videos are not supported"
        assert mock_media.called, "Media should be processed"
        assert mock_insert.called, "Message should be inserted to database"
        assert mock_n8n_batch.called, "Video message SHOULD trigger n8n batching"
