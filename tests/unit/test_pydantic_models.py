"""
Comprehensive Pydantic model validation tests.

Tests all model classes from app/models.py to ensure proper validation,
serialization, and error handling.
"""
import pytest
from pydantic import ValidationError
from app.models import (
    TextContent,
    VoiceContent,
    ImageContent,
    Message,
    Event,
    WhapiWebhook,
    N8nErrorWebhook
)


@pytest.mark.unit
class TestTextContent:
    """Tests for TextContent model validation."""

    def test_valid_text_content(self):
        """Test valid text content creation."""
        content = TextContent(body="Hello, world!")
        assert content.body == "Hello, world!"

    def test_text_content_empty_string(self):
        """Test text content with empty string (should be valid)."""
        content = TextContent(body="")
        assert content.body == ""

    def test_text_content_missing_body(self):
        """Test text content missing required body field."""
        with pytest.raises(ValidationError) as exc_info:
            TextContent()
        assert "body" in str(exc_info.value)

    def test_text_content_wrong_type(self):
        """Test text content with wrong type for body."""
        with pytest.raises(ValidationError):
            TextContent(body=123)


@pytest.mark.unit
class TestVoiceContent:
    """Tests for VoiceContent model validation."""

    def test_valid_voice_content(self):
        """Test valid voice content with all required fields."""
        voice = VoiceContent(
            id="voice123",
            mime_type="audio/ogg",
            file_size=12345,
            sha256="abc123def456",
            link="https://whapi.cloud/media/voice123",
            seconds=15
        )
        assert voice.id == "voice123"
        assert voice.mime_type == "audio/ogg"
        assert voice.file_size == 12345
        assert voice.seconds == 15

    def test_voice_content_missing_id(self):
        """Test voice content missing required id field."""
        with pytest.raises(ValidationError) as exc_info:
            VoiceContent(
                mime_type="audio/ogg",
                file_size=12345,
                sha256="abc123",
                link="https://example.com",
                seconds=15
            )
        assert "id" in str(exc_info.value)

    def test_voice_content_missing_multiple_fields(self):
        """Test voice content missing multiple required fields."""
        with pytest.raises(ValidationError) as exc_info:
            VoiceContent(id="voice123")
        # Should complain about mime_type, file_size, sha256, link, seconds
        error_str = str(exc_info.value)
        assert "mime_type" in error_str
        assert "file_size" in error_str
        assert "seconds" in error_str

    def test_voice_content_wrong_types(self):
        """Test voice content with wrong types for fields."""
        with pytest.raises(ValidationError):
            VoiceContent(
                id="voice123",
                mime_type="audio/ogg",
                file_size="not_a_number",  # Should be int
                sha256="abc123",
                link="https://example.com",
                seconds=15
            )


