from __future__ import annotations


def supabase_admin_headers(key: str) -> dict[str, str]:
    """Build API headers for current secret keys and legacy service-role JWTs.

    Supabase ``sb_secret_*`` values are API keys, not JWTs, and must not be put
    in an Authorization Bearer header. Legacy service-role keys still require
    that header for PostgREST and Storage compatibility.
    """
    normalized = key.strip()
    headers = {"apikey": normalized}
    if not normalized.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {normalized}"
    return headers
