"""
Unit tests for workers.jobs module focusing on file size validation logic.

These tests verify the core business logic for handling document size limits
without requiring full integration with external services.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from workers.jobs import process_whatsapp_message


class TestFileSizeValidation:
    """Tests for document file size validation logic."""

    @pytest.mark.unit
    def test_file_size_check_at_exactly_limit(self, mock_settings):
        """Test document at exactly the size limit (50MB) should be accepted."""
        # Exactly 50MB
        file_size_bytes = 50 * 1024 * 1024

        webhook_data = {
            "id": "test-msg-exact-limit",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-exact",
                "mime_type": "application/pdf",
                "caption": "Test at limit",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message'), \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            mock_media.return_value = ("https://storage.url/file.pdf", "parsed content")

            process_whatsapp_message(webhook_data)

            # Should be accepted (not oversized)
            assert mock_media.called, "Document at exact limit should be processed"
            assert mock_n8n_batch.called, "Document at exact limit should trigger n8n"
            # Should send "Reading the doc" notification, not rejection
            if mock_send_msg.called:
                notification = mock_send_msg.call_args[0][1]
                assert "too big" not in notification.lower(), \
                    "Should not send rejection message for document at limit"

    @pytest.mark.unit
    def test_file_size_check_just_over_limit(self, mock_settings):
        """Test document just over limit (50MB + 1 byte) should be rejected."""
        # 50MB + 1 byte
        file_size_bytes = (50 * 1024 * 1024) + 1

        webhook_data = {
            "id": "test-msg-over-limit",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-over",
                "mime_type": "application/pdf",
                "caption": "Test over limit",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message'), \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Should be rejected
            assert not mock_media.called, "Oversized document should not be processed"
            assert not mock_n8n_batch.called, "Oversized document should not trigger n8n"
            # Should send rejection notification
            assert mock_send_msg.called, "Should send rejection notification"
            notification = mock_send_msg.call_args[0][1]
            assert "we don't support media of this size" in notification.lower(), \
                "Should send unified rejection message"

    @pytest.mark.unit
    def test_file_size_check_well_under_limit(self, mock_settings):
        """Test small document (1MB) should be accepted."""
        file_size_bytes = 1 * 1024 * 1024

        webhook_data = {
            "id": "test-msg-small",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-small",
                "mime_type": "application/pdf",
                "caption": "Small doc",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message'), \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            mock_media.return_value = ("https://storage.url/file.pdf", "parsed content")

            process_whatsapp_message(webhook_data)

            # Should be accepted
            assert mock_media.called, "Small document should be processed"
            assert mock_n8n_batch.called, "Small document should trigger n8n"
            # Should send "Reading the doc" notification
            assert mock_send_msg.called
            notification = mock_send_msg.call_args[0][1]
            assert "Reading the doc" in notification or "reading the doc" in notification.lower()

    @pytest.mark.unit
    def test_skip_n8n_flag_set_before_exception(self, mock_settings):
        """
        Test that skip_n8n_batch flag is set BEFORE attempting notifications.

        This is the critical fix: even if send_whatsapp_message() throws an exception,
        the skip_n8n_batch flag should already be set to True.
        """
        # 100MB document
        file_size_bytes = 100 * 1024 * 1024

        webhook_data = {
            "id": "test-msg-exception",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-exception",
                "mime_type": "application/pdf",
                "caption": "Test exception handling",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.insert_message'), \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            # Simulate Whapi API failure
            mock_send_msg.side_effect = Exception("Whapi 500 Server Error")

            # Should not raise exception (graceful handling)
            process_whatsapp_message(webhook_data)

            # Critical assertion: n8n should NOT be called even though notification failed
            assert not mock_n8n_batch.called, \
                "n8n should NOT be triggered even when notification fails (skip flag set before exception)"

    @pytest.mark.unit
    def test_agent_messages_never_batched(self, mock_settings):
        """Test that agent messages (from_me=True) are never added to n8n batch."""
        webhook_data = {
            "id": "test-msg-agent",
            "type": "text",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": True,  # Agent message
            "from": "agent-phone",
            "timestamp": 1700000000,
            "text": {"body": "This is a response from the agent"}
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.insert_message'), \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Agent messages should never trigger n8n batching
            assert not mock_n8n_batch.called, \
                "Agent messages (from_me=True) should never trigger n8n batching"

    @pytest.mark.unit
    def test_video_messages_also_affected_by_size_limit(self, mock_settings):
        """Test that video messages ARE affected by the 50MB size limit."""
        # 75MB video (larger than 50MB limit)
        file_size_bytes = 75 * 1024 * 1024

        webhook_data = {
            "id": "test-msg-large-video",
            "type": "video",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "video": {
                "id": "media-id-video",
                "mime_type": "video/mp4",
                "caption": "Large video",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message'), \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Videos over 50MB should be rejected
            assert not mock_media.called, "Oversized video should not be processed"
            assert not mock_n8n_batch.called, "Oversized video should not trigger n8n"
            # Should send rejection notification
            assert mock_send_msg.called, "Should send rejection notification"
            notification = mock_send_msg.call_args[0][1]
            assert "we don't support media of this size" in notification.lower(), \
                "Should send unified rejection message for oversized video"

    @pytest.mark.unit
    def test_zero_size_document(self, mock_settings):
        """Test document with zero file size (edge case)."""
        webhook_data = {
            "id": "test-msg-zero-size",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-zero",
                "mime_type": "application/pdf",
                "caption": "Empty doc",
                "file_size": 0
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message'), \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            mock_media.return_value = ("https://storage.url/file.pdf", "")

            process_whatsapp_message(webhook_data)

            # Zero size should be accepted (not > limit)
            assert mock_media.called, "Zero-size document should be processed"
            assert mock_n8n_batch.called, "Zero-size document should trigger n8n"

    @pytest.mark.unit
    def test_custom_size_limit(self):
        """Test with custom size limit setting (100MB)."""
        # Mock settings with custom limit
        custom_settings = Mock()
        custom_settings.max_file_size_mb = 100  # 100MB limit instead of 50MB

        # 75MB document (under 100MB limit)
        file_size_bytes = 75 * 1024 * 1024

        webhook_data = {
            "id": "test-msg-custom-limit",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-custom",
                "mime_type": "application/pdf",
                "caption": "75MB doc",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', custom_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message'), \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            mock_media.return_value = ("https://storage.url/file.pdf", "parsed content")

            process_whatsapp_message(webhook_data)

            # 75MB should be accepted with 100MB limit
            assert mock_media.called, "75MB document should be processed with 100MB limit"
            assert mock_n8n_batch.called, "75MB document should trigger n8n with 100MB limit"

    @pytest.mark.unit
    def test_unknown_phone_number_rejection(self, mock_settings):
        """Test that messages from unknown phone numbers are rejected with a message."""
        webhook_data = {
            "id": "test-msg-unknown-number",
            "type": "text",
            "chat_id": "9999999999@s.whatsapp.net",
            "from_me": False,
            "from": "9999999999",
            "timestamp": 1700000000,
            "text": {"body": "Hello, can you help me?"}
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value=None), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Should send rejection message
            assert mock_send_msg.called, "Should send rejection message to unknown number"
            rejection_message = mock_send_msg.call_args[0][1]
            assert "not in our database" in rejection_message.lower(), \
                "Rejection message should indicate number not in database"
            assert "contact the publyc team" in rejection_message.lower(), \
                "Rejection message should tell them to contact publyc"

            # Should NOT insert to database
            assert not mock_insert.called, \
                "Should not insert message from unknown number to database"

            # Should NOT trigger n8n batching
            assert not mock_n8n_batch.called, \
                "Should not trigger n8n for unknown number"

    @pytest.mark.unit
    def test_unknown_phone_number_rejection_handles_api_failure(self, mock_settings):
        """Test that unknown number rejection handles API failures gracefully."""
        webhook_data = {
            "id": "test-msg-unknown-api-fail",
            "type": "text",
            "chat_id": "9999999999@s.whatsapp.net",
            "from_me": False,
            "from": "9999999999",
            "timestamp": 1700000000,
            "text": {"body": "Hello"}
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value=None), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            # Simulate Whapi API failure
            mock_send_msg.side_effect = Exception("Whapi API error")

            # Should not raise exception (graceful handling)
            process_whatsapp_message(webhook_data)

            # Even though notification failed, should still not insert or batch
            assert not mock_insert.called, \
                "Should not insert to database even if rejection message fails"
            assert not mock_n8n_batch.called, \
                "Should not trigger n8n even if rejection message fails"

    @pytest.mark.unit
    def test_agent_messages_with_null_user_id_not_inserted(self, mock_settings):
        """Test that agent messages (from_me=True) with NULL user_id are NOT inserted.

        This is correct behavior - agent messages to unknown users (rejection messages)
        should not be stored in the database.
        """
        webhook_data = {
            "id": "test-msg-agent-null-user",
            "type": "text",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": True,  # Agent message
            "from": "agent-phone",
            "timestamp": 1700000000,
            "text": {"body": "This is a response from the agent"}
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value=None), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Agent messages to unknown users should NOT be inserted
            assert not mock_insert.called, \
                "Agent messages to unknown users should NOT be inserted to database"

            # Agent messages should never trigger n8n batching (tested elsewhere)
            assert not mock_n8n_batch.called, \
                "Agent messages should never trigger n8n batching"

            # Should NOT send rejection message to agent
            rejection_calls = [call for call in mock_send_msg.call_args_list
                             if "not in our database" in str(call).lower()]
            assert len(rejection_calls) == 0, \
                "Should not send rejection message for agent messages"

class TestMediaTypeHandling:
    """Tests for media type handling, storage, and acknowledgments."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with standard 50MB limit."""
        mock = Mock()
        mock.max_file_size_mb = 50
        return mock

    @pytest.mark.unit
    def test_image_acceptable_size(self, mock_settings):
        """Test image processing with acceptable size."""
        file_size_bytes = 10 * 1024 * 1024  # 10MB

        webhook_data = {
            "id": "test-msg-image",
            "type": "image",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "image": {
                "id": "media-id-image",
                "mime_type": "image/jpeg",
                "caption": "Check this out!",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            # Mock media processing to return storage URL and parsed content
            mock_media.return_value = ("https://storage.url/image.jpg", "<image>\nA beautiful sunset over the ocean\n</image>")

            process_whatsapp_message(webhook_data)

            # Verify media was processed
            assert mock_media.called, "Image should be processed"
            assert mock_media.call_args[1]['media_type'] == 'image'
            assert mock_media.call_args[1]['media_id'] == 'media-id-image'

            # Verify correct acknowledgment message
            assert mock_send_msg.called
            notification = mock_send_msg.call_args[0][1]
            assert "let me check out that image" in notification.lower()

            # Verify database insertion with media_url and extracted_media_content
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] == "https://storage.url/image.jpg"
            assert db_payload['type'] == 'image'
            assert db_payload['content'] == "Check this out!"
            assert db_payload['extracted_media_content'] == "<image>\nA beautiful sunset over the ocean\n</image>"

            # Verify n8n batching triggered
            assert mock_n8n_batch.called

    @pytest.mark.unit
    def test_image_oversized(self, mock_settings):
        """Test oversized image rejection."""
        file_size_bytes = 75 * 1024 * 1024  # 75MB

        webhook_data = {
            "id": "test-msg-image-large",
            "type": "image",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "image": {
                "id": "media-id-image-large",
                "mime_type": "image/jpeg",
                "caption": "Big image",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.jobs.create_processing_job') as mock_job, \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Verify media was NOT processed
            assert not mock_media.called, "Oversized image should not be processed"

            # Verify rejection message
            assert mock_send_msg.called
            notification = mock_send_msg.call_args[0][1]
            assert "we don't support media of this size" in notification.lower()

            # Verify database insertion with NO media_url
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] is None
            assert "too large" in db_payload['content'].lower()

            # Verify n8n batching NOT triggered
            assert not mock_n8n_batch.called

            # Verify processing job created
            assert mock_job.called

    @pytest.mark.unit
    def test_image_content_extraction(self, mock_settings):
        """Test that image content is extracted and saved to extracted_media_content."""
        file_size_bytes = 5 * 1024 * 1024  # 5MB

        webhook_data = {
            "id": "test-msg-image-extract",
            "type": "image",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "image": {
                "id": "media-id-image-extract",
                "mime_type": "image/jpeg",
                "caption": "Screenshot with text",
                "file_size": file_size_bytes
            }
        }

        extracted_content = "<image>\nText visible in image: 'Hello World'\nObjects: Computer screen, keyboard\nColors: Blue background, white text\n</image>"

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            # Mock media processing to return both URL and extracted content
            mock_media.return_value = ("https://storage.url/screenshot.jpg", extracted_content)

            process_whatsapp_message(webhook_data)

            # Verify media was processed
            assert mock_media.called
            assert mock_media.call_args[1]['media_type'] == 'image'

            # Verify database insertion includes extracted_media_content
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] == "https://storage.url/screenshot.jpg"
            assert db_payload['extracted_media_content'] == extracted_content
            assert '<image>' in db_payload['extracted_media_content']
            assert 'Hello World' in db_payload['extracted_media_content']

            # Verify n8n batching triggered with extracted content
            assert mock_n8n_batch.called

    @pytest.mark.unit
    def test_video_acceptable_size(self, mock_settings):
        """Test video processing with acceptable size."""
        file_size_bytes = 10 * 1024 * 1024  # 10MB

        webhook_data = {
            "id": "test-msg-video",
            "type": "video",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "video": {
                "id": "media-id-video",
                "mime_type": "video/mp4",
                "caption": "Watch this",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            mock_media.return_value = ("https://storage.url/video.mp4", None)

            process_whatsapp_message(webhook_data)

            # Verify media was processed
            assert mock_media.called
            assert mock_media.call_args[1]['media_type'] == 'video'

            # Verify correct acknowledgment message
            assert mock_send_msg.called
            notification = mock_send_msg.call_args[0][1]
            assert "oh we don't support videos yet" in notification.lower()

            # Verify database insertion
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] == "https://storage.url/video.mp4"
            assert db_payload['type'] == 'video'

            # Verify n8n batching triggered
            assert mock_n8n_batch.called

    @pytest.mark.unit
    def test_video_oversized(self, mock_settings):
        """Test oversized video rejection."""
        file_size_bytes = 75 * 1024 * 1024  # 75MB

        webhook_data = {
            "id": "test-msg-video-large",
            "type": "video",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "video": {
                "id": "media-id-video-large",
                "mime_type": "video/mp4",
                "caption": "",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.jobs.create_processing_job') as mock_job, \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Verify media was NOT processed
            assert not mock_media.called

            # Verify rejection message
            assert mock_send_msg.called
            notification = mock_send_msg.call_args[0][1]
            assert "we don't support media of this size" in notification.lower()

            # Verify database insertion
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] is None

            # Verify n8n batching NOT triggered
            assert not mock_n8n_batch.called

            # Verify processing job created
            assert mock_job.called

    @pytest.mark.unit
    def test_audio_acceptable_size(self, mock_settings):
        """Test audio processing with acceptable size."""
        file_size_bytes = 5 * 1024 * 1024  # 5MB

        webhook_data = {
            "id": "test-msg-audio",
            "type": "audio",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "audio": {
                "id": "media-id-audio",
                "mime_type": "audio/ogg",
                "caption": "",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            mock_media.return_value = ("https://storage.url/audio.ogg", None)

            process_whatsapp_message(webhook_data)

            # Verify media was processed
            assert mock_media.called
            assert mock_media.call_args[1]['media_type'] == 'audio'

            # Verify acknowledgment message for audio
            assert mock_send_msg.called
            mock_send_msg.assert_called_once_with(
                "1234567890@s.whatsapp.net",
                "Let me listen to your voice note."
            )

            # Verify database insertion
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] == "https://storage.url/audio.ogg"
            assert db_payload['type'] == 'audio'

            # Verify n8n batching triggered
            assert mock_n8n_batch.called

    @pytest.mark.unit
    def test_audio_oversized(self, mock_settings):
        """Test oversized audio rejection."""
        file_size_bytes = 75 * 1024 * 1024  # 75MB

        webhook_data = {
            "id": "test-msg-audio-large",
            "type": "audio",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "audio": {
                "id": "media-id-audio-large",
                "mime_type": "audio/mpeg",
                "caption": "",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.jobs.create_processing_job') as mock_job, \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Verify media was NOT processed
            assert not mock_media.called

            # Verify rejection message
            assert mock_send_msg.called
            notification = mock_send_msg.call_args[0][1]
            assert "we don't support media of this size" in notification.lower()

            # Verify database insertion
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] is None

            # Verify n8n batching NOT triggered
            assert not mock_n8n_batch.called

            # Verify processing job created
            assert mock_job.called

    @pytest.mark.unit
    def test_document_acceptable_size(self, mock_settings):
        """Test document processing with acceptable size."""
        file_size_bytes = 10 * 1024 * 1024  # 10MB

        webhook_data = {
            "id": "test-msg-document",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-document",
                "mime_type": "application/pdf",
                "caption": "Important doc",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            mock_media.return_value = ("https://storage.url/document.pdf", "Parsed PDF content goes here")

            process_whatsapp_message(webhook_data)

            # Verify media was processed
            assert mock_media.called
            assert mock_media.call_args[1]['media_type'] == 'document'

            # Verify correct acknowledgment message
            assert mock_send_msg.called
            notification = mock_send_msg.call_args[0][1]
            assert "reading the doc" in notification.lower()

            # Verify database insertion
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] == "https://storage.url/document.pdf"
            assert db_payload['type'] == 'document'

            # Verify n8n batching triggered
            assert mock_n8n_batch.called

    @pytest.mark.unit
    def test_document_oversized(self, mock_settings):
        """Test oversized document rejection."""
        file_size_bytes = 75 * 1024 * 1024  # 75MB

        webhook_data = {
            "id": "test-msg-document-large",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-document-large",
                "mime_type": "application/pdf",
                "caption": "",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.jobs.create_processing_job') as mock_job, \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            process_whatsapp_message(webhook_data)

            # Verify media was NOT processed
            assert not mock_media.called

            # Verify rejection message
            assert mock_send_msg.called
            notification = mock_send_msg.call_args[0][1]
            assert "we don't support media of this size" in notification.lower()

            # Verify database insertion
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] is None

            # Verify n8n batching NOT triggered
            assert not mock_n8n_batch.called

            # Verify processing job created
            assert mock_job.called

    @pytest.mark.unit
    def test_pdf_content_extraction(self, mock_settings):
        """Test PDF document with content extraction."""
        file_size_bytes = 5 * 1024 * 1024  # 5MB

        webhook_data = {
            "id": "test-msg-pdf-extraction",
            "type": "document",
            "chat_id": "1234567890@s.whatsapp.net",
            "from_me": False,
            "from": "1234567890",
            "timestamp": 1700000000,
            "document": {
                "id": "media-id-pdf",
                "mime_type": "application/pdf",
                "caption": "PDF with content",
                "file_size": file_size_bytes
            }
        }

        with patch('workers.jobs.settings', mock_settings), \
             patch('workers.jobs.send_presence'), \
             patch('workers.jobs.send_whatsapp_message') as mock_send_msg, \
             patch('workers.jobs.process_media_message') as mock_media, \
             patch('workers.jobs.insert_message') as mock_insert, \
             patch('workers.jobs.get_user_id_by_phone', return_value="user-123"), \
             patch('workers.batching.add_message_to_batch') as mock_n8n_batch:

            # Mock media processing to return both storage URL and parsed content
            mock_media.return_value = ("https://storage.url/document.pdf", "This is the extracted PDF content with important information.")

            process_whatsapp_message(webhook_data)

            # Verify media was processed
            assert mock_media.called

            # Verify database insertion with extracted content
            assert mock_insert.called
            db_payload = mock_insert.call_args[0][0]
            assert db_payload['media_url'] == "https://storage.url/document.pdf"
            assert db_payload['extracted_media_content'] == "This is the extracted PDF content with important information."
            assert db_payload['content'] == "PDF with content"  # Caption should remain in content field
            assert db_payload['type'] == 'document'

            # Verify n8n batching triggered
            assert mock_n8n_batch.called
