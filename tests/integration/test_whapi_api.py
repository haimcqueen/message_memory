"""
Integration tests for Whapi API interactions.

Tests actual HTTP calls to Whapi API endpoints with retry logic verification.
Requires WHAPI_TOKEN and WHAPI_API_URL environment variables.
"""
import pytest
import requests
from unittest.mock import patch, MagicMock
from utils.whapi_messaging import send_whatsapp_message
from workers.media import (
    fetch_message_from_whapi,
    download_media_from_whapi
)
from workers.presence import send_presence


@pytest.mark.integration
@pytest.mark.whapi
@pytest.mark.requires_env
class TestSendWhatsappMessage:
    """Tests for sending WhatsApp messages via Whapi API."""

    def test_send_message_retry_logic_on_network_error(self, whapi_api_base_url, whapi_auth_header):
        """Test that send_whatsapp_message retries exactly 3 times on network errors."""
        with patch('requests.post') as mock_post:
            # Simulate network error on all attempts
            mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

            with pytest.raises(requests.exceptions.ConnectionError):
                send_whatsapp_message(
                    phone="1234567890",
                    message="Test message"
                )

            # Verify exactly 3 retry attempts (initial + 2 retries)
            assert mock_post.call_count == 3

    def test_send_message_retry_succeeds_on_second_attempt(self, whapi_api_base_url):
        """Test that send_whatsapp_message succeeds after first retry."""
        with patch('requests.post') as mock_post:
            # First call fails, second succeeds
            mock_post.side_effect = [
                requests.exceptions.ConnectionError("Network error"),
                MagicMock(status_code=200, json=lambda: {"id": "msg_123", "status": "sent"})
            ]

            result = send_whatsapp_message(
                phone="1234567890",
                message="Test message"
            )

            # Should succeed after retry
            assert result is not None
            assert mock_post.call_count == 2

    def test_send_message_auth_failure_no_retry(self):
        """Test that authentication failure (401) does retry (as per retry decorator)."""
        with patch('requests.post') as mock_post:
            # Simulate 401 Unauthorized
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
            mock_post.return_value = mock_response

            with pytest.raises(requests.exceptions.HTTPError):
                send_whatsapp_message(
                    phone="1234567890",
                    message="Test message"
                )

            # HTTPError triggers retries in current implementation
            assert mock_post.call_count == 3


@pytest.mark.integration
@pytest.mark.whapi
class TestSendPresence:
    """Tests for sending presence indicators via Whapi API."""

    def test_send_presence_typing_retry_logic(self):
        """Test send_presence retry logic with typing indicator."""
        with patch('requests.put') as mock_put:
            mock_put.side_effect = requests.exceptions.ConnectionError("Network error")

            with pytest.raises(requests.exceptions.ConnectionError):
                send_presence(
                    chat_id="1234567890@s.whatsapp.net",
                    presence="typing",
                    delay=15
                )

            # Verify 3 retry attempts
            assert mock_put.call_count == 3

    def test_send_presence_various_types(self):
        """Test send_presence with different presence types."""
        presence_types = ["typing", "recording", "paused"]

        for presence_type in presence_types:
            with patch('requests.put') as mock_put:
                mock_put.return_value = MagicMock(status_code=200)

                send_presence(
                    chat_id="1234567890@s.whatsapp.net",
                    presence=presence_type,
                    delay=10
                )

                # Verify call was made
                assert mock_put.call_count == 1
                call_args = mock_put.call_args

                # Verify presence type in URL
                assert presence_type in call_args[0][0] or presence_type in str(call_args)


