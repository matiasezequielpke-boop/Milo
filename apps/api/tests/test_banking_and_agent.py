"""Bank sync -> detection -> alert, and the agent loop -> approval request.

Plaid and Anthropic are replaced at their network boundary only; storage,
detection, permissions, the approval gate, history rebuilding, and the
SSE protocol all run for real against Postgres.
"""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock, BetaUsage

from app import plaid_service
from tests.conftest import ANA, ROSA, auth

TODAY = date.today()


def _plaid_txn(i, days_ago, amount, name, merchant=None):
    return {
        "transaction_id": f"tx_{i}",
        "account_id": "acc_checking",
        "amount": amount,
        "iso_currency_code": "USD",
        "date": (TODAY - timedelta(days=days_ago)).isoformat(),
        "authorized_date": None,
        "name": name,
        "merchant_name": merchant,
        "personal_finance_category": {"primary": "GENERAL_MERCHANDISE"},
        "payment_channel": "in store",
        "pending": False,
    }


@pytest.fixture
def fake_plaid(monkeypatch):
    monkeypatch.setenv("PLAID_CLIENT_ID", "test")
    monkeypatch.setenv("PLAID_SECRET", "test")
    from app.config import get_settings

    get_settings.cache_clear()

    async def exchange(public_token):
        assert public_token == "public-sandbox-abc"
        return "access-sandbox-secret", "item_1"

    pages = []
    groceries = [_plaid_txn(f"g{i}", 5 + 7 * i, 55 + i * 3, "SAFEWAY #1234", "Safeway") for i in range(10)]
    pages.append(groceries + [_plaid_txn("scam", 1, 500, "GIFT CARD MALL #3")])

    async def fetch_changes(access_token, cursor):
        assert access_token == "access-sandbox-secret"  # decrypted from the vault
        added = pages.pop(0) if pages else []
        return plaid_service.SyncPage(
            accounts=[
                {
                    "account_id": "acc_checking",
                    "name": "Plaid Checking",
                    "official_name": None,
                    "mask": "0000",
                    "type": "depository",
                    "subtype": "checking",
                    "balances": {"current": 4120.55, "available": 4020.55, "iso_currency_code": "USD"},
                }
            ],
            added=added,
            modified=[],
            removed=[],
            cursor=f"cursor-{len(pages)}",
        )

    monkeypatch.setattr(plaid_service, "exchange_public_token", exchange)
    monkeypatch.setattr(plaid_service, "fetch_changes", fetch_changes)
    yield
    get_settings.cache_clear()


async def test_bank_connection_sync_raises_alert_once(client, family, fake_plaid):
    hid = family["household_id"]
    r = await client.post(
        f"/households/{hid}/plaid/exchange",
        json={"public_token": "public-sandbox-abc", "institution_name": "First Platypus Bank"},
        headers=auth(ANA),
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"connections": 1, "accounts": 1, "added": 11, "modified": 0, "removed": 0, "new_alerts": 1}

    accounts = (await client.get(f"/households/{hid}/accounts", headers=auth(ROSA))).json()
    assert accounts[0]["current_balance"] == "4120.55"
    assert accounts[0]["institution_name"] == "First Platypus Bank"

    alerts = (await client.get(f"/households/{hid}/alerts", headers=auth(ANA))).json()
    [alert] = alerts
    assert alert["kind"] == "scam_pattern"
    assert alert["severity"] == "high"
    assert alert["transaction"]["name"] == "GIFT CARD MALL #3"

    # A second sync with no new data doesn't duplicate the alert.
    r = await client.post(f"/households/{hid}/sync", headers=auth(ANA))
    assert r.json()["new_alerts"] == 0
    assert len((await client.get(f"/households/{hid}/alerts", headers=auth(ANA))).json()) == 1


async def test_plaid_token_is_stored_encrypted(client, family, fake_plaid):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Credential

    await client.post(
        f"/households/{family['household_id']}/plaid/exchange",
        json={"public_token": "public-sandbox-abc"},
        headers=auth(ANA),
    )
    async with SessionLocal() as db:
        credential = (await db.execute(select(Credential))).scalar_one()
    assert credential.name == "plaid:item_1"
    assert "access-sandbox-secret" not in credential.encrypted_value


