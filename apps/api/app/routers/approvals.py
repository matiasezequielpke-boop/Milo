"""The HITL approval gate — Fase 5's other half, now family-shaped.

Warden's money actions (bill_payment, subscription_cancel) are proposed by
the agent's tools or by the "ask to pay" buttons below, and resolved here
by a human. Approve runs the action through app/warden.py -> app/executor.py;
deny/block runs nothing. See app/warden.py for who may do which.

The legacy, household-less flow (Herald's email_send, etc.) keeps working
through POST /approvals for the requesting user alone.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, warden
from app.agents.definitions import get_agent
from app.db import get_db
from app.deps import get_current_user
from app.households import SCOPE_VIEW_ACCOUNTS, get_membership, require_member, require_scope
from app.models import ApprovalRequest, ApprovalStatus, HouseholdMember, MemberStatus, User
from app.schemas import ApprovalCreateRequest, ApprovalResolveRequest, ApprovalResponse

router = APIRouter(tags=["approvals"])

# Money actions only ever come from Warden's own code path, never a raw POST.
_WARDEN_ONLY = {"bill_payment", "subscription_cancel", "purchase_execute", "vault_use"}


def _validate_gated_action(agent_id: str, action_type: str) -> None:
    try:
        agent = get_agent(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if action_type not in agent.requires_approval_for:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{agent.name} does not require approval for {action_type!r}.",
        )
    if action_type in _WARDEN_ONLY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Money actions are requested through Warden (chat or the household's bill/subscription pages).",
        )


async def _response(db: AsyncSession, approval: ApprovalRequest, user: User) -> ApprovalResponse:
    can_resolve = False
    if approval.status == ApprovalStatus.pending:
        if approval.household_id is None:
            can_resolve = approval.user_id == user.id
        else:
            membership = await get_membership(db, approval.household_id, user)
            can_resolve = bool(membership and (warden.can_approve(membership) or warden.can_block(membership)))
    return ApprovalResponse(
        id=approval.id,
        household_id=approval.household_id,
        conversation_id=approval.conversation_id,
        agent_id=approval.agent_id,
        action_type=approval.action_type,
        payload=approval.payload,
        summary=approval.summary,
        status=approval.status.value,
        requested_at=approval.requested_at,
        resolved_at=approval.resolved_at,
        resolution_note=approval.resolution_note,
        execution_result=approval.execution_result,
        can_resolve=can_resolve,
    )


@router.post("/approvals", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
async def create_approval(
    body: ApprovalCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalResponse:
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
    return await _response(db, approval, current_user)


@router.get("/approvals", response_model=list[ApprovalResponse])
async def list_approvals(
    status_filter: str | None = None,
    household_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ApprovalResponse]:
    """Everything this person may see: their own legacy requests, plus
    every request in households where they can view the accounts."""
    member_rows = await db.execute(
        select(HouseholdMember.household_id).where(
            HouseholdMember.user_id == current_user.id, HouseholdMember.status == MemberStatus.active
        )
    )
    visible: list[uuid.UUID] = []
    for hid in member_rows.scalars():
        membership = await get_membership(db, hid, current_user)
        if membership and membership.has(SCOPE_VIEW_ACCOUNTS):
            visible.append(hid)
    if household_id is not None:
        visible = [h for h in visible if h == household_id]

    query = select(ApprovalRequest).where(
        or_(
            ApprovalRequest.household_id.in_(visible),
            (ApprovalRequest.household_id.is_(None)) & (ApprovalRequest.user_id == current_user.id),
        )
    )
    if household_id is not None:
        query = select(ApprovalRequest).where(ApprovalRequest.household_id.in_(visible))
    if status_filter:
        query = query.where(ApprovalRequest.status == status_filter)
    result = await db.execute(query.order_by(ApprovalRequest.requested_at.desc()).limit(200))
    return [await _response(db, a, current_user) for a in result.scalars()]


async def _resolve(
    approval_id: uuid.UUID, approve: bool, note: str | None, db: AsyncSession, current_user: User
) -> ApprovalResponse:
    existing = await db.get(ApprovalRequest, approval_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")

    if existing.household_id is None:
        # Legacy single-user flow: the requester resolves their own request.
        if existing.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
        if existing.status != ApprovalStatus.pending:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Approval request already {existing.status.value}.")
        existing.status = ApprovalStatus.approved if approve else ApprovalStatus.denied
        existing.resolved_at = datetime.now(timezone.utc)
        existing.resolved_by_user_id = current_user.id
        await audit.record(
            db,
            event_type=f"approval.{existing.status.value}",
            user_id=current_user.id,
            agent_id=existing.agent_id,
            detail={"action_type": existing.action_type},
        )
        await db.commit()
        return await _response(db, existing, current_user)

    async def membership_for(household_id: uuid.UUID):
        membership = await require_member(db, household_id, current_user)
        require_scope(membership, SCOPE_VIEW_ACCOUNTS)
        return membership

    approval = await warden.resolve(
        db,
        approval_id=approval_id,
        user=current_user,
        membership_for=membership_for,
        approve=approve,
        note=note,
    )
    return await _response(db, approval, current_user)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: uuid.UUID,
    body: ApprovalResolveRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalResponse:
    return await _resolve(approval_id, True, body.note if body else None, db, current_user)


@router.post("/approvals/{approval_id}/deny", response_model=ApprovalResponse)
async def deny(
    approval_id: uuid.UUID,
    body: ApprovalResolveRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalResponse:
    return await _resolve(approval_id, False, body.note if body else None, db, current_user)


# --- "Ask to pay / cancel" buttons (same gate as the agent's tools) ---------


async def _propose(db: AsyncSession, household_id: uuid.UUID, user: User, fn, **kwargs) -> ApprovalResponse:
    membership = await require_member(db, household_id, user)
    require_scope(membership, SCOPE_VIEW_ACCOUNTS)
    try:
        approval = await fn(db, membership=membership, user=user, **kwargs)
    except warden.ProposalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await warden.notify_requested(db, approval)
    return await _response(db, approval, user)


@router.post(
    "/households/{household_id}/bills/{bill_id}/request-payment",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_bill_payment(
    household_id: uuid.UUID,
    bill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalResponse:
    return await _propose(db, household_id, current_user, warden.propose_bill_payment, bill_id=bill_id)


@router.post(
    "/households/{household_id}/subscriptions/{subscription_id}/request-cancel",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_subscription_cancel(
    household_id: uuid.UUID,
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApprovalResponse:
    return await _propose(
        db, household_id, current_user, warden.propose_subscription_cancel, subscription_id=subscription_id
    )
