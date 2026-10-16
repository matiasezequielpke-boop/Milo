"""The family flow end to end over HTTP: consent, the approval gate, the
executor, fraud blocking, and the shared audit log."""
from types import SimpleNamespace

import pytest

from tests.conftest import ANA, ROSA, auth


async def _household(client, email=ANA):
    r = await client.post(
        "/households",
        json={
            "name": "Rosa's accounts",
            "my_role": "approver",
            "my_display_name": "Ana",
            "invite": {"email": ROSA, "display_name": "Rosa", "role": "elder"},
        },
        headers=auth(email),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_invite_link_returned_when_email_is_not_configured(client):
    body = await _household(client)
    assert body["invite"]["emailed"] is False
    assert "/invite/" in body["invite"]["invite_link"]
    assert body["household"]["my_role"] == "approver"
    assert body["household"]["my_scopes"] == []


async def test_invite_must_be_accepted_by_the_invited_email(client):
    body = await _household(client)
    token = body["invite"]["invite_link"].rsplit("/", 1)[1]
    r = await client.post("/households/invites/accept", json={"token": token}, headers=auth("someone@else.com"))
    assert r.status_code == 403
    preview = await client.get(f"/households/invites/{token}")
    assert preview.json() == {
        "household_name": "Rosa's accounts",
        "invited_email": ROSA,
        "display_name": "Rosa",
        "role": "elder",
    }


async def test_approver_sees_nothing_until_the_elder_consents(client):
    body = await _household(client)
    hid = body["household"]["id"]
    token = body["invite"]["invite_link"].rsplit("/", 1)[1]
    await client.post("/households/invites/accept", json={"token": token}, headers=auth(ROSA))

    assert (await client.get(f"/households/{hid}/accounts", headers=auth(ANA))).status_code == 403
    assert (await client.get(f"/households/{hid}/audit", headers=auth(ANA))).status_code == 403
    assert (await client.get(f"/households/{hid}/accounts", headers=auth(ROSA))).status_code == 200

    # Only the elder can grant consent.
    r = await client.post(
        f"/households/{hid}/consents",
        json={"approver_member_id": body["household"]["my_member_id"], "scopes": ["view_accounts"]},
        headers=auth(ANA),
    )
    assert r.status_code == 403


async def test_consent_can_be_revoked(client, family):
    hid = family["household_id"]
    assert (await client.get(f"/households/{hid}/accounts", headers=auth(ANA))).status_code == 200
    r = await client.post(f"/households/{hid}/consents/{family['ana_member_id']}/revoke", headers=auth(ROSA))
    assert r.status_code == 200
    assert (await client.get(f"/households/{hid}/accounts", headers=auth(ANA))).status_code == 403


async def test_non_members_get_404(client, family):
    r = await client.get(f"/households/{family['household_id']}", headers=auth("stranger@example.com"))
    assert r.status_code == 404


@pytest.fixture
def fake_stripe(monkeypatch):
    """Replaces only the network call; everything around it is real."""
    calls = []

    class FakePaymentIntents:
        def create(self, params, options=None):
            calls.append((params, options))
            return SimpleNamespace(id="pi_test_123", status="succeeded", livemode=False)

    class FakeClient:
        def __init__(self, key):
            self.v1 = SimpleNamespace(payment_intents=FakePaymentIntents())

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.executor.stripe.StripeClient", FakeClient)
    yield calls
    get_settings.cache_clear()


async def _bill(client, hid, who=ROSA, payee="ConEd", amount="84.20"):
    r = await client.post(
        f"/households/{hid}/bills",
        json={"payee_name": payee, "amount": amount, "due_date": "2026-10-30", "reference": "acct 4412"},
        headers=auth(who),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_bill_payment_runs_only_after_approver_approves(client, family, fake_stripe):
    hid = family["household_id"]
    bill = await _bill(client, hid)

    r = await client.post(f"/households/{hid}/bills/{bill['id']}/request-payment", headers=auth(ROSA))
    assert r.status_code == 201, r.text
    approval = r.json()
    assert approval["status"] == "pending"
    assert approval["summary"].startswith("Pay $84.20 to ConEd")
    assert fake_stripe == []  # nothing moved yet

    # Asking twice doesn't create a second request.
    again = await client.post(f"/households/{hid}/bills/{bill['id']}/request-payment", headers=auth(ROSA))
    assert again.json()["id"] == approval["id"]

    # The elder can't approve her own payment...
    r = await client.post(f"/approvals/{approval['id']}/approve", headers=auth(ROSA))
    assert r.status_code == 403
    assert fake_stripe == []

    # ...the authorized approver can.
    r = await client.post(f"/approvals/{approval['id']}/approve", headers=auth(ANA))
    assert r.status_code == 200, r.text
    resolved = r.json()
    assert resolved["status"] == "approved"
    assert resolved["execution_result"]["status"] == "succeeded"
    assert resolved["execution_result"]["stripe_payment_intent"] == "pi_test_123"

    [(params, options)] = fake_stripe
    assert params["amount"] == 8420
    assert params["currency"] == "usd"
    assert options == {"idempotency_key": f"warden-approval-{approval['id']}"}

    bills = (await client.get(f"/households/{hid}/bills", headers=auth(ROSA))).json()
    assert bills[0]["status"] == "paid"

    # Can't approve twice.
    assert (await client.post(f"/approvals/{approval['id']}/approve", headers=auth(ANA))).status_code == 409

    events = [e["event_type"] for e in (await client.get(f"/households/{hid}/audit", headers=auth(ROSA))).json()]
    for expected in ("bill.recorded", "approval.requested", "approval.approved", "payment.succeeded"):
        assert expected in events


async def test_elder_can_block_a_request(client, family, fake_stripe):
    hid = family["household_id"]
    bill = await _bill(client, hid, who=ANA)
    approval = (await client.post(f"/households/{hid}/bills/{bill['id']}/request-payment", headers=auth(ANA))).json()

    r = await client.post(f"/approvals/{approval['id']}/deny", json={"note": "I didn't ask for this"}, headers=auth(ROSA))
    assert r.status_code == 200
    assert r.json()["status"] == "denied"
    assert fake_stripe == []
    bills = (await client.get(f"/households/{hid}/bills", headers=auth(ROSA))).json()
    assert bills[0]["status"] == "open"


async def test_approver_without_approve_scope_cannot_approve(client, family, fake_stripe):
    hid = family["household_id"]
    await client.post(
        f"/households/{hid}/consents",
        json={"approver_member_id": family["ana_member_id"], "scopes": ["view_accounts"]},
        headers=auth(ROSA),
    )
    bill = await _bill(client, hid)
    approval = (await client.post(f"/households/{hid}/bills/{bill['id']}/request-payment", headers=auth(ROSA))).json()
    r = await client.post(f"/approvals/{approval['id']}/approve", headers=auth(ANA))
    assert r.status_code == 403
    assert fake_stripe == []


async def test_payment_without_stripe_key_fails_cleanly(client, family):
    hid = family["household_id"]
    bill = await _bill(client, hid)
    approval = (await client.post(f"/households/{hid}/bills/{bill['id']}/request-payment", headers=auth(ROSA))).json()
    r = await client.post(f"/approvals/{approval['id']}/approve", headers=auth(ANA))
    assert r.status_code == 200
    result = r.json()["execution_result"]
    assert result["status"] == "failed"
    assert "STRIPE_SECRET_KEY" in result["error"]


async def test_live_stripe_key_is_refused_by_default(client, family, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_should_not_be_used")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        hid = family["household_id"]
        bill = await _bill(client, hid)
        approval = (await client.post(f"/households/{hid}/bills/{bill['id']}/request-payment", headers=auth(ROSA))).json()
        r = await client.post(f"/approvals/{approval['id']}/approve", headers=auth(ANA))
        assert r.json()["execution_result"]["status"] == "failed"
        assert "PAYMENTS_LIVE_ENABLED" in r.json()["execution_result"]["error"]
    finally:
        get_settings.cache_clear()


async def test_money_actions_cannot_be_created_through_raw_approvals_endpoint(client, family):
    r = await client.post(
        "/approvals",
        json={"agent_id": "warden", "action_type": "bill_payment", "payload": {"bill_id": "x"}},
        headers=auth(ANA),
    )
    assert r.status_code == 400