@pytest.mark.unit
class TestImageContent:
    """Tests for ImageContent model validation."""

    def test_valid_image_content_minimal(self):
        """Test valid image content with only required fields."""
        image = ImageContent(
            id="img123",
            mime_type="image/jpeg",
            file_size=500000,
            sha256="abc123def456"
        )
        assert image.id == "img123"
        assert image.mime_type == "image/jpeg"
        assert image.link is None  # Optional field
        assert image.caption is None  # Optional field

    def test_valid_image_content_full(self):
        """Test valid image content with all fields including optionals."""
        image = ImageContent(
            id="img123",
            mime_type="image/png",
            file_size=750000,
            sha256="abc123def456",
            link="https://whapi.cloud/media/img123",
            caption="Check this out!",
            width=1920,
            height=1080,
            preview="base64encodedpreview..."
        )
        assert image.id == "img123"
        assert image.caption == "Check this out!"
        assert image.width == 1920
        assert image.height == 1080
        assert image.preview == "base64encodedpreview..."

    def test_image_content_various_mime_types(self):
        """Test image content accepts different image MIME types."""
        mime_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        for mime in mime_types:
            image = ImageContent(
                id=f"img_{mime.split('/')[-1]}",
                mime_type=mime,
                file_size=100000,
                sha256="abc123"
            )
            assert image.mime_type == mime

    def test_image_content_missing_required(self):
        """Test image content missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            ImageContent(id="img123")
        error_str = str(exc_info.value)
        assert "mime_type" in error_str
        assert "file_size" in error_str
        assert "sha256" in error_str


@pytest.mark.unit
class TestMessage:
    """Tests for Message model validation."""

    def test_valid_text_message(self):
        """Test valid text message."""
        msg = Message(
            id="msg123",
            from_me=False,
            type="text",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            text=TextContent(body="Hello"),
            **{"from": "1234567890"}  # Using from_ alias
        )
        assert msg.id == "msg123"
        assert msg.type == "text"
        assert msg.from_me is False
        assert msg.text.body == "Hello"

    def test_valid_voice_message(self):
        """Test valid voice message."""
        msg = Message(
            id="msg456",
            from_me=False,
            type="voice",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            voice=VoiceContent(
                id="voice123",
                mime_type="audio/ogg",
                file_size=50000,
                sha256="abc123",
                link="https://example.com/voice",
                seconds=10
            ),
            **{"from": "1234567890"}
        )
        assert msg.type == "voice"
        assert msg.voice.seconds == 10

    def test_valid_image_message(self):
        """Test valid image message."""
        msg = Message(
            id="msg789",
            from_me=False,
            type="image",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            image=ImageContent(
                id="img123",
                mime_type="image/jpeg",
                file_size=500000,
                sha256="abc123"
            ),
            **{"from": "1234567890"}
        )
        assert msg.type == "image"
        assert msg.image.mime_type == "image/jpeg"

    def test_message_type_video(self):
        """Test message with video type."""
        msg = Message(
            id="msg_video",
            from_me=False,
            type="video",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            video={"id": "vid123", "mime_type": "video/mp4"},
            **{"from": "1234567890"}
        )
        assert msg.type == "video"
        assert msg.video["id"] == "vid123"

    def test_message_type_document(self):
        """Test message with document type."""
        msg = Message(
            id="msg_doc",
            from_me=False,
            type="document",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            document={"id": "doc123", "mime_type": "application/pdf"},
            **{"from": "1234567890"}
        )
        assert msg.type == "document"

    def test_message_type_audio(self):
        """Test message with audio type."""
        msg = Message(
            id="msg_audio",
            from_me=False,
            type="audio",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            audio={"id": "aud123", "mime_type": "audio/mpeg"},
            **{"from": "1234567890"}
        )
        assert msg.type == "audio"

    def test_message_type_short(self):
        """Test message with short (reels) type."""
        msg = Message(
            id="msg_short",
            from_me=False,
            type="short",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            short={"id": "short123", "mime_type": "video/mp4"},
            **{"from": "1234567890"}
        )
        assert msg.type == "short"

    def test_message_type_link_preview(self):
        """Test message with link_preview type."""
        msg = Message(
            id="msg_link",
            from_me=False,
            type="link_preview",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            link_preview={"body": "Check out this link!", "url": "https://example.com"},
            **{"from": "1234567890"}
        )
        assert msg.type == "link_preview"
        assert msg.link_preview["body"] == "Check out this link!"

    def test_message_from_me_agent(self):
        """Test agent message (from_me=True)."""
        msg = Message(
            id="msg_agent",
            from_me=True,
            type="text",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="api",
            text=TextContent(body="Agent response"),
            **{"from": "1234567890"}
        )
        assert msg.from_me is True
        assert msg.source == "api"

    def test_message_from_alias_serialization(self):
        """Test that 'from' field serializes correctly with alias."""
        msg = Message(
            id="msg123",
            from_me=False,
            type="text",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            text=TextContent(body="Test"),
            **{"from": "1234567890"}
        )
        # Test serialization with alias
        serialized = msg.model_dump(by_alias=True)
        assert "from" in serialized
        assert serialized["from"] == "1234567890"

    def test_message_optional_source(self):
        """Test message with None source field."""
        msg = Message(
            id="msg_no_source",
            from_me=False,
            type="text",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source=None,
            text=TextContent(body="Test"),
            **{"from": "1234567890"}
        )
        assert msg.source is None

    def test_message_optional_from_name(self):
        """Test message with and without from_name."""
        # Mobile message with from_name
        msg1 = Message(
            id="msg1",
            from_me=False,
            type="text",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            text=TextContent(body="Test"),
            from_name="John Doe",
            **{"from": "1234567890"}
        )
        assert msg1.from_name == "John Doe"

        # API message without from_name
        msg2 = Message(
            id="msg2",
            from_me=True,
            type="text",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="api",
            text=TextContent(body="Test"),
            **{"from": "1234567890"}
        )
        assert msg2.from_name is None

    def test_message_invalid_type(self):
        """Test message with invalid type (not in Literal)."""
        with pytest.raises(ValidationError) as exc_info:
            Message(
                id="msg_bad",
                from_me=False,
                type="invalid_type",  # Not in allowed types
                chat_id="1234567890@s.whatsapp.net",
                timestamp=1700000000,
                **{"from": "1234567890"}
            )
        assert "type" in str(exc_info.value)

    def test_message_missing_required_fields(self):
        """Test message missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            Message(id="msg123")
        error_str = str(exc_info.value)
        assert "from_me" in error_str or "type" in error_str


