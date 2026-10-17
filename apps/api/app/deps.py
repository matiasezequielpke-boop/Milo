"""Shared FastAPI dependencies."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import AuthSession, User
from app.supabase_auth import (
    InvalidSupabaseTokenError,
    SupabaseAuthNotConfiguredError,
    token_claims,
    verify_supabase_token,
)

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if credentials is None:
        raise unauthorized

    if credentials.credentials.startswith("dev:"):
        return await _dev_user(credentials.credentials.removeprefix("dev:"), db, unauthorized)
    if credentials.credentials.startswith("demo:"):
        return await _demo_user(credentials.credentials.removeprefix("demo:"), db, unauthorized)

    try:
        supabase_user = await verify_supabase_token(credentials.credentials)
    except SupabaseAuthNotConfiguredError as exc:
        # A 503, not a 401 — the token might be perfectly valid, the app
        # just can't check it yet. Distinguishing these matters: a 401
        # here would look like a bad login when it's actually a missing
        # SUPABASE_URL/SUPABASE_ANON_KEY in this deployment's env.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth is not configured on this server yet"
        ) from exc
    except InvalidSupabaseTokenError as exc:
        raise unauthorized from exc

    try:
        user_id = uuid.UUID(supabase_user["id"])
        session_id = uuid.UUID(token_claims(credentials.credentials)["session_id"])
    except (KeyError, ValueError, InvalidSupabaseTokenError) as exc:
        raise unauthorized from exc

    # A valid Supabase token isn't enough on its own: its session must have
    # been opened through this API (sign-up, or password + emailed code —
    # see app/routers/auth.py). Anything else, including a session signed
    # out here, is refused.
    recorded = await db.get(AuthSession, session_id)
    if recorded is None or recorded.revoked_at is not None or recorded.user_id != user_id:
        raise unauthorized

    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


async def _dev_user(email: str, db: AsyncSession, unauthorized: HTTPException) -> User:
    """`Bearer dev:<email>` — local development only. Lets the whole family
    flow (two people, two roles) run on a laptop or CI without a reachable
    Supabase project. app/main.py refuses to start with DEV_AUTH_ENABLED
    outside APP_ENV=development, and this re-checks both on every call."""
    settings = get_settings()
    if not (settings.dev_auth_enabled and settings.app_env == "development"):
        raise unauthorized
    email = email.strip().lower()
    if "@" not in email:
        raise unauthorized
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, display_name=email.split("@")[0].title())
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def _demo_user(email: str, db: AsyncSession, unauthorized: HTTPException) -> User:
    """`Bearer demo:<email>` — only with DEMO_MODE on, and only for the two
    configured demo people. Anyone can act as them, which is the point of a
    sign-in-free demo and why demo mode can't coexist with real money."""
    settings = get_settings()
    email = email.strip().lower()
    people = settings.demo_people
    if not settings.demo_mode or email not in people:
        raise unauthorized
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, display_name=people[email][0])
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user
