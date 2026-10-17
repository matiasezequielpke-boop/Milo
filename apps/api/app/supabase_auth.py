"""Talks to Supabase Auth (GoTrue) over its REST API.

Supabase owns the credentials: passwords are checked and stored there,
and the sign-in codes are emailed by Supabase. This API is the gate in
front of it — sign-up and both login steps go through here so that a
session only counts once the whole flow has run (see app/routers/auth.py
and `AuthSession` in app/models.py). The password passes through this
server on its way to Supabase; it is never stored or logged here.

Token verification goes through Supabase's own /auth/v1/user endpoint
instead of checking the JWT signature locally. That costs one extra
network round-trip per request, but it needs no shared secret this
codebase would otherwise have to store and rotate, and it stays correct
whether the project signs tokens with the legacy shared secret (HS256) or
newer per-project signing keys (ES256). It also fails for a signed-out
session straight away.
"""
from __future__ import annotations

import base64
import json

import httpx

from app.config import get_settings


class SupabaseAuthNotConfiguredError(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_ANON_KEY aren't set yet."""


class InvalidSupabaseTokenError(RuntimeError):
    """Raised when Supabase rejects the token (expired, malformed, revoked)."""


class SupabaseAuthError(RuntimeError):
    """Supabase answered with an error. `status` is its HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _base(service: bool = False) -> tuple[str, dict[str, str]]:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise SupabaseAuthNotConfiguredError(
            "SUPABASE_URL / SUPABASE_ANON_KEY not set — see .env.example. "
            "Auth cannot work at all until these point at your project."
        )
    key = settings.supabase_anon_key
    if service:
        if not settings.supabase_service_role_key:
            raise SupabaseAuthNotConfiguredError("SUPABASE_SERVICE_ROLE_KEY not set.")
        key = settings.supabase_service_role_key
    headers = {"apikey": key, "Content-Type": "application/json"}
    # A legacy service_role key is a JWT and goes in Authorization too; the
    # newer sb_secret_ keys are only accepted as `apikey`.
    if service and not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return f"{settings.supabase_url.rstrip('/')}/auth/v1", headers


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"Supabase error {response.status_code}"
    return str(body.get("msg") or body.get("error_description") or body.get("message") or body.get("error") or body)


async def _post(path: str, body: dict | None, *, service: bool = False, token: str | None = None) -> dict:
    base, headers = _base(service)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(f"{base}{path}", headers=headers, json=body or {})
    if response.status_code >= 400:
        raise SupabaseAuthError(response.status_code, _message(response))
    return response.json() if response.content else {}


async def verify_supabase_token(access_token: str) -> dict:
    """Returns the Supabase auth user record ({"id", "email", ...}) for a
    valid access token, or raises. Never caches — a revoked or expired
    token must fail on the very next call."""
    base, headers = _base()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{base}/user", headers={**headers, "Authorization": f"Bearer {access_token}"})
    if response.status_code != 200:
        raise InvalidSupabaseTokenError(f"Supabase rejected the token (status {response.status_code})")
    return response.json()


def token_claims(access_token: str) -> dict:
    """The JWT payload, decoded without checking the signature. Only call
    this on a token Supabase has just accepted (verify_supabase_token or a
    token Supabase itself returned)."""
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError) as exc:
        raise InvalidSupabaseTokenError("Malformed access token") from exc


async def password_grant(email: str, password: str) -> dict:
    """Checks the password. Returns a Supabase session (the caller decides
    whether the browser ever sees it)."""
    return await _post("/token?grant_type=password", {"email": email, "password": password})


async def refresh_session(refresh_token: str) -> dict:
    return await _post("/token?grant_type=refresh_token", {"refresh_token": refresh_token})


async def sign_out(access_token: str) -> None:
    """Ends that one session at Supabase (scope=local)."""
    await _post("/logout?scope=local", None, token=access_token)


async def send_email_code(email: str) -> None:
    """Supabase emails a one-time code to an existing account. The email
    uses the project's "Magic Link" template, which must include
    {{ .Token }} for the code to appear (see docs/auth-setup.md)."""
    await _post("/otp", {"email": email, "create_user": False})


async def verify_email_code(email: str, code: str) -> dict:
    return await _post("/verify", {"type": "email", "email": email, "token": code})


async def create_confirmed_user(email: str, password: str) -> dict:
    """Admin API (service role): the account is usable at once, without a
    confirmation email — the login step verifies the email every time."""
    return await _post("/admin/users", {"email": email, "password": password, "email_confirm": True}, service=True)


async def sign_up(email: str, password: str) -> dict:
    """Public sign-up, used when no service role key is configured. Returns
    a session only if "Confirm email" is off in the Supabase project."""
    return await _post("/signup", {"email": email, "password": password})


async def delete_user(user_id: str) -> None:
    base, headers = _base(service=True)
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.delete(f"{base}/admin/users/{user_id}", headers=headers)
    if response.status_code >= 400 and response.status_code != 404:
        raise SupabaseAuthError(response.status_code, _message(response))