@pytest.mark.unit
class TestEvent:
    """Tests for Event model validation."""

    def test_valid_event(self):
        """Test valid event creation."""
        event = Event(type="messages", event="message")
        assert event.type == "messages"
        assert event.event == "message"

    def test_event_missing_fields(self):
        """Test event missing required fields."""
        with pytest.raises(ValidationError):
            Event(type="messages")

        with pytest.raises(ValidationError):
            Event(event="message")


@pytest.mark.unit
class TestWhapiWebhook:
    """Tests for WhapiWebhook model validation."""

    def test_valid_webhook_with_messages(self):
        """Test valid webhook with messages."""
        webhook = WhapiWebhook(
            messages=[
                Message(
                    id="msg1",
                    from_me=False,
                    type="text",
                    chat_id="1234567890@s.whatsapp.net",
                    timestamp=1700000000,
                    source="mobile",
                    text=TextContent(body="Hello"),
                    **{"from": "1234567890"}
                )
            ],
            event=Event(type="messages", event="message"),
            channel_id="channel123"
        )
        assert len(webhook.messages) == 1
        assert webhook.messages[0].text.body == "Hello"

    def test_valid_webhook_multiple_messages(self):
        """Test webhook with multiple messages."""
        webhook = WhapiWebhook(
            messages=[
                Message(
                    id="msg1",
                    from_me=False,
                    type="text",
                    chat_id="1234567890@s.whatsapp.net",
                    timestamp=1700000000,
                    source="mobile",
                    text=TextContent(body="First"),
                    **{"from": "1234567890"}
                ),
                Message(
                    id="msg2",
                    from_me=False,
                    type="text",
                    chat_id="1234567890@s.whatsapp.net",
                    timestamp=1700000001,
                    source="mobile",
                    text=TextContent(body="Second"),
                    **{"from": "1234567890"}
                )
            ],
            event=Event(type="messages", event="message"),
            channel_id="channel123"
        )
        assert len(webhook.messages) == 2
        assert webhook.messages[0].text.body == "First"
        assert webhook.messages[1].text.body == "Second"

    def test_webhook_with_statuses(self):
        """Test webhook with status updates."""
        webhook = WhapiWebhook(
            statuses=[
                {"id": "status1", "status": "delivered"},
                {"id": "status2", "status": "read"}
            ],
            event=Event(type="statuses", event="status"),
            channel_id="channel123"
        )
        assert webhook.statuses is not None
        assert len(webhook.statuses) == 2
        assert webhook.messages is None

    def test_webhook_optional_messages(self):
        """Test webhook without messages (statuses only)."""
        webhook = WhapiWebhook(
            event=Event(type="statuses", event="status"),
            channel_id="channel123"
        )
        assert webhook.messages is None
        assert webhook.statuses is None

    def test_webhook_missing_event(self):
        """Test webhook missing required event field."""
        with pytest.raises(ValidationError) as exc_info:
            WhapiWebhook(channel_id="channel123")
        assert "event" in str(exc_info.value)


