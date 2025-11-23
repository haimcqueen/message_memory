"""
Unit tests for Whapi webhook endpoint.

These tests verify the /webhook/whapi endpoint functionality.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_text_webhook():
    """Sample Whapi webhook with text message."""
    return {
        "event": {
            "type": "messages",
            "event": "message"
        },
        "channel_id": "test-channel-123",
        "messages": [
            {
                "id": "test-msg-001",
                "type": "text",
                "chat_id": "1234567890@s.whatsapp.net",
                "from_me": False,
                "from_name": "Test User",
                "from": "1234567890",
                "source": "mobile",
                "timestamp": 1700000000,
                "text": {
                    "body": "Hello, this is a test"
                }
            }
        ]
    }


@pytest.fixture
def sample_status_webhook():
    """Sample Whapi webhook for status update (not a message)."""
    return {
        "event": {
            "type": "status",
            "event": "status_update"
        },
        "channel_id": "test-channel-123",
        "messages": []
    }


class TestWhapiWebhook:
    """Tests for /webhook/whapi endpoint."""

    @pytest.mark.unit
    def test_webhook_receives_text_message(self, test_client, sample_text_webhook):
        """Test webhook endpoint receives and queues text message."""
        with patch('app.main.message_queue') as mock_queue:
            mock_job = Mock()
            mock_job.id = "job-123"
            mock_queue.enqueue.return_value = mock_job

            response = test_client.post(
                "/webhook/whapi",
                json=sample_text_webhook,
                headers={"Authorization": "Bearer test-token"}
            )

            assert response.status_code == 200
            assert response.json()["status"] == "queued"
            assert response.json()["message_count"] == 1

            # Should enqueue job
            assert mock_queue.enqueue.called

    @pytest.mark.unit
    def test_webhook_ignores_non_message_events(self, test_client, sample_status_webhook):
        """Test webhook ignores status updates and other non-message events."""
        with patch('app.main.message_queue') as mock_queue:
            response = test_client.post(
                "/webhook/whapi",
                json=sample_status_webhook,
                headers={"Authorization": "Bearer test-token"}
            )

            assert response.status_code == 200
            assert response.json()["status"] == "ignored"
            assert response.json()["reason"] == "not a message webhook"

            # Should NOT enqueue any job
            assert not mock_queue.enqueue.called

    @pytest.mark.unit
    def test_webhook_handles_multiple_messages(self, test_client):
        """Test webhook handles multiple messages in one payload."""
        webhook_data = {
            "event": {
                "type": "messages",
                "event": "message"
            },
            "channel_id": "test-channel-123",
            "messages": [
                {
                    "id": "msg-1",
                    "type": "text",
                    "chat_id": "1234567890@s.whatsapp.net",
                    "from_me": False,
                    "from": "1234567890",
                    "source": "mobile",
                    "timestamp": 1700000000,
                    "text": {"body": "Message 1"}
                },
                {
                    "id": "msg-2",
                    "type": "text",
                    "chat_id": "1234567890@s.whatsapp.net",
                    "from_me": False,
                    "from": "1234567890",
                    "source": "mobile",
                    "timestamp": 1700000001,
                    "text": {"body": "Message 2"}
                },
                {
                    "id": "msg-3",
                    "type": "text",
                    "chat_id": "1234567890@s.whatsapp.net",
                    "from_me": False,
                    "from": "1234567890",
                    "source": "mobile",
                    "timestamp": 1700000002,
                    "text": {"body": "Message 3"}
                }
            ]
        }

        with patch('app.main.message_queue') as mock_queue:
            mock_job = Mock()
            mock_job.id = "job-123"
            mock_queue.enqueue.return_value = mock_job

            response = test_client.post(
                "/webhook/whapi",
                json=webhook_data,
                headers={"Authorization": "Bearer test-token"}
            )

            assert response.status_code == 200
            assert response.json()["message_count"] == 3

            # Should enqueue 3 jobs
            assert mock_queue.enqueue.call_count == 3

    @pytest.mark.unit
    def test_webhook_sets_job_timeout(self, test_client, sample_text_webhook):
        """Test that webhook sets appropriate job timeout."""
        with patch('app.main.message_queue') as mock_queue:
            mock_job = Mock()
            mock_job.id = "job-123"
            mock_queue.enqueue.return_value = mock_job

            response = test_client.post(
                "/webhook/whapi",
                json=sample_text_webhook,
                headers={"Authorization": "Bearer test-token"}
            )

            assert response.status_code == 200

            # Check job timeout was set
            call_kwargs = mock_queue.enqueue.call_args[1]
            assert call_kwargs["job_timeout"] == "10m"

    @pytest.mark.unit
    def test_webhook_passes_message_data_correctly(self, test_client, sample_text_webhook):
        """Test that webhook passes message data to job correctly."""
        with patch('app.main.message_queue') as mock_queue:
            mock_job = Mock()
            mock_job.id = "job-123"
            mock_queue.enqueue.return_value = mock_job

            response = test_client.post(
                "/webhook/whapi",
                json=sample_text_webhook,
                headers={"Authorization": "Bearer test-token"}
            )

            assert response.status_code == 200

            # Check message data passed to job
            call_args = mock_queue.enqueue.call_args[0]
            message_data = call_args[1]

            assert message_data["id"] == "test-msg-001"
            assert message_data["type"] == "text"
            assert message_data["chat_id"] == "1234567890@s.whatsapp.net"
            assert message_data["text"]["body"] == "Hello, this is a test"

    @pytest.mark.unit
    def test_webhook_returns_200_immediately(self, test_client, sample_text_webhook):
        """Test that webhook returns 200 immediately without waiting for processing."""
        with patch('app.main.message_queue') as mock_queue:
            mock_job = Mock()
            mock_job.id = "job-123"
            mock_queue.enqueue.return_value = mock_job

            response = test_client.post(
                "/webhook/whapi",
                json=sample_text_webhook,
                headers={"Authorization": "Bearer test-token"}
            )

            # Should return 200 immediately
            assert response.status_code == 200
            assert "queued" in response.json()["status"]


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.mark.unit
    def test_health_check(self, test_client):
        """Test health check endpoint returns healthy status."""
        response = test_client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "whatsapp-message-logger"


class TestRootEndpoint:
    """Tests for root / endpoint."""

    @pytest.mark.unit
    def test_root_endpoint(self, test_client):
        """Test root endpoint returns service info."""
        response = test_client.get("/")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["service"] == "WhatsApp Message Logger"
        assert json_data["version"] == "0.1.0"
        assert "endpoints" in json_data
        assert "/health" in json_data["endpoints"]["health"]
        assert "/webhook/whapi" in json_data["endpoints"]["webhook"]
