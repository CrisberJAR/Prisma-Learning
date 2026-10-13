from functools import lru_cache

from supabase import Client, create_client

from config import settings


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """Cliente con anon key: respeta RLS. Usar en peticiones de usuario."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """Cliente con service key: salta RLS. Solo servidor y jobs, nunca al navegador."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


def user_client(access_token: str) -> Client:
    """Cliente anon que actúa como el usuario autenticado, para que RLS aplique sus permisos."""
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.postgrest.auth(access_token)
    return client
