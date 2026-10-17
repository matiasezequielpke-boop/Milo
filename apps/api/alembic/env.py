"""Async Alembic env.py — runs migrations through the same asyncpg engine
the app itself uses (see app/db.py), so there's no second DB driver
(psycopg2) to install just for migrations.

The DB URL comes from app.config.get_settings() (i.e. the same .env the
app reads), not from alembic.ini — one source of truth, no drift between
"the URL the app connects with" and "the URL migrations run against".
"""
import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool

# Make `app` importable regardless of the cwd alembic was invoked from —
# alembic.ini and this file both live at apps/api/, so that's the root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

from app.config import get_settings
from app.db import engine_options
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# Same URL handling as the app (Supabase's pooled URL included).
_url, _options = engine_options(get_settings().database_url)
_options.pop("pool_recycle", None)
_options["poolclass"] = pool.NullPool
config.set_main_option("sqlalchemy.url", _url.render_as_string(hide_password=False).replace("%", "%%"))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(_url, **_options)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
