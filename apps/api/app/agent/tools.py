"""The tools Milo can call. Read tools look things up for the household the
conversation belongs to; the two money tools only *propose* — they create
an approval request through app/warden.py and return. Nothing here can
execute a payment or a cancellation; that only happens in app/executor.py
after a human approves.

Every handler re-checks the speaker's permission (consent can be revoked
mid-conversation) and validates its input with pydantic before running —
the model's tool input is untrusted until validated.

Tool definitions are a fixed, ordered list so the request prefix (and the
prompt cache) stays stable across turns.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import warden
from app.households import SCOPE_APPROVE_ACTIONS, SCOPE_VIEW_ACCOUNTS, Membership, active_scopes, members_with_scope
from app.models import (
    Alert,
    AlertStatus,
    ApprovalRequest,
    ApprovalStatus,
    BankAccount,
    BankConnection,
    BankTransaction,
    Bill,
    HouseholdMember,
    MemberStatus,
    Payee,
    Subscription,
    User,
)
from app.routers.banking import create_bill_record
from app.schemas import BillCreateRequest


@dataclass
class ToolContext:
    db: AsyncSession
    user: User
    membership: Membership
    conversation_id: uuid.UUID
    # Approval requests created during this turn — the runner announces
    # them to the UI and notifies approvers after commit.
    created_approvals: list[ApprovalRequest]


class ToolError(Exception):
    """Returned to the model as an is_error tool_result, in plain words."""


def _money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoInput(_Input):
    pass


class ListTransactionsInput(_Input):
    days: int = Field(default=30, ge=1, le=365)
    merchant: str | None = Field(default=None, max_length=100)
    min_amount: Decimal | None = Field(default=None, ge=0)


class ListAlertsInput(_Input):
    status: str = Field(default="open", pattern="^(open|all)$")


class ListApprovalsInput(_Input):
    status: str = Field(default="pending", pattern="^(pending|all)$")


class RecordBillInput(_Input):
    payee_name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, le=Decimal("100000"), decimal_places=2)
    due_date: date | None = None
    reference: str | None = Field(default=None, max_length=200)


class RequestBillPaymentInput(_Input):
    bill_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=300)


class RequestCancellationInput(_Input):
    subscription_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=300)


def _require_view(ctx: ToolContext) -> None:
    if not ctx.membership.has(SCOPE_VIEW_ACCOUNTS):
        raise ToolError(
            "This person can't see the accounts yet: the account owner hasn't granted them permission. "
            "The owner can do that on the Family page."
        )


async def get_overview(ctx: ToolContext, _: NoInput) -> dict:
    db, hid = ctx.db, ctx.membership.household.id
    members = []
    for m in (await db.execute(select(HouseholdMember).where(HouseholdMember.household_id == hid))).scalars():
        if m.status == MemberStatus.removed:
            continue
        members.append(
            {
                "name": m.display_name,
                "role": m.role.value,
                "status": m.status.value,
                "permissions": sorted(await active_scopes(db, m)),
            }
        )
    overview: dict = {"household": ctx.membership.household.name, "members": members}
    if not ctx.membership.has(SCOPE_VIEW_ACCOUNTS):
        overview["accounts"] = "not visible to this person (no permission from the owner yet)"
        return overview
    accounts = await db.execute(
        select(BankAccount, BankConnection.institution_name)
        .join(BankConnection, BankConnection.id == BankAccount.connection_id)
        .where(BankAccount.household_id == hid)
        .order_by(BankAccount.name)
    )
    overview["accounts"] = [
        {
            "name": a.name,
            "bank": inst,
            "last4": a.mask,
            "type": a.subtype or a.type,
            "current_balance": _money(a.current_balance),
            "available_balance": _money(a.available_balance),
            "currency": a.currency,
        }
        for a, inst in accounts.all()
    ]
    overview["open_alerts"] = (
        await db.execute(select(func.count()).select_from(Alert).where(Alert.household_id == hid, Alert.status == AlertStatus.open))
    ).scalar_one()
    overview["pending_approvals"] = (
        await db.execute(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(ApprovalRequest.household_id == hid, ApprovalRequest.status == ApprovalStatus.pending)
        )
    ).scalar_one()
    overview["open_bills"] = (
        await db.execute(
            select(func.count()).select_from(Bill).where(Bill.household_id == hid, Bill.status.in_(["open", "failed"]))
        )
    ).scalar_one()
    if not overview["accounts"]:
        overview["note"] = "No bank account is connected yet. It can be connected from the Accounts page."
    return overview


async def list_transactions(ctx: ToolContext, args: ListTransactionsInput) -> dict:
    _require_view(ctx)
    query = select(BankTransaction).where(
        BankTransaction.household_id == ctx.membership.household.id,
        BankTransaction.removed.is_(False),
        BankTransaction.date >= date.today() - timedelta(days=args.days),
    )
    if args.merchant:
        like = f"%{args.merchant.lower()}%"
        query = query.where(
            func.lower(BankTransaction.name).like(like) | func.lower(func.coalesce(BankTransaction.merchant_name, "")).like(like)
        )
    if args.min_amount is not None:
        query = query.where(BankTransaction.amount >= args.min_amount)
    rows = (await ctx.db.execute(query.order_by(BankTransaction.date.desc()).limit(60))).scalars().all()
    return {
        "note": "Positive amount = money out of the account; negative = money in.",
        "count": len(rows),
        "transactions": [
            {
                "date": t.date.isoformat(),
                "description": t.name,
                "merchant": t.merchant_name,
                "amount": _money(t.amount),
                "pending": t.pending,
                "category": t.category,
            }
            for t in rows
        ],
    }


async def list_alerts(ctx: ToolContext, args: ListAlertsInput) -> dict:
    _require_view(ctx)
    query = (
        select(Alert, BankTransaction)
        .outerjoin(BankTransaction, BankTransaction.id == Alert.transaction_id)
        .where(Alert.household_id == ctx.membership.household.id)
    )
    if args.status == "open":
        query = query.where(Alert.status == AlertStatus.open)
    rows = (await ctx.db.execute(query.order_by(Alert.created_at.desc()).limit(30))).all()
    return {
        "alerts": [
            {
                "alert_id": str(a.id),
                "kind": a.kind,
                "severity": a.severity,
                "title": a.title,
                "why_flagged": a.reasons,
                "status": a.status.value,
                "charge": (
                    {"date": t.date.isoformat(), "description": t.name, "amount": _money(t.amount)} if t else None
                ),
            }
            for a, t in rows
        ]
    }


async def list_subscriptions(ctx: ToolContext, _: NoInput) -> dict:
    _require_view(ctx)
    rows = (
        await ctx.db.execute(
            select(Subscription)
            .where(Subscription.household_id == ctx.membership.household.id)
            .order_by(Subscription.merchant_name)
        )
    ).scalars()
    return {
        "subscriptions": [
            {
                "subscription_id": str(s.id),
                "merchant": s.merchant_name,
                "last_amount": _money(s.last_amount),
                "every_days": s.cadence_days,
                "times_charged": s.charge_count,
                "last_charged_on": s.last_charged_on.isoformat(),
                "status": s.status,
            }
            for s in rows
        ]
    }


async def list_bills(ctx: ToolContext, _: NoInput) -> dict:
    _require_view(ctx)
    rows = (
        await ctx.db.execute(
            select(Bill, Payee)
            .join(Payee, Payee.id == Bill.payee_id)
            .where(Bill.household_id == ctx.membership.household.id)
            .order_by(Bill.created_at.desc())
            .limit(40)
        )
    ).all()
    return {
        "bills": [
            {
                "bill_id": str(b.id),
                "payee": p.name,
                "payee_blocked": p.blocked,
                "amount": _money(b.amount),
                "due_date": b.due_date.isoformat() if b.due_date else None,
                "reference": b.reference,
                "status": b.status,
            }
            for b, p in rows
        ]
    }


async def list_approvals(ctx: ToolContext, args: ListApprovalsInput) -> dict:
    _require_view(ctx)
    query = select(ApprovalRequest).where(ApprovalRequest.household_id == ctx.membership.household.id)
    if args.status == "pending":
        query = query.where(ApprovalRequest.status == ApprovalStatus.pending)
    rows = (await ctx.db.execute(query.order_by(ApprovalRequest.requested_at.desc()).limit(20))).scalars()
    return {
        "approvals": [
            {
                "approval_id": str(a.id),
                "summary": a.summary,
                "status": a.status.value,
                "requested_by": a.payload.get("requested_by"),
                "outcome": (a.execution_result or {}).get("status"),
            }
            for a in rows
        ]
    }


async def record_bill(ctx: ToolContext, args: RecordBillInput) -> dict:
    _require_view(ctx)
    bill = await create_bill_record(
        ctx.db,
        ctx.membership.household.id,
        ctx.user,
        BillCreateRequest(
            payee_name=args.payee_name, amount=args.amount, due_date=args.due_date, reference=args.reference
        ),
    )
    payee = await ctx.db.get(Payee, bill.payee_id)
    result = {"bill_id": str(bill.id), "payee": payee.name, "amount": _money(bill.amount), "status": bill.status}
    if payee.blocked:
        result["warning"] = "This payee is blocked (a charge from them was marked as fraud). Warden will not pay it."
    return result


async def _propose(ctx: ToolContext, fn, **kwargs) -> dict:
    _require_view(ctx)
    try:
        approval = await fn(
            ctx.db, membership=ctx.membership, user=ctx.user, conversation_id=ctx.conversation_id, **kwargs
        )
    except warden.ProposalError as exc:
        raise ToolError(str(exc)) from exc
    ctx.created_approvals.append(approval)
    approvers = [m.display_name for m in await members_with_scope(ctx.db, ctx.membership.household.id, SCOPE_APPROVE_ACTIONS)]
    return {
        "approval_id": str(approval.id),
        "status": "pending — nothing has happened yet",
        "summary": approval.summary,
        "who_can_approve": approvers or "nobody yet: the owner hasn't authorized an approver, so this can't be approved until they do",
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
    }


async def request_bill_payment(ctx: ToolContext, args: RequestBillPaymentInput) -> dict:
    return await _propose(ctx, warden.propose_bill_payment, bill_id=args.bill_id, reason=args.reason)


async def request_subscription_cancellation(ctx: ToolContext, args: RequestCancellationInput) -> dict:
    return await _propose(
        ctx, warden.propose_subscription_cancel, subscription_id=args.subscription_id, reason=args.reason
    )


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[_Input]
    input_schema: dict
    handler: Callable[[ToolContext, _Input], Awaitable[dict]]
    # Shown in the chat while the tool runs ("Warden is checking ...").
    status_text: str
    agent: str = "milo"


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="get_overview",
        description="Household members and their permissions, connected bank accounts with balances, and counts of open alerts, pending approvals, and open bills. Start here when you need context.",
        input_model=NoInput,
        input_schema=_schema({}),
        handler=get_overview,
        status_text="Looking at the household",
    ),
    Tool(
        name="list_transactions",
        description="Recent bank transactions, newest first (max 60). Positive amounts are money out. Filter by days back, a merchant/description substring, or a minimum amount.",
        input_model=ListTransactionsInput,
        input_schema=_schema(
            {
                "days": {"type": "integer", "minimum": 1, "maximum": 365, "description": "How many days back. Default 30."},
                "merchant": {"type": "string", "description": "Case-insensitive text to match in the merchant or description."},
                "min_amount": {"type": "number", "minimum": 0, "description": "Only charges at least this large, in dollars."},
            }
        ),
        handler=list_transactions,
        status_text="Checking transactions",
    ),
    Tool(
        name="list_alerts",
        description="Charges Warden's monitor flagged (possible scams, large charges from new merchants, double charges, new subscriptions, price increases), with the reasons each was flagged.",
        input_model=ListAlertsInput,
        input_schema=_schema({"status": {"type": "string", "enum": ["open", "all"], "description": "Default open."}}),
        handler=list_alerts,
        status_text="Reviewing alerts",
        agent="sentinel",
    ),
    Tool(
        name="list_subscriptions",
        description="Recurring charges detected from the transaction history, with their subscription_id for cancellation requests.",
        input_model=NoInput,
        input_schema=_schema({}),
        handler=list_subscriptions,
        status_text="Checking subscriptions",
    ),
    Tool(
        name="list_bills",
        description="Bills recorded for this household and their status (open, pending_approval, processing, paid, failed), with bill_id for payment requests.",
        input_model=NoInput,
        input_schema=_schema({}),
        handler=list_bills,
        status_text="Checking bills",
    ),
    Tool(
        name="list_approvals",
        description="Approval requests Warden has sent to the family and what happened to them.",
        input_model=ListApprovalsInput,
        input_schema=_schema({"status": {"type": "string", "enum": ["pending", "all"], "description": "Default pending."}}),
        handler=list_approvals,
        status_text="Checking approvals",
        agent="warden",
    ),
    Tool(
        name="record_bill",
        description="Record a bill the household needs to pay (payee, amount, optional due date and account/reference number). This only records it; it does not pay anything.",
        input_model=RecordBillInput,
        input_schema=_schema(
            {
                "payee_name": {"type": "string", "description": "Who is owed, e.g. 'ConEd' or 'Dr. Patel's office'."},
                "amount": {"type": "number", "exclusiveMinimum": 0, "description": "Amount in dollars."},
                "due_date": {"type": "string", "format": "date", "description": "YYYY-MM-DD, if known."},
                "reference": {"type": "string", "description": "Account or invoice number on the bill, if given."},
            },
            ["payee_name", "amount"],
        ),
        handler=record_bill,
        status_text="Recording the bill",
        agent="warden",
    ),
    Tool(
        name="request_bill_payment",
        description="Ask the family approver to approve paying a recorded bill. Creates a pending approval request and notifies them; nothing is paid until a human approves in the app.",
        input_model=RequestBillPaymentInput,
        input_schema=_schema(
            {
                "bill_id": {"type": "string", "description": "From list_bills or record_bill."},
                "reason": {"type": "string", "description": "One short line of context for the approver."},
            },
            ["bill_id"],
        ),
        handler=request_bill_payment,
        status_text="Warden is asking the family to approve",
        agent="warden",
    ),
    Tool(
        name="request_subscription_cancellation",
        description="Ask the family approver to approve cancelling a recurring charge. Creates a pending approval request; after approval Warden prepares the cancellation request for a person to send.",
        input_model=RequestCancellationInput,
        input_schema=_schema(
            {
                "subscription_id": {"type": "string", "description": "From list_subscriptions."},
                "reason": {"type": "string", "description": "One short line of context for the approver."},
            },
            ["subscription_id"],
        ),
        handler=request_subscription_cancellation,
        status_text="Warden is asking the family to approve",
        agent="warden",
    ),
)

TOOLS_BY_NAME = {t.name: t for t in TOOLS}

# Request-shape tool definitions. eager_input_streaming lets inputs stream
# as they're generated; the trade-off is the server stops validating
# them, which is why every handler validates with pydantic first.
TOOL_DEFINITIONS: list[dict] = [
    {"name": t.name, "description": t.description, "input_schema": t.input_schema, "eager_input_streaming": True}
    for t in TOOLS
]


async def run_tool(ctx: ToolContext, name: str, raw_input: object) -> tuple[str, bool]:
    """Returns (content, is_error). Never raises for model mistakes — those
    go back to the model as an error result it can correct."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return f"Unknown tool {name!r}.", True
    try:
        args = tool.input_model.model_validate(raw_input if isinstance(raw_input, dict) else {})
    except ValidationError as exc:
        return json.dumps({"INVALID_INPUT": json.loads(exc.json(include_url=False))}), True
    try:
        result = await tool.handler(ctx, args)
    except ToolError as exc:
        return str(exc), True
    return json.dumps(result, default=str), False
