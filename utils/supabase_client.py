"""Supabase client singleton."""
from supabase import create_client, Client
from utils.config import settings


class SupabaseClient:
    """Singleton Supabase client."""

    _instance: Client | None = None

    @classmethod
    def get_client(cls) -> Client:
        """Get or create Supabase client instance."""
        if cls._instance is None:
            cls._instance = create_client(
                settings.supabase_url,
                settings.supabase_key
            )
        return cls._instance


# Helper function for easy access
def get_supabase() -> Client:
    """Get Supabase client instance."""
    return SupabaseClient.get_client()
