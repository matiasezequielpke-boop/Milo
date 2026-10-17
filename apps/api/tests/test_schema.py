"""Every table has row level security on (see the f4d1a9c3e822 migration):
on Supabase, a table without it is readable and writable through the
project's public REST API by anyone holding the anon key."""
from sqlalchemy import text

from app.db import engine


async def test_every_table_has_row_level_security():
    async with engine.connect() as conn:
        open_tables = (
            await conn.execute(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' AND NOT c.relrowsecurity"
                )
            )
        ).scalars().all()
    assert open_tables == []


def test_supabase_pooler_url_is_adapted_for_asyncpg():
    from app.db import engine_options

    url, options = engine_options(
        "postgres://postgres.ref:pw@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require&supa=base-pooler.x"
    )
    assert url.drivername == "postgresql+asyncpg"
    assert dict(url.query) == {"prepared_statement_cache_size": "0"}
    args = options["connect_args"]
    assert args["ssl"] == "require" and args["statement_cache_size"] == 0
    assert args["prepared_statement_name_func"]() != args["prepared_statement_name_func"]()

    url, options = engine_options("postgresql://milo:milo@localhost:5432/milo")
    assert url.drivername == "postgresql+asyncpg" and options["connect_args"] == {}