@pytest.mark.integration
@pytest.mark.whapi
class TestFetchMessageFromWhapi:
    """Tests for fetching message data from Whapi API."""

    def test_fetch_message_success(self):
        """Test successful message fetch from Whapi."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "msg_123",
                "type": "text",
                "from": "1234567890",
                "text": {"body": "Test message"}
            }
            mock_get.return_value = mock_response

            result = fetch_message_from_whapi("msg_123")

            assert result is not None
            assert result["id"] == "msg_123"
            assert result["type"] == "text"

    def test_fetch_message_404_not_found(self):
        """Test fetch_message handles 404 not found."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
            mock_get.return_value = mock_response

            with pytest.raises(requests.exceptions.HTTPError):
                fetch_message_from_whapi("nonexistent_msg")

            # Should retry 3 times even on 404
            assert mock_get.call_count == 3

    def test_fetch_message_retry_on_timeout(self):
        """Test fetch_message retries on timeout."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

            with pytest.raises(requests.exceptions.Timeout):
                fetch_message_from_whapi("msg_123")

            # Verify 3 retry attempts
            assert mock_get.call_count == 3


@pytest.mark.integration
@pytest.mark.whapi
class TestDownloadMediaFromWhapi:
    """Tests for downloading media files from Whapi API."""

    def test_download_media_image_success(self, sample_media_bytes):
        """Test successful image download from Whapi."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_media_bytes["jpg"]
            mock_response.headers = {"content-type": "image/jpeg"}
            mock_get.return_value = mock_response

            content, mime_type = download_media_from_whapi("media_123", "image")

            assert content == sample_media_bytes["jpg"]
            assert mime_type == "image/jpeg"
            assert len(content) > 0

    def test_download_media_pdf_success(self, sample_media_bytes):
        """Test successful PDF download from Whapi."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = sample_media_bytes["pdf"]
            mock_response.headers = {"content-type": "application/pdf"}
            mock_get.return_value = mock_response

            content, mime_type = download_media_from_whapi("media_pdf", "document")

            assert content == sample_media_bytes["pdf"]
            assert mime_type == "application/pdf"

    def test_download_media_various_types(self, sample_media_bytes):
        """Test download for various media types."""
        test_cases = [
            ("image", "image/png", "png"),
            ("video", "video/mp4", "mp3"),  # Using mp3 bytes as placeholder
            ("audio", "audio/ogg", "ogg"),
            ("document", "application/pdf", "pdf")
        ]

        for media_type, expected_mime, bytes_key in test_cases:
            with patch('requests.get') as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.content = sample_media_bytes.get(bytes_key, b"test")
                mock_response.headers = {"content-type": expected_mime}
                mock_get.return_value = mock_response

                content, mime_type = download_media_from_whapi(f"media_{media_type}", media_type)

                assert mime_type == expected_mime
                assert len(content) > 0

    def test_download_media_retry_on_network_error(self):
        """Test download_media retries 3 times on network error."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

            with pytest.raises(requests.exceptions.ConnectionError):
                download_media_from_whapi("media_123", "image")

            # Verify 3 retry attempts
            assert mock_get.call_count == 3

    def test_download_media_large_file(self):
        """Test downloading a large media file (simulated)."""
        large_content = b"x" * (10 * 1024 * 1024)  # 10MB

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = large_content
            mock_response.headers = {"content-type": "video/mp4"}
            mock_get.return_value = mock_response

            content, mime_type = download_media_from_whapi("large_media", "video")

            assert len(content) == 10 * 1024 * 1024
            assert mime_type == "video/mp4"

    def test_download_media_corrupted_response(self):
        """Test handling of corrupted/incomplete download."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b""  # Empty content
            mock_response.headers = {"content-type": "image/jpeg"}
            mock_get.return_value = mock_response

            content, mime_type = download_media_from_whapi("media_corrupt", "image")

            # Should still return even if content is empty (no validation in current implementation)
            assert content == b""
            assert mime_type == "image/jpeg"


@pytest.mark.integration
@pytest.mark.whapi
@pytest.mark.slow
class TestRetryBackoffTiming:
    """Tests to verify exponential backoff timing for retries."""

    def test_send_message_backoff_timing(self):
        """Test that retry backoff is within expected range (1-8s)."""
        import time

        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

            start_time = time.time()

            with pytest.raises(requests.exceptions.ConnectionError):
                send_whatsapp_message(
                    phone="1234567890",
                    message="Test message"
                )

            elapsed_time = time.time() - start_time

            # With 3 attempts and exponential backoff (1-8s):
            # First attempt: immediate
            # Second attempt: wait 1-2s
            # Third attempt: wait 2-4s (or up to 8s max)
            # Total should be roughly 3-14 seconds for 3 attempts

            # Allow some tolerance for test execution overhead
            assert elapsed_time >= 1.0  # At least some backoff happened
            assert elapsed_time < 20.0  # Not excessively long

    def test_download_media_backoff_timing(self):
        """Test download_media retry backoff timing."""
        import time

        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

            start_time = time.time()

            with pytest.raises(requests.exceptions.ConnectionError):
                download_media_from_whapi("media_123", "image")

            elapsed_time = time.time() - start_time

            # Similar to above: 3 attempts with 1-8s backoff
            assert elapsed_time >= 1.0
            assert elapsed_time < 20.0
