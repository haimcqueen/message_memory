"""Pydantic models for Whapi webhook payloads."""
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any


class TextContent(BaseModel):
    """Text message content."""
    body: str


class VoiceContent(BaseModel):
    """Voice message content."""
    id: str
    mime_type: str
    file_size: int
    sha256: str
    link: str
    seconds: int


class ImageContent(BaseModel):
    """Image message content."""
    id: str
    mime_type: str
    file_size: int
    sha256: str
    link: Optional[str] = None  # Link may not be present initially
    caption: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    preview: Optional[str] = None  # Base64 preview image


class Message(BaseModel):
    """WhatsApp message from webhook."""
    id: str
    from_me: bool
    type: Literal["text", "voice", "image", "video", "document", "audio", "short", "link_preview"]
    chat_id: str
    timestamp: int
    source: Optional[str] # Usually "api" or "mobile", but optional for robustness
    text: Optional[TextContent] = None
    voice: Optional[VoiceContent] = None
    image: Optional[ImageContent] = None
    video: Optional[dict] = None  # Video content
    document: Optional[dict] = None  # Document content
    audio: Optional[dict] = None  # Audio content
    short: Optional[dict] = None  # Short video content (WhatsApp reels)
    link_preview: Optional[dict] = None  # Link preview content
    from_: str = Field(alias="from")
    from_name: Optional[str] = None  # Not present in API-sent messages


class Event(BaseModel):
    """Webhook event metadata."""
    type: str
    event: str


class WhapiWebhook(BaseModel):
    """Complete Whapi webhook payload."""
    messages: Optional[list[Message]] = None
    event: Event
    channel_id: str

    # For status updates (delivered, read, etc.)
    statuses: Optional[list[dict]] = None


class N8nErrorWebhook(BaseModel):
    """n8n error webhook payload - accepts any error format from n8n."""
    mode: Optional[Any] = None
    workflow: Optional[Any] = None
    error: Optional[Any] = None
    lastNodeExecuted: Optional[Any] = None
    stack: Optional[Any] = None
    # Accept any additional fields n8n might send
    class Config:
        extra = "allow"
