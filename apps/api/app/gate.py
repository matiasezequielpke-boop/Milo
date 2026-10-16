"""The enforcement point real agent-execution code (the future LangGraph
coordinator) must call before running any action listed in an agent's
`requires_approval_for`. There's no agent loop wired to a live model yet
(Fase 1 gateway is still inert pending Fase 0 budget) — this exists now
so that when one lands, it has nowhere to accidentally skip the gate.

Usage once a real agent loop exists:

    approval = await gate.request_approval(db, user_id=..., agent_id="warden",
                                             action_type="purchase_execute", payload={...})
    raise ApprovalPending(approval.id)  # pause this run; resume on approvals.approve webhook/poll

The HTTP surface for creating/approving/denying these lives in
app/routers/approvals.py; this module is the non-HTTP entry point for
in-process agent code.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents.definitions import get_agent
from app.models import ApprovalRequest, ApprovalStatus


class UngatedActionError(ValueError):
    """Raised if code calls request_approval() for an action that isn't
    actually gated — a sign the caller has the wrong action_type, not a
    reason to silently proceed."""


class ApprovalPending(RuntimeError):
    """Signal to pause agent execution until a human resolves the approval."""

    def __init__(self, approval_id: uuid.UUID):
        self.approval_id = approval_id
        super().__init__(f"Waiting on human approval {approval_id}")


async def request_approval(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    agent_id: str,
    action_type: str,
    payload: dict,
    conversation_id: uuid.UUID | None = None,
    household_id: uuid.UUID | None = None,
    summary: str | None = None,
) -> ApprovalRequest:
    agent = get_agent(agent_id)
    if action_type not in agent.requires_approval_for:
        raise UngatedActionError(f"{agent.name} does not require approval for {action_type!r}")

    approval = ApprovalRequest(
        user_id=user_id,
        household_id=household_id,
        conversation_id=conversation_id,
        agent_id=agent_id,
        action_type=action_type,
        payload=payload,
        summary=summary,
        status=ApprovalStatus.pending,
    )
    db.add(approval)
    await db.flush()
    await audit.record(
        db, event_type="approval.requested", user_id=user_id, agent_id=agent_id,
        household_id=household_id,
        detail={"action_type": action_type, "approval_id": str(approval.id), "summary": summary},
    )
    return approval


def is_approved(approval: ApprovalRequest) -> bool:
    return approval.status == ApprovalStatus.approved
