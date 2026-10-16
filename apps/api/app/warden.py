"""Warden's gate: propose an irreversible action, let a human decide, then
(and only then) execute it.

    propose_*()  ->  ApprovalRequest(pending)  ->  approver notified
    resolve(approve=True)   ->  executor.execute()  ->  result to the family
    resolve(approve=False)  ->  nothing runs

Both the agent's tools (app/agent/tools.py) and the plain HTTP buttons in
the app (app/routers/approvals.py, "ask to pay this bill") go through the
same functions here, so there is exactly one path to money movement.

Who may do what:
- Anyone in the household who can see the accounts may *ask* (the elder,
  or an approver with consent).
- Only a member with the `approve_actions` scope may *approve*.
- The elder may always *block* a request made on their behalf, and so may
  any approver.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, gate, notify
from app.config import get_settings
from app.executor import ExecutionError, execute
from app.households import SCOPE_APPROVE_ACTIONS, Membership, elders, members_with_scope
from app.models import (
    ApprovalRequest,
    ApprovalStatus,
    Bill,
    Conversation,
    Household,
    Message,
    Payee,
    Subscription,
    User,
)

APPROVAL_TTL = timedelta(hours=72)


class ProposalError(ValueError):
    """The action can't even be proposed (blocked payee, already paid...)."""


async def _pending_for(db: AsyncSession, household_id: uuid.UUID, key: str, value: str) -> ApprovalRequest | None:
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.household_id == household_id,
            ApprovalRequest.status == ApprovalStatus.pending,
            ApprovalRequest.payload[key].astext == value,
        )
    )
    return result.scalars().first()


