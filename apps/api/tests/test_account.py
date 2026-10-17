"""Privacy rights and email hygiene: export, deletion, unsubscribe."""
import json

import httpx
import pytest
import respx

from app import plaid_service
from tests.conftest import ANA, ROSA, auth
from tests.test_banking_and_agent import fake_plaid  # noqa: F401 — fixture


@pytest.fixture
def removed_items(monkeypatch):
    removed = []

    async def remove_item(access_token):
        removed.append(access_token)

    monkeypatch.setattr(plaid_service, "remove_item", remove_item)
    return removed


async def _connect_bank(client, family):
    hid = family["household_id"]
    r = await client.post(f"/households/{hid}/plaid/exchange", json={"public_token": "public-sandbox-abc"}, headers=auth(ANA))
    assert r.status_code == 201, r.text


async def test_owner_export_has_the_household_data(client, family, fake_plaid):  # noqa: F811
    await _connect_bank(client, family)
    r = await client.get("/me/export", headers=auth(ROSA))
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    household = data["households"][0]
    assert household["my_membership"]["role"] == "elder"
    assert len(household["transactions"]) == 11
    assert household["alerts"]
    # Internals never leave the server.
    text = json.dumps(data)
    assert "invite_token_hash" not in text and "access-sandbox-secret" not in text and "encrypted_value" not in text


async def test_approver_export_is_only_their_part(client, family, fake_plaid):  # noqa: F811
    await _connect_bank(client, family)
    data = (await client.get("/me/export", headers=auth(ANA))).json()
    household = data["households"][0]
    assert household["my_membership"]["role"] == "approver"
    assert "transactions" not in household
    assert household["consents_given_to_me"]


async def test_approver_deleting_their_account_leaves_the_owner_household(client, family, fake_plaid, removed_items):  # noqa: F811
    await _connect_bank(client, family)
    hid = family["household_id"]
    await client.post("/conversations", json={"household_id": hid, "title": "Ana's chat"}, headers=auth(ANA))

    r = await client.request("DELETE", "/me", json={"confirm": "DELETE"}, headers=auth(ANA))
    assert r.status_code == 200, r.text
    assert removed_items == []  # Rosa's bank stays connected

    household = (await client.get(f"/households/{hid}", headers=auth(ROSA))).json()
    assert [m["role"] for m in household["members"]] == ["elder"]
    assert all(c["revoked_at"] for c in household["consents"])
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import HouseholdMember

    async with SessionLocal() as db:
        ana = (await db.execute(select(HouseholdMember).where(HouseholdMember.role == "approver"))).scalar_one()
    assert ana.status.value == "removed" and ana.user_id is None and ANA not in ana.email
    # Rosa still sees her money (the bank link moved to her).
    assert (await client.get(f"/households/{hid}/accounts", headers=auth(ROSA))).json()
    activity = (await client.get(f"/households/{hid}/audit", headers=auth(ROSA))).json()
    assert any(e["event_type"] == "household.member_deleted_account" for e in activity)


async def test_owner_deleting_their_account_closes_the_household(client, family, fake_plaid, removed_items):  # noqa: F811
    await _connect_bank(client, family)
    hid = family["household_id"]
    r = await client.request("DELETE", "/me", json={"confirm": "DELETE"}, headers=auth(ROSA))
    assert r.status_code == 200, r.text
    assert r.json()["problems"] == []
    assert removed_items == ["access-sandbox-secret"]  # access revoked at Plaid
    assert (await client.get("/households", headers=auth(ANA))).json() == []
    assert (await client.get(f"/households/{hid}", headers=auth(ANA))).status_code == 404


async def test_deletion_needs_the_typed_confirmation(client, family):
    r = await client.request("DELETE", "/me", json={"confirm": "yes"}, headers=auth(ROSA))
    assert r.status_code == 422


async def test_unsubscribe_link_and_settings(client, family):
    from app import notify

    me = (await client.get("/auth/me", headers=auth(ANA))).json()
    import uuid

    token = notify.unsubscribe_token(uuid.UUID(me["id"]))
    assert (await client.post("/email/unsubscribe", params={"token": token + "x"})).status_code == 404
    assert (await client.post("/email/unsubscribe", params={"token": token})).status_code == 200
    assert (await client.get("/auth/me", headers=auth(ANA))).json()["email_opt_out_at"]

    r = await client.put("/me/notifications", json={"email_notifications": True}, headers=auth(ANA))
    assert r.json()["email_opt_out_at"] is None


async def test_notification_emails_skip_opted_out_people_and_carry_unsubscribe(client, family, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("PUBLIC_API_URL", "https://api.example.com")
    from app import notify
    from app.config import get_settings

    get_settings.cache_clear()
    await client.put("/me/notifications", json={"email_notifications": False}, headers=auth(ROSA))
    with respx.mock(assert_all_called=False) as router:
        sent = router.post("https://api.resend.com/emails").mock(return_value=httpx.Response(200, json={"id": "x"}))
        delivered = await notify.notify_people([ANA, ROSA], "Warden needs your OK", "Pay $10 to ConEd", link="https://app/x")
    assert delivered is True
    assert sent.call_count == 1  # Rosa opted out
    payload = json.loads(sent.calls[0].request.content)
    assert payload["to"] == [ANA]
    assert "unsubscribe?token=" in payload["text"]
    assert payload["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert payload["headers"]["List-Unsubscribe"].startswith("<https://api.example.com/email/unsubscribe?token=")


async def test_demo_family_cannot_be_deleted(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    await client.post("/demo/bootstrap")
    r = await client.request(
        "DELETE", "/me", json={"confirm": "DELETE"}, headers={"Authorization": "Bearer demo:rosa@demo.warden.app"}
    )
    assert r.status_code == 403
