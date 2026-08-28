"""Auth router.

Register/login are gone on purpose — Supabase Auth owns them now. The
frontend calls Supabase directly (`supabase.auth.signInWithOtp`, etc.);
this backend never sees a password or issues a token. All that's left
here is /me, which just echoes back the user get_current_user already
resolved from the verified Supabase token.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import User
from app.schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