async def propose_bill_payment(
    db: AsyncSession,
    *,
    membership: Membership,
    user: User,
    bill_id: uuid.UUID,
    reason: str | None = None,
    conversation_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    bill = await db.get(Bill, bill_id)
    if bill is None or bill.household_id != membership.household.id:
        raise ProposalError("That bill doesn't exist in this household.")
    if bill.status in ("paid", "processing"):
        raise ProposalError(f"That bill is already {bill.status}.")
    payee = await db.get(Payee, bill.payee_id)
    if payee is None or payee.blocked:
        raise ProposalError(
            f"{payee.name if payee else 'This payee'} is blocked because the family marked a charge from them as fraud. "
            "Warden won't pay them."
        )
    existing = await _pending_for(db, bill.household_id, "bill_id", str(bill.id))
    if existing is not None:
        return existing

    due = f", due {bill.due_date.isoformat()}" if bill.due_date else ""
    summary = f"Pay ${bill.amount:,.2f} to {payee.name}{due}" + (f" — {reason}" if reason else "")
    approval = await gate.request_approval(
        db,
        user_id=user.id,
        agent_id="warden",
        action_type="bill_payment",
        payload={
            "bill_id": str(bill.id),
            "payee": payee.name,
            "amount": str(bill.amount),
            "currency": bill.currency,
            "due_date": bill.due_date.isoformat() if bill.due_date else None,
            "reference": bill.reference,
            "requested_by": membership.member.display_name,
            "reason": reason,
        },
        conversation_id=conversation_id,
        household_id=bill.household_id,
        summary=summary,
    )
    approval.expires_at = datetime.now(timezone.utc) + APPROVAL_TTL
    bill.status = "pending_approval"
    return approval


async def propose_subscription_cancel(
    db: AsyncSession,
    *,
    membership: Membership,
    user: User,
    subscription_id: uuid.UUID,
    reason: str | None = None,
    conversation_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    subscription = await db.get(Subscription, subscription_id)
    if subscription is None or subscription.household_id != membership.household.id:
        raise ProposalError("That subscription doesn't exist in this household.")
    if subscription.status != "active":
        raise ProposalError(f"That subscription is already {subscription.status}.")
    if subscription.kind != "subscription":
        raise ProposalError(
            f"{subscription.merchant_name} looks like an essential bill (utility, insurance, rent), not a subscription. "
            "Warden doesn't cancel those."
        )
    existing = await _pending_for(db, subscription.household_id, "subscription_id", str(subscription.id))
    if existing is not None:
        return existing
    summary = f"Cancel {subscription.merchant_name} (${subscription.last_amount:,.2f} every {subscription.cadence_days} days)" + (
        f" — {reason}" if reason else ""
    )
    approval = await gate.request_approval(
        db,
        user_id=user.id,
        agent_id="warden",
        action_type="subscription_cancel",
        payload={
            "subscription_id": str(subscription.id),
            "merchant": subscription.merchant_name,
            "amount": str(subscription.last_amount),
            "cadence_days": subscription.cadence_days,
            "requested_by": membership.member.display_name,
            "reason": reason,
        },
        conversation_id=conversation_id,
        household_id=subscription.household_id,
        summary=summary,
    )
    approval.expires_at = datetime.now(timezone.utc) + APPROVAL_TTL
    return approval


async def notify_requested(db: AsyncSession, approval: ApprovalRequest) -> None:
    """Call after commit. Approvers are asked; the elder is told."""
    household = await db.get(Household, approval.household_id)
    name = household.name if household else "the household"
    link = f"{get_settings().web_app_url.rstrip('/')}/approvals"
    approvers = [m.email for m in await members_with_scope(db, approval.household_id, SCOPE_APPROVE_ACTIONS)]
    await notify.notify_people(
        approvers,
        f"Warden needs your OK: {approval.summary}",
        f"{approval.payload.get('requested_by', 'Someone')} asked Warden to do this for {name}:\n"
        f"{approval.summary}\n"
        "Nothing happens until you approve. If it looks wrong, block it.",
        link=link,
    )
    elder_emails = [m.email for m in await elders(db, approval.household_id)]
    await notify.notify_people(
        elder_emails,
        f"Warden asked your family to approve: {approval.summary}",
        f"Warden sent this to your family approver before doing anything:\n{approval.summary}\n"
        "If you didn't ask for this, open Warden and block it.",
        link=link,
    )


async def post_event(db: AsyncSession, conversation_id: uuid.UUID | None, text: str) -> None:
    """Drop a Warden event into the conversation that asked for the action,
    so the chat (and the model, on its next turn) sees what happened."""
    if conversation_id is None:
        return
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        return
    db.add(
        Message(
            conversation_id=conversation_id,
            role="system",
            agent_id="warden",
            content=text,
            api_content=[{"type": "text", "text": f"<warden_event>{text}</warden_event>"}],
        )
    )


def can_approve(membership: Membership) -> bool:
    return membership.has(SCOPE_APPROVE_ACTIONS)


def can_block(membership: Membership) -> bool:
    return membership.is_elder or membership.has(SCOPE_APPROVE_ACTIONS)


async def resolve(
    db: AsyncSession,
    *,
    approval_id: uuid.UUID,
    user: User,
    membership_for,  # async (household_id) -> Membership, raises 404 if not a member
    approve: bool,
    note: str | None = None,
) -> ApprovalRequest:
    # populate_existing: the row may already be in this session's identity
    # map (the router loaded it); without it, a second approver racing the
    # first would see the stale "pending" status after waiting on the lock.
    approval = (
        await db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if approval is None or approval.household_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    membership: Membership = await membership_for(approval.household_id)

    if approve and not can_approve(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a family approver the account owner has authorized can approve this.",
        )
    if not approve and not can_block(membership):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can't block this request.")
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Already {approval.status.value}.")

    now = datetime.now(timezone.utc)
    who = membership.member.display_name
    if approval.expires_at and approval.expires_at < now:
        approval.status = ApprovalStatus.expired
        approval.resolved_at = now
        await _release_bill(db, approval)
        await audit.record(
            db, event_type="approval.expired", agent_id="warden", household_id=approval.household_id,
            detail={"approval_id": str(approval.id), "summary": approval.summary},
        )
        await post_event(db, approval.conversation_id, f"Request expired without a decision: {approval.summary}. Nothing was done.")
        await db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This request expired. Ask Warden again if it's still needed.")

    approval.status = ApprovalStatus.approved if approve else ApprovalStatus.denied
    approval.resolved_at = now
    approval.resolved_by_user_id = user.id
    approval.resolution_note = note
    await audit.record(
        db,
        event_type=f"approval.{approval.status.value}",
        user_id=user.id,
        agent_id=approval.agent_id,
        household_id=approval.household_id,
        detail={"approval_id": str(approval.id), "summary": approval.summary, "by": who, "note": note},
    )

    if not approve:
        await _release_bill(db, approval)
        await post_event(db, approval.conversation_id, f"{who} blocked: {approval.summary}. Nothing was done.")
        await db.commit()
        await _notify_outcome(db, approval, f"{who} blocked: {approval.summary}", "Nothing was done.")
        return approval

    try:
        result = await execute(db, approval)
        approval.execution_result = result
        if result["status"] == "succeeded":
            text = f"{who} approved. Done: {approval.summary}. Stripe payment {result['stripe_payment_intent']}" + (
                " (test mode)." if not result.get("livemode") else "."
            )
        elif result["status"] == "processing":
            text = f"{who} approved. Payment started and is processing: {approval.summary}."
        else:
            text = f"{who} approved. {approval.summary}: {result.get('next_step', '')}"
    except ExecutionError as exc:
        approval.execution_result = {"status": "failed", "error": str(exc)}
        await _fail_bill(db, approval)
        text = f"{who} approved, but it could not be completed: {exc} No money moved."
        await audit.record(
            db, event_type="execution.failed", agent_id="warden", household_id=approval.household_id,
            detail={"approval_id": str(approval.id), "error": str(exc)},
        )
    await post_event(db, approval.conversation_id, text)
    await db.commit()
    await _notify_outcome(db, approval, text.split(". ")[0] + ".", text)
    return approval


async def _release_bill(db: AsyncSession, approval: ApprovalRequest) -> None:
    if approval.action_type == "bill_payment":
        bill = await db.get(Bill, uuid.UUID(approval.payload["bill_id"]))
        if bill is not None and bill.status == "pending_approval":
            bill.status = "open"


async def _fail_bill(db: AsyncSession, approval: ApprovalRequest) -> None:
    """A failed execution must leave the bill retryable ("Ask to pay"
    again), not stuck behind an approval that will never run."""
    if approval.action_type == "bill_payment":
        bill = await db.get(Bill, uuid.UUID(approval.payload["bill_id"]))
        if bill is not None and bill.status in ("pending_approval", "processing"):
            bill.status = "failed"


async def _notify_outcome(db: AsyncSession, approval: ApprovalRequest, subject: str, body: str) -> None:
    emails = {m.email for m in await elders(db, approval.household_id)}
    emails.update(m.email for m in await members_with_scope(db, approval.household_id, SCOPE_APPROVE_ACTIONS))
    await notify.notify_people(sorted(emails), f"Warden: {subject}", body)
