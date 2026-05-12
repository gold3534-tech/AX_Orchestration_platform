import os

from supabase import Client, create_client

_client: Client | None = None


def get_supabase() -> Client | None:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return None
        _client = create_client(url, key)
    return _client
