"""
Unit tests for n8n error webhook endpoint.

These tests verify the error notification for n8n workflow failures.
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
            "error_message": "Workflow execution failed"
        }

        with patch('app.main.settings') as mock_settings, \
             patch('utils.whapi_messaging.send_whatsapp_message') as mock_send_msg:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 200
            assert response.json()["status"] == "success"

            # Verify error notification was sent to admin
            assert mock_send_msg.called
            notification_msg = mock_send_msg.call_args[0][1]
            assert "workflow error" in notification_msg.lower()
            assert "workflow execution failed" in notification_msg.lower()

            # Verify it was sent to the correct admin chat_id
            admin_chat_id = mock_send_msg.call_args[0][0]
            assert admin_chat_id == "4915202618514@s.whatsapp.net"

    @pytest.mark.unit
    def test_n8n_error_webhook_invalid_auth(self, test_client, mock_n8n_api_key):
        """Test n8n error webhook with invalid authentication."""
        payload = {
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
            "error_message": "Workflow execution failed"
        }

        response = test_client.post(
            "/webhook/n8n-error",
            json=payload
        )

        assert response.status_code == 401
        assert "Missing or invalid authorization header" in response.json()["detail"]

    @pytest.mark.unit
    def test_n8n_error_webhook_notification_failure(self, test_client, mock_n8n_api_key):
        """Test that webhook returns error if notification fails."""
        payload = {
            "error_message": "Workflow execution failed"
        }

        with patch('app.main.settings') as mock_settings, \
             patch('utils.whapi_messaging.send_whatsapp_message') as mock_send_msg:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key
            mock_send_msg.side_effect = Exception("Whapi API error")

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 500
            assert "Failed to send notification" in response.json()["message"]

    @pytest.mark.unit
    def test_n8n_error_webhook_accepts_any_format(self, test_client, mock_n8n_api_key):
        """Test that webhook accepts any n8n error format."""
        payload = {
            "execution": {
                "id": 231,
                "error": {
                    "message": "Example Error Message",
                    "stack": "Stacktrace"
                }
            },
            "workflow": {
                "name": "Example Workflow"
            }
        }

        with patch('app.main.settings') as mock_settings, \
             patch('utils.whapi_messaging.send_whatsapp_message') as mock_send_msg:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 200
            assert mock_send_msg.called

            # When error_message not provided, should use "Unknown error"
            notification_msg = mock_send_msg.call_args[0][1]
            assert "unknown error" in notification_msg.lower()

    @pytest.mark.unit
    def test_n8n_error_webhook_empty_payload(self, test_client, mock_n8n_api_key):
        """Test that webhook accepts even empty payloads."""
        payload = {}

        with patch('app.main.settings') as mock_settings, \
             patch('utils.whapi_messaging.send_whatsapp_message') as mock_send_msg:

            mock_settings.n8n_webhook_api_key = mock_n8n_api_key

            response = test_client.post(
                "/webhook/n8n-error",
                json=payload,
                headers={"Authorization": f"Bearer {mock_n8n_api_key}"}
            )

            assert response.status_code == 200
            assert mock_send_msg.called
