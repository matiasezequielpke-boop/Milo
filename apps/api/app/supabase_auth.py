"""Verifies Supabase-issued access tokens. Replaces app/security.py.

Identity moved to Supabase Auth (see claude/ruta-a-produccion.md): the
frontend talks to Supabase directly for email OTP sign-in and holds the
resulting access token. This module's only job is to answer "is this
token real, and whose is it" — it never issues one.

Verification goes through Supabase's own /auth/v1/user endpoint instead
of checking the JWT signature locally. That costs one extra network
round-trip per request, but it needs no shared secret this codebase
would otherwise have to store and rotate, and it stays correct
regardless of whether the project signs tokens with the legacy shared
secret (HS256) or newer per-project signing keys (ES256) — Supabase can
change that without this code changing. If request latency ever
matters enough to justify it, swap this for local verification against
Supabase's JWKS endpoint (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`)
without touching anything downstream of `verify_supabase_token`.
"""
from __future__ import annotations

import httpx

from app.config import get_settings


class SupabaseAuthNotConfiguredError(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_ANON_KEY aren't set yet."""


class InvalidSupabaseTokenError(RuntimeError):
    """Raised when Supabase rejects the token (expired, malformed, revoked)."""


async def verify_supabase_token(access_token: str) -> dict:
    """Returns the Supabase auth user record ({"id", "email", ...}) for a
    valid access token, or raises. Never caches — a revoked or expired
    token must fail on the very next call.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise SupabaseAuthNotConfiguredError(
            "SUPABASE_URL / SUPABASE_ANON_KEY not set — see .env.example. "
            "Auth cannot work at all until these point at your project."
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "apikey": settings.supabase_anon_key,
            },
        )

    if response.status_code != 200:
        raise InvalidSupabaseTokenError(f"Supabase rejected the token (status {response.status_code})")

    return response.json()
