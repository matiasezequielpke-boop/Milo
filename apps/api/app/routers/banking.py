"""Bank data for a household: connect (Plaid), sync, and read.

Read endpoints need the `view_accounts` scope (the elder always has it;
an approver only after consent). Resolving an alert as fraud blocks the
merchant as a payee, so Warden will refuse to ever propose paying them.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, monitoring, plaid_service
from app.db import get_db
from app.deps import get_current_user
from app.households import SCOPE_VIEW_ACCOUNTS, Membership, elders, require_member, require_scope
from app.models import (
    Alert,
    AlertStatus,
    BankAccount,
    BankConnection,
    BankTransaction,
    Bill,
    Payee,
    Subscription,
    User,
)
from app.schemas import (
    AlertResolveRequest,
    AlertResponse,
    BankAccountResponse,
    BillCreateRequest,
    BillResponse,
    PlaidExchangeRequest,
    PlaidLinkTokenResponse,
    SandboxTransactionRequest,
    SubscriptionResponse,
    SyncResult,
    TransactionResponse,
)

router = APIRouter(prefix="/households/{household_id}", tags=["banking"])


def _plaid_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, plaid_service.PlaidNotConfiguredError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, plaid_service.PlaidSandboxOnlyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


async def _viewer(db: AsyncSession, household_id: uuid.UUID, user: User) -> Membership:
    membership = await require_member(db, household_id, user)
    require_scope(membership, SCOPE_VIEW_ACCOUNTS)
    return membership


async def _owner(db: AsyncSession, household_id: uuid.UUID):
    owners = await elders(db, household_id)
    if not owners:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The account owner hasn't joined yet. Bank accounts are connected for them, with their consent.",
        )
    return owners[0]


async def sync_household(db: AsyncSession, household_id: uuid.UUID) -> SyncResult:
    result = await db.execute(
        select(BankConnection).where(BankConnection.household_id == household_id, BankConnection.status == "active")
    )
    connections = list(result.scalars())
    totals = {"accounts": 0, "added": 0, "modified": 0, "removed": 0}
    for connection in connections:
        counts = await plaid_service.sync_connection(db, connection)
        for key in totals:
            totals[key] += getattr(counts, key)
    new_alerts = await monitoring.run_detection(db, household_id)
    await audit.record(
        db,
        event_type="bank.synced",
        agent_id="sentinel",
        household_id=household_id,
        detail={**totals, "new_alerts": len(new_alerts)},
    )
    await db.commit()
    await monitoring.notify_alerts(db, household_id, new_alerts)
    return SyncResult(connections=len(connections), new_alerts=len(new_alerts), **totals)


# --- Plaid connect -----------------------------------------------------------


@router.post("/plaid/link-token", response_model=PlaidLinkTokenResponse)
async def plaid_link_token(
    household_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> PlaidLinkTokenResponse:
    await _viewer(db, household_id, current_user)
    await _owner(db, household_id)
    try:
        data = await plaid_service.create_link_token(client_user_id=str(current_user.id))
    except (plaid_service.PlaidNotConfiguredError, plaid_service.PlaidApiError) as exc:
        raise _plaid_http_error(exc) from exc
    return PlaidLinkTokenResponse(link_token=data["link_token"], expiration=data.get("expiration"))


async def _connect(
    db: AsyncSession, household_id: uuid.UUID, user: User, public_token: str, institution_name: str | None
) -> SyncResult:
    owner = await _owner(db, household_id)
    try:
        await plaid_service.connect_item(
            db,
            household_id=household_id,
            owner=owner,
            linked_by=user,
            public_token=public_token,
            institution_name=institution_name,
        )
        await db.flush()
        return await sync_household(db, household_id)
    except (plaid_service.PlaidNotConfiguredError, plaid_service.PlaidApiError) as exc:
        await db.rollback()
        raise _plaid_http_error(exc) from exc


@router.post("/plaid/exchange", response_model=SyncResult, status_code=status.HTTP_201_CREATED)
async def plaid_exchange(
    household_id: uuid.UUID,
    body: PlaidExchangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SyncResult:
    await _viewer(db, household_id, current_user)
    return await _connect(db, household_id, current_user, body.public_token, body.institution_name)


@router.post("/plaid/sandbox-connect", response_model=SyncResult, status_code=status.HTTP_201_CREATED)
async def plaid_sandbox_connect(
    household_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> SyncResult:
    """Sandbox only: connects Plaid's test bank without the Link widget."""
    await _viewer(db, household_id, current_user)
    try:
        public_token = await plaid_service.sandbox_public_token()
    except (plaid_service.PlaidNotConfiguredError, plaid_service.PlaidApiError, plaid_service.PlaidSandboxOnlyError) as exc:
        raise _plaid_http_error(exc) from exc
    return await _connect(db, household_id, current_user, public_token, "First Platypus Bank (Plaid sandbox)")


