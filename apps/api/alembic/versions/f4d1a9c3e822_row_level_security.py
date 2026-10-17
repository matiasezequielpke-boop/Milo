"""row level security on every table

Supabase serves the `public` schema over its REST API, where the anon key
(public by design) would otherwise read and write these tables directly.
With RLS on and no policies, that API sees nothing; Warden's own API
connects as the table owner, which RLS doesn't restrict. Any table added
later must turn RLS on too (tests/test_schema.py checks).

Revision ID: f4d1a9c3e822
Revises: e3c8f5a2b711
Create Date: 2026-10-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4d1a9c3e822'
down_revision: Union[str, None] = 'e3c8f5a2b711'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _all_tables(action: str) -> str:
    return f"""
    DO $$
    DECLARE t record;
    BEGIN
      FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I {action} ROW LEVEL SECURITY', t.tablename);
      END LOOP;
    END $$;
    """


def upgrade() -> None:
    op.execute(_all_tables("ENABLE"))


def downgrade() -> None:
    op.execute(_all_tables("DISABLE"))
