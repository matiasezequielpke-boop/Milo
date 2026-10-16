"""Test setup: a real Postgres (TEST_DATABASE_URL, default the local
milo_test DB), migrated with Alembic once per run and truncated between
tests. Dev auth is on so tests can act as different family members with
`Authorization: Bearer dev:<email>`.

External providers (Stripe, Plaid, Anthropic) are replaced with fakes in
individual tests — the only place fakes exist in this codebase.
"""
import os
import subprocess
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql://milo:milo@localhost:5432/milo_test")
os.environ["APP_ENV"] = "development"
os.environ["DEV_AUTH_ENABLED"] = "true"
for key in ("ANTHROPIC_API_KEY", "PLAID_CLIENT_ID", "PLAID_SECRET", "STRIPE_SECRET_KEY", "RESEND_API_KEY", "NTFY_TOPIC"):
    os.environ.pop(key, None)

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    env = {**os.environ}
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], cwd=API_ROOT, env=env, check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_ROOT, env=env, check=True, capture_output=True)
    yield


@pytest.fixture(autouse=True)
def fresh_settings():
    """Settings are cached; a test that monkeypatches env vars must not leak
    a cached copy into the next test (monkeypatch restores the env only
    after the test's own teardown has run)."""
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def clean_tables(migrated_db):
    from app.db import engine
    from app.models import Base

    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def client():
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def auth(email: str) -> dict:
    return {"Authorization": f"Bearer dev:{email}"}


ANA = "ana@example.com"      # the adult child — approver
ROSA = "rosa@example.com"    # her mother — the account owner


@pytest.fixture
async def family(client):
    """Ana sets Warden up for her mother Rosa; Rosa joins and consents."""
    r = await client.post(
        "/households",
        json={
            "name": "Rosa's accounts",
            "my_role": "approver",
            "my_display_name": "Ana",
            "invite": {"email": ROSA, "display_name": "Rosa", "role": "elder"},
        },
        headers=auth(ANA),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    household_id = body["household"]["id"]
    ana_member_id = body["household"]["my_member_id"]
    token = body["invite"]["invite_link"].rsplit("/", 1)[1]

    r = await client.post("/households/invites/accept", json={"token": token}, headers=auth(ROSA))
    assert r.status_code == 200, r.text

    r = await client.post(
        f"/households/{household_id}/consents",
        json={"approver_member_id": ana_member_id, "scopes": ["view_accounts", "receive_alerts", "approve_actions"]},
        headers=auth(ROSA),
    )
    assert r.status_code == 201, r.text
    return {"household_id": household_id, "ana_member_id": ana_member_id}