async def test_marking_fraud_blocks_the_payee(client, family, fake_plaid):
    hid = family["household_id"]
    await client.post(f"/households/{hid}/plaid/exchange", json={"public_token": "public-sandbox-abc"}, headers=auth(ANA))
    [alert] = (await client.get(f"/households/{hid}/alerts", headers=auth(ANA))).json()

    r = await client.post(
        f"/households/{hid}/alerts/{alert['id']}/resolve", json={"resolution": "confirmed_fraud"}, headers=auth(ROSA)
    )
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed_fraud"

    bill = (
        await client.post(
            f"/households/{hid}/bills", json={"payee_name": "GIFT CARD MALL #3", "amount": "500.00"}, headers=auth(ROSA)
        )
    ).json()
    assert bill["payee_blocked"] is True
    r = await client.post(f"/households/{hid}/bills/{bill['id']}/request-payment", headers=auth(ROSA))
    assert r.status_code == 409
    assert "blocked" in r.json()["detail"]


async def test_plaid_endpoints_say_when_not_configured(client, family):
    r = await client.post(f"/households/{family['household_id']}/plaid/link-token", headers=auth(ANA))
    assert r.status_code == 503
    assert "PLAID_CLIENT_ID" in r.json()["detail"]


# --- The agent loop ---------------------------------------------------------


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events = []
    for chunk in raw.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def _message(content, stop_reason):
    return BetaMessage(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=BetaUsage(input_tokens=10, output_tokens=10),
    )


