"""The HITL approval gate — Fase 5's other half.

Any agent whose AgentDefinition.requires_approval_for lists an action
(Herald: email_send/message_send; Warden: vault_use/purchase_execute)
must create a pending ApprovalRequest here and stop — never execute
the action first. `gate.require_approval()` is the function future
agent-execution code calls to enforce this; these endpoints are what
the frontend polls/renders and what a human acts on.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents.definitions import get_agent
from app.db import get_db
from app.deps import get_current_user
from app.models import ApprovalRequest, ApprovalStatus, User
from app.schemas import ApprovalCreateRequest, ApprovalResponse

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _validate_gated_action(agent_id: str, action_type: str) -> None:
    agent = get_agent(agent_id)  # raises ValueError -> 500 if unknown; caught by FastAPI as 500
    if action_type not in agent.requires_approval_for:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{agent.name} does not require approval for {action_type!r}.",
        )


@router.post("", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
async def create_approval(
    body: ApprovalCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalRequest:
    _validate_gated_action(body.agent_id, body.action_type)

    approval = ApprovalRequest(
        user_id=current_user.id,
        conversation_id=body.conversation_id,
        agent_id=body.agent_id,
        action_type=body.action_type,
        payload=body.payload,
        status=ApprovalStatus.pending,
    )
    db.add(approval)
    await audit.record(
        db,
        event_type="approval.requested",
        user_id=current_user.id,
        agent_id=body.agent_id,
        detail={"action_type": body.action_type},
    )
    await db.commit()
    await db.refresh(approval)
    return approval


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ApprovalRequest]:
    query = select(ApprovalRequest).where(ApprovalRequest.user_id == current_user.id)
    if status_filter:
        query = query.where(ApprovalRequest.status == status_filter)
    result = await db.execute(query.order_by(ApprovalRequest.requested_at.desc()))
    return list(result.scalars().all())


async def _resolve(
    approval_id: str,
    new_status: ApprovalStatus,
    db: AsyncSession,
    current_user: User,
) -> ApprovalRequest:
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id, ApprovalRequest.user_id == current_user.id
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval request already {approval.status.value}.",
        )

    approval.status = new_status
    approval.resolved_at = datetime.now(timezone.utc)
    await audit.record(
        db,
        event_type=f"approval.{new_status.value}",
        user_id=current_user.id,
        agent_id=approval.agent_id,
        detail={"action_type": approval.action_type},
    )
    await db.commit()
    await db.refresh(approval)
    return approval


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ApprovalRequest:
    return await _resolve(approval_id, ApprovalStatus.approved, db, current_user)


@router.post("/{approval_id}/deny", response_model=ApprovalResponse)
async def deny(
    approval_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ApprovalRequest:
    return await _resolve(approval_id, ApprovalStatus.denied, db, current_user)
