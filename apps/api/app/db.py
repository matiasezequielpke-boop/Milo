"""Async SQLAlchemy engine + session factory.

`Settings.database_url` is written the plain `postgresql://` way in
.env.example so it also works as a psql/Alembic-style DSN; this module
rewrites it to the asyncpg driver for the app's own async engine.

Hosted on Vercel with Supabase, the URL is Supabase's pooled connection
string (`postgres://…pooler.supabase.com:6543/…?sslmode=require`). Its
transaction pooler can't keep prepared statements between queries, so
those are turned off for it, and each serverless instance opens a
connection per request instead of holding a pool.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings


def _async_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    for prefix in ("postgresql://", "postgres://"):
        if database_url.startswith(prefix):
            return database_url.replace(prefix, "postgresql+asyncpg://", 1)
    return database_url


def engine_options(database_url: str) -> tuple[URL, dict]:
    """The asyncpg URL plus create_async_engine() options for it."""
    url = make_url(_async_url(database_url))
    query = dict(url.query)
    connect_args: dict = {}
    # libpq-style options asyncpg doesn't take as keywords.
    sslmode = query.pop("sslmode", None)
    for key in ("supa", "pgbouncer", "connect_timeout"):
        query.pop(key, None)
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = sslmode
    if url.port == 6543 or (url.host or "").endswith("pooler.supabase.com"):
        query["prepared_statement_cache_size"] = "0"
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid.uuid4()}__"
    options: dict = {"connect_args": connect_args}
    if os.environ.get("VERCEL"):
        options["poolclass"] = NullPool
    else:
        options["pool_recycle"] = 1800
    return url.set(query=query), options


settings = get_settings()
# Note: pool_pre_ping is deliberately NOT set here. With this SQLAlchemy
# version + asyncpg, a ping-triggered reconnect after a rollback can hit
# `MissingGreenlet` (the ping runs outside the async bridge's greenlet
# context) — confirmed locally, not a hypothetical. pool_recycle bounds
# staleness instead without that failure mode.
_url, _options = engine_options(settings.database_url)
engine = create_async_engine(_url, **_options)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
