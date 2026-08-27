"""Async SQLAlchemy engine + session factory.

`Settings.database_url` is written the plain `postgresql://` way in
.env.example so it also works as a psql/Alembic-style DSN; this module
rewrites it to the asyncpg driver for the app's own async engine.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings


def _async_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


settings = get_settings()
# Note: pool_pre_ping is deliberately NOT set here. With this SQLAlchemy
# version + asyncpg, a ping-triggered reconnect after a rollback can hit
# `MissingGreenlet` (the ping runs outside the async bridge's greenlet
# context) — confirmed locally, not a hypothetical. pool_recycle bounds
# staleness instead without that failure mode.
engine = create_async_engine(_async_url(settings.database_url), pool_recycle=1800)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
