"""Custom agents: who can make, change and delete them, that they only get
read-only tools, scheduled runs, and that they're covered by export and
account deletion. The model is the ScriptedModel fake; everything else
runs for real against Postgres.
"""
import uuid
from datetime import datetime, timezone

from anthropic.types.beta import BetaTextBlock, BetaToolUseBlock
from sqlalchemy import select, update

from app import custom_agents
from app.agent.prompts import CUSTOM_AGENT_PROMPT
from app.db import SessionLocal
from app.models import Conversation, CustomAgent, Message
from tests.conftest import ANA, ROSA, auth
from tests.test_banking_and_agent import ScriptedModel, _message, _parse_sse

SPENDING = {
    "name": "Spending check",
    "instructions": "Review this month's spending and tell me where the money went, biggest categories first.",
    "kind": "calc",
    "schedule": "manual",
}


def _model(monkeypatch, steps):
    model = ScriptedModel(steps)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.agent.runner._client", lambda: model)
    return model


async def _make(client, hid, who=ANA, **overrides):
    r = await client.post(f"/households/{hid}/agents", json={**SPENDING, **overrides}, headers=auth(who))
    assert r.status_code == 201, r.text
    return r.json()


async def test_make_list_change_delete(client, family):
    hid = family["household_id"]
    agent = await _make(client, hid)
    assert agent["ref"] == f"custom:{agent['id']}"
    assert agent["created_by"] == "Ana" and agent["can_edit"] is True
    assert agent["next_run_at"] is None  # manual

    # The account owner sees it and can change it too.
    [listed] = (await client.get(f"/households/{hid}/agents", headers=auth(ROSA))).json()
    assert listed["id"] == agent["id"] and listed["can_edit"] is True

    r = await client.patch(f"/households/{hid}/agents/{agent['id']}", json={"schedule": "weekly"}, headers=auth(ROSA))
    assert r.status_code == 200, r.text
    next_run = datetime.fromisoformat(r.json()["next_run_at"])
    assert next_run.weekday() == 0 and next_run.hour == custom_agents.RUN_HOUR_UTC

    r = await client.delete(f"/households/{hid}/agents/{agent['id']}", headers=auth(ROSA))
    assert r.status_code == 204
    assert (await client.get(f"/households/{hid}/agents", headers=auth(ANA))).json() == []

    events = [e["event_type"] for e in (await client.get(f"/households/{hid}/audit", headers=auth(ROSA))).json()]
    assert {"agent.created", "agent.updated", "agent.deleted"} <= set(events)


async def test_rules_for_making_and_deleting(client, family):
    hid = family["household_id"]
    # Warden's own agents' names are taken.
    r = await client.post(f"/households/{hid}/agents", json={**SPENDING, "name": "Warden"}, headers=auth(ANA))
    assert r.status_code == 422
    # Milo's and Sentinel's faces are theirs.
    r = await client.post(f"/households/{hid}/agents", json={**SPENDING, "kind": "beacon"}, headers=auth(ANA))
    assert r.status_code == 422
    # Instructions too short to be a job.
    r = await client.post(f"/households/{hid}/agents", json={**SPENDING, "instructions": "hi"}, headers=auth(ANA))
    assert r.status_code == 422

    # Only the person who made it or the account owner can change it.
    rosas = await _make(client, hid, who=ROSA, name="Bills watch")
    r = await client.delete(f"/households/{hid}/agents/{rosas['id']}", headers=auth(ANA))
    assert r.status_code == 403
    [listed] = (await client.get(f"/households/{hid}/agents", headers=auth(ANA))).json()
    assert listed["can_edit"] is False

    # People outside the family see nothing.
    assert (await client.get(f"/households/{hid}/agents", headers=auth("eve@example.com"))).status_code in (403, 404)

    # Up to ten per family.
    for i in range(custom_agents.MAX_PER_HOUSEHOLD - 1):
        await _make(client, hid, name=f"Agent {i}")
    r = await client.post(f"/households/{hid}/agents", json=SPENDING, headers=auth(ANA))
    assert r.status_code == 409


async def test_approver_without_access_cannot_make_one(client):
    r = await client.post(
        "/households",
        json={"name": "Rosa's accounts", "my_role": "approver", "my_display_name": "Ana",
              "invite": {"email": ROSA, "display_name": "Rosa", "role": "elder"}},
        headers=auth(ANA),
    )
    hid = r.json()["household"]["id"]
    r = await client.post(f"/households/{hid}/agents", json=SPENDING, headers=auth(ANA))
    assert r.status_code == 403 and "permission" in r.json()["detail"]


