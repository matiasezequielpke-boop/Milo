"""The person's own account: export, notification emails, deletion, and
the unsubscribe link from emails.

Deleting an account removes:
- for an account owner: the whole household — bank links (also revoked at
  Plaid), accounts, transactions, alerts, bills, approvals, chats and the
  household's activity log;
- for a family approver: their access (consents revoked, membership
  removed, email scrubbed). The owner's activity log keeps the approver's
  name next to decisions already made — the owner needs that record —
  and says the person left;
- in every case: their chats, sessions and the sign-in account at
  Supabase.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, notify, plaid_service, supabase_auth
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import (
    Alert,
    ApprovalRequest,
    AuditLogEntry,
    AuthSession,
    BankAccount,
    BankConnection,
    BankTransaction,
    Bill,
    Consent,
    Conversation,
    Credential,
    CustomAgent,
    Household,
    HouseholdMember,
    LoginChallenge,
    MemberRole,
    MemberStatus,
    Message,
    Payee,
    Payment,
    Subscription,
    User,
)
from app.schemas import AccountDeleteRequest, NotificationSettings, UserResponse

router = APIRouter(tags=["account"])
logger = logging.getLogger(__name__)

# Internal values that mean nothing to the person and shouldn't leave the
# server (hashes, cursors, vault references, model replay blocks).
_PRIVATE = {"invite_token_hash", "sync_cursor", "credential_id", "encrypted_value", "dedupe_key", "api_content", "merchant_key"}


def _plain(value):
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _row(obj) -> dict:
    return {c.key: _plain(getattr(obj, c.key)) for c in obj.__table__.columns if c.key not in _PRIVATE}


async def _all(db: AsyncSession, model, *where) -> list[dict]:
    return [_row(r) for r in (await db.execute(select(model).where(*where))).scalars()]


@router.get("/me/export")
async def export_my_data(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> JSONResponse:
    """Everything Warden holds about the person, as JSON (right of access /
    portability). An account owner gets their household's financial data;
    an approver gets their own part of it (membership, consents, the
    requests and decisions they made)."""
    memberships = (
        await db.execute(select(HouseholdMember).where(HouseholdMember.user_id == user.id, HouseholdMember.status != MemberStatus.removed))
    ).scalars().all()
    households = []
    for m in memberships:
        hid = m.household_id
        household = await db.get(Household, hid)
        entry: dict = {"household": _row(household), "my_membership": _row(m)}
        if m.role == MemberRole.elder:
            entry.update(
                members=await _all(db, HouseholdMember, HouseholdMember.household_id == hid),
                consents=await _all(db, Consent, Consent.household_id == hid),
                bank_connections=await _all(db, BankConnection, BankConnection.household_id == hid),
                accounts=await _all(db, BankAccount, BankAccount.household_id == hid),
                transactions=await _all(db, BankTransaction, BankTransaction.household_id == hid),
                alerts=await _all(db, Alert, Alert.household_id == hid),
                subscriptions=await _all(db, Subscription, Subscription.household_id == hid),
                payees=await _all(db, Payee, Payee.household_id == hid),
                bills=await _all(db, Bill, Bill.household_id == hid),
                payments=await _all(db, Payment, Payment.household_id == hid),
                approvals=await _all(db, ApprovalRequest, ApprovalRequest.household_id == hid),
                agents=await _all(db, CustomAgent, CustomAgent.household_id == hid),
                activity=await _all(db, AuditLogEntry, AuditLogEntry.household_id == hid),
            )
        else:
            entry.update(
                consents_given_to_me=await _all(db, Consent, Consent.approver_member_id == m.id),
                agents_i_made=await _all(db, CustomAgent, CustomAgent.household_id == hid, CustomAgent.created_by_user_id == user.id),
                approvals_i_requested_or_decided=await _all(
                    db,
                    ApprovalRequest,
                    ApprovalRequest.household_id == hid,
                    (ApprovalRequest.user_id == user.id) | (ApprovalRequest.resolved_by_user_id == user.id),
                ),
            )
        households.append(entry)

    conversations = []
    for conv in (await db.execute(select(Conversation).where(Conversation.user_id == user.id))).scalars():
        messages = (await db.execute(select(Message).where(Message.conversation_id == conv.id).order_by(Message.seq))).scalars()
        conversations.append({**_row(conv), "messages": [_row(msg) for msg in messages]})

    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": _row(user),
        "households": households,
        "conversations": conversations,
        "account_activity": await _all(db, AuditLogEntry, AuditLogEntry.user_id == user.id, AuditLogEntry.household_id.is_(None)),
    }
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="warden-my-data.json"'})


@router.put("/me/notifications", response_model=UserResponse)
async def set_notifications(
    body: NotificationSettings, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> User:
    user.email_opt_out_at = None if body.email_notifications else (user.email_opt_out_at or datetime.now(timezone.utc))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/email/unsubscribe")
async def unsubscribe(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """The link in every notification email, and the target of mail apps'
    one-click unsubscribe (RFC 8058). No sign-in needed; idempotent. POST
    only, so link scanners that prefetch URLs don't unsubscribe anyone."""
    user_id = notify.read_unsubscribe_token(token)
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This unsubscribe link isn't valid.")
    if user.email_opt_out_at is None:
        user.email_opt_out_at = datetime.now(timezone.utc)
        await audit.record(db, event_type="email.unsubscribed", user_id=user.id, detail={})
        await db.commit()
    return {"status": "unsubscribed"}


