"""
Unit tests for n8n error webhook endpoint.

These tests verify the error handling and retry logic for n8n workflow failures.
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
def mock_n8n_api_key():
    """Mock n8n API key for testing."""
    return "test-n8n-api-key-12345"


class TestN8nErrorWebhook:
    """Tests for /webhook/n8n-error endpoint."""

    @pytest.mark.unit
    def test_n8n_error_webhook_with_valid_auth(self, test_client, mock_n8n_api_key):
        """Test n8n error webhook with valid authentication."""
        payload = {
            "user_id": "test-user-123",
            "error_message": "Workflow execution failed",
            "chat_id": "1234567890@s.whatsapp.net"
        }

        with patch('app.main.settings') as mock_settings, \
             patch('utils.whapi_messaging.send_whatsapp_message') as mock_send_msg, \
             patch('workers.batching.add_message_to_batch') as mock_batch:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 200
            assert response.json()["status"] == "success"

            # Verify error notification was sent
            assert mock_send_msg.called
            notification_msg = mock_send_msg.call_args[0][1]
            assert "encountered an issue" in notification_msg.lower()
            assert "retrying" in notification_msg.lower()

            # Verify retry was triggered
            assert mock_batch.called
            assert mock_batch.call_args[1]["user_id"] == "test-user-123"

    @pytest.mark.unit
    def test_n8n_error_webhook_invalid_auth(self, test_client, mock_n8n_api_key):
        """Test n8n error webhook with invalid authentication."""
        payload = {
            "user_id": "test-user-123",
            "error_message": "Workflow execution failed"
        }

        with patch('app.main.settings') as mock_settings:
            mock_settings.n8n_webhook_api_key = mock_n8n_api_key

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": "Bearer wrong-api-key"}
            )

            assert response.status_code == 403
            assert "Invalid n8n API key" in response.json()["detail"]

    @pytest.mark.unit
    def test_n8n_error_webhook_missing_auth(self, test_client):
        """Test n8n error webhook with missing authentication."""
        payload = {
            "user_id": "test-user-123",
            "error_message": "Workflow execution failed"
        }

        response = test_client.post(
            "/webhook/n8n-error",
            json=payload
        )

        assert response.status_code == 401
        assert "Missing or invalid authorization header" in response.json()["detail"]

    @pytest.mark.unit
    def test_n8n_error_webhook_lookup_chat_id(self, test_client, mock_n8n_api_key):
        """Test n8n error webhook when chat_id needs to be looked up."""
        payload = {
            "user_id": "test-user-123",
            "error_message": "Workflow execution failed"
            # chat_id not provided
        }

        with patch('app.main.settings') as mock_settings, \
             patch('workers.database.get_chat_id_by_user_id') as mock_get_chat, \
             patch('utils.whapi_messaging.send_whatsapp_message') as mock_send_msg, \
             patch('workers.batching.add_message_to_batch') as mock_batch:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key
            mock_get_chat.return_value = "1234567890@s.whatsapp.net"

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 200
            assert mock_get_chat.called
            assert mock_get_chat.call_args[0][0] == "test-user-123"
            assert mock_send_msg.called
            assert mock_batch.called

    @pytest.mark.unit
    def test_n8n_error_webhook_chat_id_not_found(self, test_client, mock_n8n_api_key):
        """Test n8n error webhook when chat_id cannot be found."""
        payload = {
            "user_id": "test-user-123",
            "error_message": "Workflow execution failed"
        }

        with patch('app.main.settings') as mock_settings, \
             patch('workers.database.get_chat_id_by_user_id') as mock_get_chat:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key
            mock_get_chat.return_value = None

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 404
            assert "No chat_id found for user" in response.json()["message"]

    @pytest.mark.unit
    def test_n8n_error_webhook_notification_failure_continues(self, test_client, mock_n8n_api_key):
        """Test that webhook continues even if notification fails."""
        payload = {
            "user_id": "test-user-123",
            "error_message": "Workflow execution failed",
            "chat_id": "1234567890@s.whatsapp.net"
        }

        with patch('app.main.settings') as mock_settings, \
             patch('utils.whapi_messaging.send_whatsapp_message') as mock_send_msg, \
             patch('workers.batching.add_message_to_batch') as mock_batch:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key
            mock_send_msg.side_effect = Exception("Whapi API error")

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            # Should still succeed and trigger retry
            assert response.status_code == 200
            assert mock_batch.called

    @pytest.mark.unit
    def test_n8n_error_webhook_retry_failure(self, test_client, mock_n8n_api_key):
        """Test n8n error webhook when retry trigger fails."""
        payload = {
            "user_id": "test-user-123",
            "error_message": "Workflow execution failed",
            "chat_id": "1234567890@s.whatsapp.net"
        }

        with patch('app.main.settings') as mock_settings, \
             patch('utils.whapi_messaging.send_whatsapp_message'), \
             patch('workers.batching.add_message_to_batch') as mock_batch:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key
            mock_batch.side_effect = Exception("Redis connection error")

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 500
            assert "Failed to trigger retry" in response.json()["message"]

    @pytest.mark.unit
    def test_n8n_error_webhook_invalid_payload(self, test_client, mock_n8n_api_key):
        """Test n8n error webhook with missing required fields."""
        payload = {
            # Missing user_id and error_message
            "chat_id": "1234567890@s.whatsapp.net"
        }

        with patch('app.main.settings') as mock_settings:
            mock_settings.n8n_webhook_api_key = mock_n8n_api_key

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 422  # Validation error