def test_next_run_dates():
    def at(*args):
        return datetime(*args, tzinfo=timezone.utc)

    assert custom_agents.next_run("manual", at(2026, 10, 17, 9)) is None
    # Weekly: Mondays at 13:00 UTC, strictly after now.
    assert custom_agents.next_run("weekly", at(2026, 10, 14, 9)) == at(2026, 10, 19, 13)  # Wednesday
    assert custom_agents.next_run("weekly", at(2026, 10, 19, 12)) == at(2026, 10, 19, 13)  # Monday morning
    assert custom_agents.next_run("weekly", at(2026, 10, 19, 13)) == at(2026, 10, 26, 13)  # exactly then
    # Monthly: the 1st at 13:00 UTC.
    assert custom_agents.next_run("monthly", at(2026, 10, 17, 9)) == at(2026, 11, 1, 13)
    assert custom_agents.next_run("monthly", at(2026, 10, 1, 12)) == at(2026, 10, 1, 13)
    assert custom_agents.next_run("monthly", at(2026, 12, 5, 9)) == at(2027, 1, 1, 13)


async def test_chat_with_a_custom_agent_is_read_only(client, family, monkeypatch):
    hid = family["household_id"]
    bill = (
        await client.post(f"/households/{hid}/bills", json={"payee_name": "ConEd", "amount": "84.20"}, headers=auth(ROSA))
    ).json()
    agent = await _make(client, hid)
    model = _model(
        monkeypatch,
        [
            # Even if the model asks for a money tool, the agent can't use it.
            lambda msgs: _message(
                [BetaToolUseBlock(type="tool_use", id="toolu_1", name="request_bill_payment", input={"bill_id": bill["id"]})],
                "tool_use",
            ),
            lambda msgs: _message([BetaToolUseBlock(type="tool_use", id="toolu_2", name="list_bills", input={})], "tool_use"),
            lambda msgs: _message([BetaTextBlock(type="text", text="One bill: ConEd, $84.20.")], "end_turn"),
        ],
    )
    conv = (
        await client.post("/conversations", json={"household_id": hid, "active_participants": [agent["ref"]]}, headers=auth(ANA))
    ).json()
    r = await client.post(f"/conversations/{conv['id']}/messages", json={"content": custom_agents.RUN_NOW_TEXT}, headers=auth(ANA))
    events = _parse_sse(r.text)

    assert events[0] == ("start", {"agent_id": agent["ref"], "model": "claude-opus-5-5"})
    assert events[-1][0] == "done"
    assert [d["agent"] for e, d in events if e == "tool"] == [agent["ref"], agent["ref"]]

    first = model.requests[0]
    assert first["system"][0]["text"] == CUSTOM_AGENT_PROMPT
    assert "<agent_job>" in first["system"][1]["text"] and SPENDING["instructions"] in first["system"][1]["text"]
    assert {t["name"] for t in first["tools"]} <= custom_agents.READ_ONLY_TOOLS

    refused = model.requests[1]["messages"][-1]["content"][0]
    assert refused["is_error"] is True and "read-only" in refused["content"]

    # Nothing was asked of the family and the bill is untouched.
    assert (await client.get(f"/approvals?household_id={hid}", headers=auth(ANA))).json() == []
    assert (await client.get(f"/households/{hid}/bills", headers=auth(ROSA))).json()[0]["status"] != "pending_approval"
    shown = (await client.get(f"/conversations/{conv['id']}/messages", headers=auth(ANA))).json()
    assert shown[-1]["agent_id"] == agent["ref"]


async def test_deleted_agent_cannot_answer(client, family, monkeypatch):
    hid = family["household_id"]
    agent = await _make(client, hid)
    conv = (
        await client.post("/conversations", json={"household_id": hid, "active_participants": [agent["ref"]]}, headers=auth(ANA))
    ).json()
    await client.delete(f"/households/{hid}/agents/{agent['id']}", headers=auth(ANA))
    _model(monkeypatch, [])
    r = await client.post(f"/conversations/{conv['id']}/messages", json={"content": "hello?"}, headers=auth(ANA))
    [(event, data)] = _parse_sse(r.text)
    assert event == "error" and "deleted" in data["message"]

    # And a chat can't be started with an agent that doesn't exist.
    r = await client.post("/conversations", json={"household_id": hid, "active_participants": [agent["ref"]]}, headers=auth(ANA))
    assert r.status_code == 404


