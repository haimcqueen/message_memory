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

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")

    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Supabase Storage
    media_bucket_name: str = Field(default="whatsapp-media")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
