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
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _async_database_url() -> str:
    url = get_settings().database_url
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


config.set_main_option("sqlalchemy.url", _async_database_url())


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
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