@pytest.mark.unit
class TestN8nErrorWebhook:
    """Tests for N8nErrorWebhook model validation."""

    def test_valid_n8n_error_minimal(self):
        """Test N8nErrorWebhook with minimal fields."""
        error = N8nErrorWebhook()
        assert error.mode is None
        assert error.workflow is None
        assert error.error is None

    def test_valid_n8n_error_full(self):
        """Test N8nErrorWebhook with all standard fields."""
        error = N8nErrorWebhook(
            mode="production",
            workflow={"id": "workflow123", "name": "My Workflow"},
            error={"message": "Something went wrong", "code": 500},
            lastNodeExecuted="HTTP Request",
            stack="Error stack trace..."
        )
        assert error.mode == "production"
        assert error.workflow["id"] == "workflow123"
        assert error.error["message"] == "Something went wrong"
        assert error.lastNodeExecuted == "HTTP Request"

    def test_n8n_error_extra_fields_allowed(self):
        """Test N8nErrorWebhook accepts extra fields (Config extra='allow')."""
        error = N8nErrorWebhook(
            mode="test",
            custom_field_1="value1",
            custom_field_2=123,
            nested_custom={"key": "value"}
        )
        assert error.mode == "test"
        # Extra fields should be stored
        assert hasattr(error, "custom_field_1") or "custom_field_1" in error.model_dump()

    def test_n8n_error_various_formats(self):
        """Test N8nErrorWebhook with various error formats from n8n."""
        # Format 1: Simple string error
        error1 = N8nErrorWebhook(error="Simple error message")
        assert error1.error == "Simple error message"

        # Format 2: Dict error
        error2 = N8nErrorWebhook(error={"message": "Dict error", "details": "More info"})
        assert error2.error["message"] == "Dict error"

        # Format 3: List of errors
        error3 = N8nErrorWebhook(error=["Error 1", "Error 2"])
        assert len(error3.error) == 2

    def test_n8n_error_empty_payload(self):
        """Test N8nErrorWebhook accepts empty payload."""
        error = N8nErrorWebhook()
        assert error is not None
        # All fields should be None
        assert error.mode is None
        assert error.workflow is None
        assert error.error is None
        assert error.lastNodeExecuted is None
        assert error.stack is None


@pytest.mark.unit
class TestModelSerialization:
    """Tests for model serialization and round-trip conversion."""

    def test_text_content_round_trip(self):
        """Test TextContent serialization round-trip."""
        original = TextContent(body="Test message")
        serialized = original.model_dump()
        reconstructed = TextContent(**serialized)
        assert reconstructed.body == original.body

    def test_message_round_trip_with_alias(self):
        """Test Message serialization round-trip preserves 'from' alias."""
        original = Message(
            id="msg123",
            from_me=False,
            type="text",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            text=TextContent(body="Test"),
            **{"from": "1234567890"}
        )

        # Serialize with alias
        serialized = original.model_dump(by_alias=True)
        assert "from" in serialized
        assert serialized["from"] == "1234567890"

        # Reconstruct from serialized data
        reconstructed = Message(**serialized)
        assert reconstructed.from_ == original.from_

    def test_webhook_json_round_trip(self):
        """Test WhapiWebhook JSON serialization round-trip."""
        original = WhapiWebhook(
            messages=[
                Message(
                    id="msg1",
                    from_me=False,
                    type="text",
                    chat_id="1234567890@s.whatsapp.net",
                    timestamp=1700000000,
                    source="mobile",
                    text=TextContent(body="Hello"),
                    **{"from": "1234567890"}
                )
            ],
            event=Event(type="messages", event="message"),
            channel_id="channel123"
        )

        # Convert to JSON dict and back
        json_data = original.model_dump(by_alias=True)
        reconstructed = WhapiWebhook(**json_data)

        assert len(reconstructed.messages) == len(original.messages)
        assert reconstructed.messages[0].id == original.messages[0].id
        assert reconstructed.channel_id == original.channel_id

    def test_optional_fields_serialize_as_none(self):
        """Test that optional fields serialize as None when not provided."""
        msg = Message(
            id="msg123",
            from_me=False,
            type="text",
            chat_id="1234567890@s.whatsapp.net",
            timestamp=1700000000,
            source="mobile",
            text=TextContent(body="Test"),
            **{"from": "1234567890"}
        )

        serialized = msg.model_dump()
        assert serialized["voice"] is None
        assert serialized["image"] is None
        assert serialized["from_name"] is None