@router.post("/plaid/sandbox-transactions", response_model=SyncResult)
async def plaid_sandbox_transaction(
    household_id: uuid.UUID,
    body: SandboxTransactionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SyncResult:
    """Sandbox only: adds a transaction at Plaid's test bank (e.g. a gift
    card purchase) and syncs, so the detection → alert → approval flow can
    be demonstrated end to end on real Plaid API responses."""
    await _viewer(db, household_id, current_user)
    result = await db.execute(
        select(BankConnection).where(BankConnection.household_id == household_id, BankConnection.status == "active")
    )
    connection = result.scalars().first()
    if connection is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Connect a sandbox bank first.")
    try:
        token = await plaid_service.access_token_for(db, connection)
        await plaid_service.sandbox_add_transactions(
            token,
            [{"description": body.description, "amount": body.amount, "date": body.date or date.today()}],
        )
        return await sync_household(db, household_id)
    except (plaid_service.PlaidNotConfiguredError, plaid_service.PlaidApiError, plaid_service.PlaidSandboxOnlyError) as exc:
        raise _plaid_http_error(exc) from exc


@router.post("/sync", response_model=SyncResult)
async def sync(
    household_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> SyncResult:
    await _viewer(db, household_id, current_user)
    try:
        return await sync_household(db, household_id)
    except (plaid_service.PlaidNotConfiguredError, plaid_service.PlaidApiError) as exc:
        raise _plaid_http_error(exc) from exc


# --- Read ------------------------------------------------------------------------


@router.get("/accounts", response_model=list[BankAccountResponse])
async def list_accounts(
    household_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[BankAccountResponse]:
    await _viewer(db, household_id, current_user)
    result = await db.execute(
        select(BankAccount, BankConnection.institution_name)
        .join(BankConnection, BankConnection.id == BankAccount.connection_id)
        .where(BankAccount.household_id == household_id)
        .order_by(BankAccount.name)
    )
    return [
        BankAccountResponse(
            id=a.id,
            name=a.name,
            mask=a.mask,
            type=a.type,
            subtype=a.subtype,
            current_balance=a.current_balance,
            available_balance=a.available_balance,
            currency=a.currency,
            institution_name=institution,
        )
        for a, institution in result.all()
    ]


def _txn(t: BankTransaction) -> TransactionResponse:
    return TransactionResponse(
        id=t.id,
        account_id=t.account_id,
        amount=t.amount,
        currency=t.currency,
        date=t.date,
        name=t.name,
        merchant_name=t.merchant_name,
        category=t.category,
        pending=t.pending,
    )


@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    household_id: uuid.UUID,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TransactionResponse]:
    await _viewer(db, household_id, current_user)
    since = date.today() - timedelta(days=max(1, min(days, 730)))
    result = await db.execute(
        select(BankTransaction)
        .where(
            BankTransaction.household_id == household_id,
            BankTransaction.removed.is_(False),
            BankTransaction.date >= since,
        )
        .order_by(BankTransaction.date.desc(), BankTransaction.created_at.desc())
        .limit(500)
    )
    return [_txn(t) for t in result.scalars()]


def _alert(alert: Alert, txn: BankTransaction | None) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        kind=alert.kind,
        severity=alert.severity,
        title=alert.title,
        reasons=alert.reasons,
        status=alert.status.value,
        transaction=_txn(txn) if txn else None,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
    )


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    household_id: uuid.UUID,
    status_filter: str | None = "open",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertResponse]:
    await _viewer(db, household_id, current_user)
    query = (
        select(Alert, BankTransaction)
        .outerjoin(BankTransaction, BankTransaction.id == Alert.transaction_id)
        .where(Alert.household_id == household_id)
    )
    if status_filter and status_filter != "all":
        if status_filter not in AlertStatus.__members__:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown status {status_filter!r}.")
        query = query.where(Alert.status == AlertStatus(status_filter))
    result = await db.execute(query.order_by(Alert.created_at.desc()).limit(200))
    return [_alert(a, t) for a, t in result.all()]


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    household_id: uuid.UUID,
    alert_id: uuid.UUID,
    body: AlertResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertResponse:
    membership = await _viewer(db, household_id, current_user)
    result = await db.execute(
        select(Alert, BankTransaction)
        .outerjoin(BankTransaction, BankTransaction.id == Alert.transaction_id)
        .where(Alert.id == alert_id, Alert.household_id == household_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert, txn = row
    if alert.status != AlertStatus.open:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Alert already {alert.status.value}.")
    alert.status = AlertStatus(body.resolution)
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by_user_id = current_user.id

    blocked_payee = None
    if alert.status == AlertStatus.confirmed_fraud and txn is not None:
        # Warden can't stop a card charge at the bank (that needs the
        # bank's own controls — see docs/money-plan.md), but it can make
        # sure it never helps pay this merchant again.
        name = (txn.merchant_name or txn.name)[:200]
        existing = (
            await db.execute(select(Payee).where(Payee.household_id == household_id, Payee.name == name))
        ).scalar_one_or_none()
        if existing is None:
            existing = Payee(household_id=household_id, name=name, category="blocked")
            db.add(existing)
        existing.blocked = True
        blocked_payee = name

    await audit.record(
        db,
        event_type=f"alert.{body.resolution}",
        user_id=current_user.id,
        household_id=household_id,
        detail={
            "alert_id": str(alert.id),
            "title": alert.title,
            "by": membership.member.display_name,
            **({"blocked_payee": blocked_payee} if blocked_payee else {}),
        },
    )
    await db.commit()
    return _alert(alert, txn)


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    household_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[SubscriptionResponse]:
    await _viewer(db, household_id, current_user)
    result = await db.execute(
        select(Subscription).where(Subscription.household_id == household_id).order_by(Subscription.merchant_name)
    )
    return [
        SubscriptionResponse(
            id=s.id,
            merchant_name=s.merchant_name,
            kind=s.kind,
            average_amount=s.average_amount,
            last_amount=s.last_amount,
            cadence_days=s.cadence_days,
            charge_count=s.charge_count,
            last_charged_on=s.last_charged_on,
            status=s.status,
        )
        for s in result.scalars()
    ]


async def _bill_response(db: AsyncSession, bill: Bill) -> BillResponse:
    payee = await db.get(Payee, bill.payee_id)
    return BillResponse(
        id=bill.id,
        payee_name=payee.name if payee else "?",
        payee_blocked=bool(payee and payee.blocked),
        amount=bill.amount,
        currency=bill.currency,
        due_date=bill.due_date,
        reference=bill.reference,
        status=bill.status,
        created_at=bill.created_at,
    )


async def create_bill_record(
    db: AsyncSession, household_id: uuid.UUID, user: User, body: BillCreateRequest
) -> Bill:
    name = body.payee_name.strip()
    payee = (
        await db.execute(select(Payee).where(Payee.household_id == household_id, Payee.name == name))
    ).scalar_one_or_none()
    if payee is None:
        payee = Payee(household_id=household_id, name=name)
        db.add(payee)
        await db.flush()
    bill = Bill(
        household_id=household_id,
        payee_id=payee.id,
        amount=body.amount,
        due_date=body.due_date,
        reference=body.reference,
        status="open",
        created_by_user_id=user.id,
    )
    db.add(bill)
    await db.flush()
    await audit.record(
        db,
        event_type="bill.recorded",
        user_id=user.id,
        household_id=household_id,
        detail={"bill_id": str(bill.id), "payee": payee.name, "amount": str(bill.amount)},
    )
    return bill


@router.get("/bills", response_model=list[BillResponse])
async def list_bills(
    household_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[BillResponse]:
    await _viewer(db, household_id, current_user)
    result = await db.execute(
        select(Bill).where(Bill.household_id == household_id).order_by(Bill.created_at.desc()).limit(200)
    )
    return [await _bill_response(db, b) for b in result.scalars()]


@router.post("/bills", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
async def create_bill(
    household_id: uuid.UUID,
    body: BillCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillResponse:
    await _viewer(db, household_id, current_user)
    bill = await create_bill_record(db, household_id, current_user, body)
    await db.commit()
    return await _bill_response(db, bill)
