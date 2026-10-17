"""Custom agents: made by a family member for one job, run on demand or on
a schedule, read-only.

A conversation with a custom agent has `active_participants =
["custom:<agent id>"]`; app/agent/runner.py then swaps Milo's system prompt
for CUSTOM_AGENT_PROMPT plus the agent's own job text, and offers only the
read-only tools below. Scheduled runs (weekly on Mondays, monthly on the
1st) are started by the Celery beat task in app/tasks.py via `run_due()`;
each run is a normal conversation owned by the agent's creator, who gets
an email when it's done.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app import notify
from app.config import get_settings
from app.db import SessionLocal
from app.models import Conversation, CustomAgent, User

logger = logging.getLogger(__name__)

PREFIX = "custom:"
READ_ONLY_TOOLS = frozenset({"get_overview", "list_transactions", "list_alerts", "list_subscriptions", "list_bills", "list_approvals"})
RESERVED_NAMES = {"milo", "warden", "sentinel", "scout", "herald", "ledger", "scribe", "courier"}
MAX_PER_HOUSEHOLD = 10
RUN_HOUR_UTC = 13  # morning across the US
RUN_NOW_TEXT = "Run your job now and report back."
SCHEDULE_LABEL = {"manual": "only when asked", "weekly": "every Monday", "monthly": "on the 1st of every month"}


def ref(agent_id: uuid.UUID) -> str:
    return f"{PREFIX}{agent_id}"


def agent_id_from(participants: list[str] | None) -> uuid.UUID | None:
    """The custom agent a conversation is with, if any."""
    if not participants or len(participants) != 1 or not participants[0].startswith(PREFIX):
        return None
    try:
        return uuid.UUID(participants[0].removeprefix(PREFIX))
    except ValueError:
        return None


def next_run(schedule: str, after: datetime) -> datetime | None:
    """The first scheduled moment strictly after `after`."""
    if schedule == "weekly":
        candidate = after.replace(hour=RUN_HOUR_UTC, minute=0, second=0, microsecond=0)
        candidate += timedelta(days=(7 - candidate.weekday()) % 7)  # Monday
        return candidate if candidate > after else candidate + timedelta(days=7)
    if schedule == "monthly":
        candidate = after.replace(day=1, hour=RUN_HOUR_UTC, minute=0, second=0, microsecond=0)
        if candidate > after:
            return candidate
        return candidate.replace(year=candidate.year + (candidate.month == 12), month=candidate.month % 12 + 1)
    return None


def job_block(agent: CustomAgent) -> dict:
    return {
        "type": "text",
        "text": f"<agent_job>\nName: {agent.name}\nRuns: {SCHEDULE_LABEL.get(agent.schedule, agent.schedule)}\n\n{agent.instructions}\n</agent_job>",
    }


async def run_due(now: datetime | None = None) -> list[dict]:
    """Starts every scheduled run that's due. Each agent is claimed with a
    conditional UPDATE first, so overlapping beat ticks can't run it twice."""
    from app.agent.runner import run_turn  # runner imports this module

    now = now or datetime.now(timezone.utc)
    summaries: list[dict] = []
    async with SessionLocal() as db:
        due = (
            await db.execute(
                select(CustomAgent).where(CustomAgent.schedule != "manual", CustomAgent.next_run_at <= now)
            )
        ).scalars().all()
        claimed: list[CustomAgent] = []
        for agent in due:
            got = await db.execute(
                update(CustomAgent)
                .where(CustomAgent.id == agent.id, CustomAgent.next_run_at <= now)
                .values(next_run_at=next_run(agent.schedule, now), last_run_at=now)
                .returning(CustomAgent.id)
            )
            if got.scalar_one_or_none() is not None:
                claimed.append(agent)
        await db.commit()

        for agent in claimed:
            creator = await db.get(User, agent.created_by_user_id) if agent.created_by_user_id else None
            if creator is None:
                summaries.append({"agent": str(agent.id), "status": "skipped", "reason": "creator gone"})
                continue
            conversation = Conversation(
                user_id=creator.id,
                household_id=agent.household_id,
                title=f"{agent.name} · {now:%b} {now.day}",
                active_participants=[ref(agent.id)],
            )
            db.add(conversation)
            await db.commit()
            errors = []
            async for chunk in run_turn(conversation.id, creator.id, RUN_NOW_TEXT):
                if chunk.startswith("event: error"):
                    errors.append(chunk.split("data: ", 1)[-1].strip())
            status = "failed" if errors else "done"
            summaries.append({"agent": str(agent.id), "conversation": str(conversation.id), "status": status, "errors": errors})
            if not errors:
                await notify.notify_people(
                    [creator.email],
                    f"{agent.name} finished its {('weekly' if agent.schedule == 'weekly' else 'monthly')} run",
                    f"Your agent {agent.name} looked at the accounts and wrote a report. Open Warden to read it.",
                    link=get_settings().web_app_url,
                )
            else:
                logger.warning("scheduled agent run failed: %s", errors)
    return summaries
