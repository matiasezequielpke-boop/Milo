"""Shared FastAPI dependencies."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.supabase_auth import InvalidSupabaseTokenError, SupabaseAuthNotConfiguredError, verify_supabase_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if credentials is None:
        raise unauthorized

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
    except (KeyError, ValueError) as exc:
        raise unauthorized from exc

    # public.users is populated by the on_auth_user_created trigger the
    # moment Supabase creates the auth.users row, so this should always
    # find a match. If it doesn't (trigger disabled, or a token from a
    # different Supabase project), treat it the same as "not
    # authenticated" rather than silently creating a row here — this
    # dependency verifies identity, it doesn't provision accounts.
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized
    return user
