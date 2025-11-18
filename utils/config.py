"""Configuration management using pydantic-settings."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Supabase
    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_key: str = Field(..., alias="SUPABASE_KEY")

    # Whapi
    whapi_token: str = Field(..., alias="WHAPI_TOKEN")
    whapi_api_url: str = Field(default="https://gate.whapi.cloud", alias="WHAPI_API_URL")

    # OpenAI
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    # OpenAI Models
    openai_pdf_model: str = Field(default="gpt-5.1-2025-11-13", alias="OPENAI_PDF_MODEL")
    openai_session_model: str = Field(default="gpt-5-mini-2025-08-07", alias="OPENAI_SESSION_MODEL")
    openai_transcription_model: str = Field(default="whisper-1", alias="OPENAI_TRANSCRIPTION_MODEL")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")

    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Supabase Storage
    media_bucket_name: str = Field(default="whatsapp-media")

    # n8n Webhook
    n8n_webhook_url: str = Field(..., alias="N8N_WEBHOOK_URL")
    n8n_webhook_api_key: str = Field(..., alias="N8N_WEBHOOK_API_KEY")
    n8n_batch_delay_seconds: int = Field(default=60, alias="N8N_BATCH_DELAY_SECONDS")

    # Session Detection Configuration
    session_timeout_hours: int = Field(default=24, alias="SESSION_TIMEOUT_HOURS")
    session_recent_messages_limit: int = Field(default=20, alias="SESSION_RECENT_MESSAGES_LIMIT")
    session_detection_max_tokens: int = Field(default=10, alias="SESSION_DETECTION_MAX_TOKENS")
    # Note: temperature not configurable - gpt-5-mini models only support default (1.0)

    # Presence Configuration
    presence_typing_min_seconds: int = Field(default=13, alias="PRESENCE_TYPING_MIN_SECONDS")
    presence_typing_max_seconds: int = Field(default=18, alias="PRESENCE_TYPING_MAX_SECONDS")

    # File Upload Limits
    max_file_size_mb: int = Field(default=50, alias="MAX_FILE_SIZE_MB")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
