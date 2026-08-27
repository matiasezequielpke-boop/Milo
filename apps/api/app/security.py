"""Password hashing and JWT issuance for the email/password auth flow.

No external auth provider (Auth0, Clerk, etc.) — those cost money and
Fase 0 budget is deferred. This is a plain, self-hosted JWT scheme:
bcrypt for passwords, HS256 signed with app_secret_key for tokens.
Swapping in a managed provider later doesn't touch anything downstream
of `get_current_user`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
    return uuid.UUID(payload["sub"])