async def test_scheduled_run(client, family, monkeypatch):
    hid = family["household_id"]
    agent = await _make(client, hid, schedule="monthly")
    _model(monkeypatch, [lambda msgs: _message([BetaTextBlock(type="text", text="October: $1,240 spent.")], "end_turn")])
    sent = []

    async def fake_notify(emails, subject, body, *, link=None):
        sent.append((emails, subject))
        return True

    monkeypatch.setattr("app.notify.notify_people", fake_notify)
    now = datetime(2026, 11, 1, 13, 5, tzinfo=timezone.utc)
    async with SessionLocal() as db:
        await db.execute(update(CustomAgent).values(next_run_at=datetime(2026, 11, 1, 13, tzinfo=timezone.utc)))
        await db.commit()

    [summary] = await custom_agents.run_due(now)
    assert summary["status"] == "done", summary
    # A second tick finds nothing due: the run was claimed.
    assert await custom_agents.run_due(now) == []
    assert sent == [(["ana@example.com"], "Spending check finished its monthly run")]

    async with SessionLocal() as db:
        row = await db.get(CustomAgent, uuid.UUID(agent["id"]))
        assert row.last_run_at == now and row.next_run_at == datetime(2026, 12, 1, 13, tzinfo=timezone.utc)
        conv = (await db.execute(select(Conversation).where(Conversation.active_participants == [agent["ref"]]))).scalar_one()
        assert conv.title == "Spending check · Nov 1"
        reply = (
            await db.execute(select(Message).where(Message.conversation_id == conv.id, Message.role == "agent"))
        ).scalar_one()
        assert reply.content == "October: $1,240 spent." and reply.agent_id == agent["ref"]

    # The creator finds the report among their chats.
    chats = (await client.get(f"/conversations?household_id={hid}", headers=auth(ANA))).json()
    assert any(c["title"] == "Spending check · Nov 1" for c in chats)


async def test_export_and_account_deletion_cover_agents(client, family):
    hid = family["household_id"]
    await _make(client, hid)
    await _make(client, hid, who=ROSA, name="Bills watch")

    rosa = (await client.get("/me/export", headers=auth(ROSA))).json()
    assert {a["name"] for a in rosa["households"][0]["agents"]} == {"Spending check", "Bills watch"}
    ana = (await client.get("/me/export", headers=auth(ANA))).json()
    assert [a["name"] for a in ana["households"][0]["agents_i_made"]] == ["Spending check"]

    r = await client.request("DELETE", "/me", json={"confirm": "DELETE"}, headers=auth(ANA))
    assert r.status_code == 200, r.text
    left = (await client.get(f"/households/{hid}/agents", headers=auth(ROSA))).json()
    assert [a["name"] for a in left] == ["Bills watch"]


async def test_cron_endpoint_needs_the_secret(client, family, monkeypatch):
    await _make(client, family["household_id"], schedule="weekly")
    r = await client.get("/internal/cron/agents")
    assert r.status_code == 401  # no CRON_SECRET configured: always refused

    monkeypatch.setenv("CRON_SECRET", "s3cret-for-tests")
    from app.config import get_settings

    get_settings.cache_clear()
    assert (await client.get("/internal/cron/agents", headers={"Authorization": "Bearer wrong"})).status_code == 401
    r = await client.get("/internal/cron/agents", headers={"Authorization": "Bearer s3cret-for-tests"})
    assert r.status_code == 200 and r.json() == {"runs": []}  # nothing due yet


async def test_run_due_respects_its_time_budget(client, family):
    await _make(client, family["household_id"], schedule="weekly")
    async with SessionLocal() as db:
        await db.execute(update(CustomAgent).values(next_run_at=datetime(2026, 10, 19, 13, tzinfo=timezone.utc)))
        await db.commit()
    # A spent budget starts nothing; the agent stays due for the next tick.
    assert await custom_agents.run_due(datetime(2026, 10, 19, 13, 5, tzinfo=timezone.utc), budget_seconds=0) == []
    async with SessionLocal() as db:
        [row] = (await db.execute(select(CustomAgent))).scalars().all()
        assert row.last_run_at is None
