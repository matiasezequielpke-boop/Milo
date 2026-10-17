"""Demo mode: sign-in-free access for exactly two demo people."""
import pytest

from tests.conftest import auth

ROSA_DEMO = "rosa@demo.warden.app"
ANA_DEMO = "ana@demo.warden.app"


def demo(email):
    return {"Authorization": f"Bearer demo:{email}"}


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    yield


async def test_demo_tokens_rejected_when_demo_mode_off(client):
    assert (await client.get("/auth/me", headers=demo(ROSA_DEMO))).status_code == 401
    assert (await client.post("/demo/bootstrap")).status_code == 404


async def test_only_the_configured_demo_people_can_sign_in(client, demo_on):
    assert (await client.get("/auth/me", headers=demo("someone@else.com"))).status_code == 401
    r = await client.get("/auth/me", headers=demo(ROSA_DEMO))
    assert r.status_code == 200 and r.json()["display_name"] == "Rosa"


async def test_bootstrap_builds_the_family_once(client, demo_on):
    first = (await client.post("/demo/bootstrap")).json()
    second = (await client.post("/demo/bootstrap")).json()
    assert first["household_id"] == second["household_id"]
    assert [p["role"] for p in first["people"]] == ["elder", "approver"]

    rosa = (await client.get("/households", headers=demo(ROSA_DEMO))).json()
    ana = (await client.get("/households", headers=demo(ANA_DEMO))).json()
    assert len(rosa) == len(ana) == 1
    assert rosa[0]["my_role"] == "elder"
    assert sorted(ana[0]["my_scopes"]) == ["approve_actions", "receive_alerts", "view_accounts"]


async def test_bootstrap_does_not_regrant_revoked_consent(client, demo_on):
    boot = (await client.post("/demo/bootstrap")).json()
    hid = boot["household_id"]
    household = (await client.get(f"/households/{hid}", headers=demo(ROSA_DEMO))).json()
    ana_member = next(m for m in household["members"] if m["role"] == "approver")
    await client.post(f"/households/{hid}/consents/{ana_member['id']}/revoke", headers=demo(ROSA_DEMO))
    await client.post("/demo/bootstrap")
    ana = (await client.get(f"/households/{hid}", headers=demo(ANA_DEMO))).json()
    assert ana["my_scopes"] == []


async def test_dev_tokens_still_work_alongside_demo(client, demo_on):
    assert (await client.get("/auth/me", headers=auth("dev@example.com"))).status_code == 200


def test_demo_mode_refuses_to_boot_with_live_money(monkeypatch):
    import importlib

    import app.main

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_nope")
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        importlib.reload(app.main)
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    monkeypatch.delenv("DEMO_MODE")
    get_settings.cache_clear()
    importlib.reload(app.main)