async def _delete_household(db: AsyncSession, household: Household) -> list[str]:
    """Removes a household and everything in it. Returns problems that
    didn't stop the deletion (e.g. Plaid unreachable)."""
    problems: list[str] = []
    hid = household.id
    connections = (await db.execute(select(BankConnection).where(BankConnection.household_id == hid))).scalars().all()
    credential_ids = [c.credential_id for c in connections]
    for connection in connections:
        try:
            await plaid_service.remove_item(await plaid_service.access_token_for(db, connection))
        except Exception as exc:  # noqa: BLE001 — deletion must go on; reported back
            logger.warning("plaid item removal failed for %s: %s", connection.provider_item_id, exc)
            problems.append(f"Couldn't confirm with Plaid that the {connection.institution_name or 'bank'} link was removed.")
    await db.execute(delete(Payment).where(Payment.household_id == hid))
    await db.execute(delete(Bill).where(Bill.household_id == hid))
    await db.execute(delete(Payee).where(Payee.household_id == hid))
    await db.execute(delete(ApprovalRequest).where(ApprovalRequest.household_id == hid))
    await db.execute(delete(BankConnection).where(BankConnection.household_id == hid))
    if credential_ids:
        await db.execute(delete(Credential).where(Credential.id.in_(credential_ids)))
    await db.execute(delete(AuditLogEntry).where(AuditLogEntry.household_id == hid))
    await db.execute(delete(Conversation).where(Conversation.household_id == hid))
    await db.execute(delete(Household).where(Household.id == hid))
    return problems


async def _leave_household(db: AsyncSession, member: HouseholdMember, user: User) -> None:
    hid = member.household_id
    now = datetime.now(timezone.utc)
    consents = (await db.execute(select(Consent).where(Consent.approver_member_id == member.id, Consent.revoked_at.is_(None)))).scalars()
    for consent in consents:
        consent.revoked_at = now
    # A bank link this person set up belongs to the account owner's data;
    # hand the stored access to the owner instead of deleting their bank.
    owner = (
        await db.execute(
            select(HouseholdMember).where(HouseholdMember.household_id == hid, HouseholdMember.role == MemberRole.elder)
        )
    ).scalars().first()
    connections = (await db.execute(select(BankConnection).where(BankConnection.household_id == hid))).scalars()
    for connection in connections:
        credential = await db.get(Credential, connection.credential_id)
        if credential is not None and credential.user_id == user.id:
            if owner is not None and owner.user_id is not None:
                credential.user_id = owner.user_id
            else:
                try:
                    await plaid_service.remove_item(await plaid_service.access_token_for(db, connection))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("plaid item removal failed: %s", exc)
                await db.delete(connection)
                await db.flush()
                await db.delete(credential)
    # Agents this person made carry their own words; they go with them.
    await db.execute(delete(CustomAgent).where(CustomAgent.household_id == hid, CustomAgent.created_by_user_id == user.id))
    member.status = MemberStatus.removed
    member.user_id = None
    member.invite_token_hash = None
    member.email = f"deleted-{member.id.hex[:12]}@deleted.invalid"
    await audit.record(
        db, event_type="household.member_deleted_account", household_id=hid, detail={"name": member.display_name}
    )


@router.delete("/me")
async def delete_my_account(
    body: AccountDeleteRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    settings = get_settings()
    if settings.demo_mode and user.email.lower() in settings.demo_people:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The demo family can't be deleted.")

    # The Supabase sign-in account goes first: if that fails, nothing here
    # is deleted and the person can simply try again.
    has_supabase_login = (await db.execute(select(AuthSession.id).where(AuthSession.user_id == user.id).limit(1))).first()
    if has_supabase_login:
        try:
            await supabase_auth.delete_user(str(user.id))
        except supabase_auth.SupabaseAuthNotConfiguredError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account deletion isn't set up on this server yet (SUPABASE_SERVICE_ROLE_KEY). Email us and we'll do it by hand.",
            ) from exc
        except supabase_auth.SupabaseAuthError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Couldn't delete the sign-in account. Try again.") from exc

    problems: list[str] = []
    memberships = (await db.execute(select(HouseholdMember).where(HouseholdMember.user_id == user.id))).scalars().all()
    for member in memberships:
        household = await db.get(Household, member.household_id)
        if household is None:
            continue
        if member.role == MemberRole.elder:
            problems += await _delete_household(db, household)
        else:
            await _leave_household(db, member, user)
    await db.execute(delete(LoginChallenge).where(LoginChallenge.email == user.email.lower()))
    await db.execute(delete(AuditLogEntry).where(AuditLogEntry.user_id == user.id, AuditLogEntry.household_id.is_(None)))
    await db.execute(delete(User).where(User.id == user.id))
    await audit.record(db, event_type="account.deleted", detail={"households_closed": sum(m.role == MemberRole.elder for m in memberships)})
    await db.commit()
    return {"status": "deleted", "problems": problems}