class ScriptedModel:
    """Plays the model's side of a conversation. Each step reads the request
    it's given (like the real API would) and returns the next message."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        message = self.steps.pop(0)(kwargs["messages"])
        model = self

        class _Stream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def __aiter__(self):
                async def gen():
                    for block in message.content:
                        if block.type == "tool_use":
                            yield SimpleNamespace(type="content_block_start", content_block=block)
                        elif block.type == "text":
                            yield SimpleNamespace(type="text", text=block.text)

                return gen()

            async def get_final_message(self):
                return message

        assert model is self
        return _Stream()


def _last_tool_result(messages) -> dict:
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m["content"], list):
            for block in m["content"]:
                if block.get("type") == "tool_result":
                    return json.loads(block["content"])
    raise AssertionError("no tool result in history")


async def test_agent_requests_approval_and_never_pays(client, family, monkeypatch):
    hid = family["household_id"]
    await client.post(
        f"/households/{hid}/bills",
        json={"payee_name": "ConEd", "amount": "84.20", "due_date": "2026-10-30"},
        headers=auth(ROSA),
    )
    model = ScriptedModel(
        [
            lambda msgs: _message(
                [BetaToolUseBlock(type="tool_use", id="toolu_1", name="list_bills", input={})], "tool_use"
            ),
            lambda msgs: _message(
                [
                    BetaTextBlock(type="text", text="I'll ask Ana to approve it."),
                    BetaToolUseBlock(
                        type="tool_use",
                        id="toolu_2",
                        name="request_bill_payment",
                        input={"bill_id": _last_tool_result(msgs)["bills"][0]["bill_id"], "reason": "due soon"},
                    ),
                ],
                "tool_use",
            ),
            lambda msgs: _message(
                [BetaTextBlock(type="text", text=" Done — it's waiting for Ana's approval. Nothing is paid yet.")],
                "end_turn",
            ),
        ]
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.agent.runner._client", lambda: model)
    try:
        conv = (await client.post("/conversations", json={"household_id": hid}, headers=auth(ROSA))).json()
        r = await client.post(
            f"/conversations/{conv['id']}/messages", json={"content": "Please pay my ConEd bill"}, headers=auth(ROSA)
        )
        events = _parse_sse(r.text)
    finally:
        get_settings.cache_clear()

    kinds = [e for e, _ in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    assert ("tool", {"name": "request_bill_payment", "status": "Warden is asking the family to approve", "agent": "warden"}) in events
    [approval_event] = [d for e, d in events if e == "approval"]
    assert approval_event["approval"]["summary"].startswith("Pay $84.20 to ConEd")

    # The request shape sent to the model.
    first = model.requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert first["betas"] == ["server-side-fallback-2026-07-01"]
    assert first["thinking"] == {"type": "adaptive"}
    assert first["output_config"] == {"effort": "medium"}
    assert all(t["eager_input_streaming"] for t in first["tools"])
    context = first["messages"][0]["content"][0]["text"]
    assert "You're talking with Rosa, the account owner" in context and "Can approve actions: no" in context

    # History is append-only: request 3 starts with exactly request 2's messages.
    assert model.requests[2]["messages"][: len(model.requests[1]["messages"])] == model.requests[1]["messages"]

    # The approval exists, nothing was paid, and Ana sees it as resolvable.
    approvals = (await client.get(f"/approvals?household_id={hid}&status_filter=pending", headers=auth(ANA))).json()
    assert len(approvals) == 1 and approvals[0]["can_resolve"] is True
    assert approvals[0]["conversation_id"] == conv["id"]
    bills = (await client.get(f"/households/{hid}/bills", headers=auth(ROSA))).json()
    assert bills[0]["status"] == "pending_approval"

    # The chat shows people only the visible turns.
    shown = (await client.get(f"/conversations/{conv['id']}/messages", headers=auth(ROSA))).json()
    assert [m["role"] for m in shown] == ["user", "agent", "agent"]


async def test_resolution_appears_in_the_conversation_and_next_turn(client, family, monkeypatch):
    hid = family["household_id"]
    bill = (
        await client.post(f"/households/{hid}/bills", json={"payee_name": "ConEd", "amount": "84.20"}, headers=auth(ROSA))
    ).json()
    model = ScriptedModel(
        [
            lambda msgs: _message(
                [BetaToolUseBlock(type="tool_use", id="toolu_1", name="request_bill_payment", input={"bill_id": bill["id"]})],
                "tool_use",
            ),
            lambda msgs: _message([BetaTextBlock(type="text", text="Sent to Ana.")], "end_turn"),
            lambda msgs: _message([BetaTextBlock(type="text", text="Ana blocked it, so nothing was paid.")], "end_turn"),
        ]
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.agent.runner._client", lambda: model)
    try:
        conv = (await client.post("/conversations", json={"household_id": hid}, headers=auth(ROSA))).json()
        await client.post(f"/conversations/{conv['id']}/messages", json={"content": "pay ConEd"}, headers=auth(ROSA))
        [approval] = (await client.get(f"/approvals?household_id={hid}", headers=auth(ANA))).json()
        await client.post(f"/approvals/{approval['id']}/deny", headers=auth(ANA))
        await client.post(f"/conversations/{conv['id']}/messages", json={"content": "did it go through?"}, headers=auth(ROSA))
    finally:
        get_settings.cache_clear()

    third = model.requests[2]["messages"]
    texts = [b.get("text", "") for m in third for b in (m["content"] if isinstance(m["content"], list) else [])]
    assert any("<warden_event>Ana blocked: Pay $84.20 to ConEd" in t for t in texts)
    # Earlier turns replayed unchanged.
    assert third[: len(model.requests[1]["messages"])] == model.requests[1]["messages"]
    shown = (await client.get(f"/conversations/{conv['id']}/messages", headers=auth(ROSA))).json()
    assert [m["role"] for m in shown] == ["user", "agent", "system", "user", "agent"]


async def test_chat_without_model_key_says_so(client, family):
    conv = (await client.post("/conversations", json={"household_id": family["household_id"]}, headers=auth(ROSA))).json()
    r = await client.post(f"/conversations/{conv['id']}/messages", json={"content": "hi"}, headers=auth(ROSA))
    [(event, data)] = _parse_sse(r.text)
    assert event == "error" and "ANTHROPIC_API_KEY" in data["message"]


async def test_agent_respects_missing_consent(client, monkeypatch):
    # Ana creates the household but Rosa never consents: tools must refuse.
    r = await client.post(
        "/households",
        json={"name": "Rosa's accounts", "my_role": "approver", "my_display_name": "Ana",
              "invite": {"email": ROSA, "display_name": "Rosa", "role": "elder"}},
        headers=auth(ANA),
    )
    hid = r.json()["household"]["id"]
    model = ScriptedModel(
        [
            lambda msgs: _message([BetaToolUseBlock(type="tool_use", id="toolu_1", name="list_transactions", input={})], "tool_use"),
            lambda msgs: _message([BetaTextBlock(type="text", text="Rosa needs to give you access first.")], "end_turn"),
        ]
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.agent.runner._client", lambda: model)
    try:
        conv = (await client.post("/conversations", json={"household_id": hid}, headers=auth(ANA))).json()
        await client.post(f"/conversations/{conv['id']}/messages", json={"content": "show charges"}, headers=auth(ANA))
    finally:
        get_settings.cache_clear()
    tool_result = model.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "hasn't granted them permission" in tool_result["content"]
