"""Runs an approved Warden action. Nothing else in the codebase moves money.

Only `app/warden.py:resolve()` calls `execute()`, and only after a family
approver has released the request — the model never reaches this module.
What runs is exactly what was approved: the payload is re-checked against
the live bill and payee before anything is sent to Stripe.

Payments (bill_payment)
    Stripe PaymentIntent, confirmed server-side. Warden never holds the
    money: when the payee has a Stripe Connect account the charge is a
    destination charge straight to them (`transfer_data.destination`).
    The approval id is the Stripe idempotency key, so a retry after a
    crash can never pay twice.

    MVP limits, on purpose:
    - Test mode only. A live key (sk_live_) is refused unless
      PAYMENTS_LIVE_ENABLED is set — that switch is for after the fintech
      legal review (docs/money-plan.md), not before.
    - The paying instrument is Stripe's test card until the elder's own
      bank account is attached as a payment method (Plaid → Stripe
      processor token, ACH debit). That's the production path.

Cancellations (subscription_cancel)
    There's no universal API to cancel a third-party subscription, so
    Warden doesn't pretend to. It marks the subscription, prepares the
    cancellation request for the family to send, and says so plainly.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.config import get_settings
from app.models import ApprovalRequest, Bill, Household, Payee, Payment, Subscription


class ExecutionError(RuntimeError):
    """The approved action could not run (and nothing was moved)."""


def _stripe_client() -> stripe.StripeClient:
    settings = get_settings()
    key = settings.stripe_secret_key
    if not key:
        raise ExecutionError("STRIPE_SECRET_KEY is not set — payments can't run until it is (free test keys: dashboard.stripe.com).")
    if key.startswith(("sk_live_", "rk_live_")) and not settings.payments_live_enabled:
        raise ExecutionError("Live Stripe keys are disabled until PAYMENTS_LIVE_ENABLED is turned on after legal review.")
    return stripe.StripeClient(key)


def _cents(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal("1")))


async def execute(db: AsyncSession, approval: ApprovalRequest) -> dict:
    if approval.action_type == "bill_payment":
        return await _pay_bill(db, approval)
    if approval.action_type == "subscription_cancel":
        return await _cancel_subscription(db, approval)
    raise ExecutionError(f"No executor for {approval.action_type!r}.")


async def _pay_bill(db: AsyncSession, approval: ApprovalRequest) -> dict:
    payload = approval.payload
    bill = await db.get(Bill, uuid.UUID(payload["bill_id"]), with_for_update=True)
    if bill is None or bill.household_id != approval.household_id:
        raise ExecutionError("The bill no longer exists.")
    if bill.status not in ("open", "pending_approval", "failed"):
        raise ExecutionError(f"The bill is already {bill.status}.")
    approved_amount = Decimal(payload["amount"])
    if bill.amount != approved_amount:
        raise ExecutionError(
            f"The bill changed after approval (approved ${approved_amount}, now ${bill.amount}). Ask again."
        )
    payee = await db.get(Payee, bill.payee_id)
    if payee is None or payee.blocked:
        raise ExecutionError("This payee is blocked — the family marked a charge from them as fraud.")

    client = _stripe_client()
    settings = get_settings()
    household = await db.get(Household, bill.household_id)

    payment = Payment(
        household_id=bill.household_id,
        bill_id=bill.id,
        approval_id=approval.id,
        amount=bill.amount,
        currency=bill.currency,
        provider="stripe",
        status="processing",
    )
    db.add(payment)
    await db.flush()

    params: dict = {
        "amount": _cents(bill.amount),
        "currency": bill.currency.lower(),
        "payment_method": settings.stripe_test_payment_method,
        "confirm": True,
        "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
        "description": f"Warden: {payee.name}" + (f" ({bill.reference})" if bill.reference else ""),
        "metadata": {
            "warden_household_id": str(bill.household_id),
            "warden_bill_id": str(bill.id),
            "warden_approval_id": str(approval.id),
            "household": household.name if household else "",
        },
    }
    if payee.stripe_account_id:
        params["transfer_data"] = {"destination": payee.stripe_account_id}

    try:
        intent = await asyncio.to_thread(
            client.v1.payment_intents.create,
            params,
            {"idempotency_key": f"warden-approval-{approval.id}"},
        )
    except stripe.StripeError as exc:
        message = getattr(exc, "user_message", None) or str(exc)
        payment.status = "failed"
        payment.error = message[:1000]
        bill.status = "failed"
        await audit.record(
            db,
            event_type="payment.failed",
            agent_id="warden",
            household_id=bill.household_id,
            detail={"approval_id": str(approval.id), "payee": payee.name, "amount": str(bill.amount), "error": message},
        )
        raise ExecutionError(f"Stripe declined the payment: {message}") from exc

    payment.provider_payment_id = intent.id
    payment.livemode = bool(intent.livemode)
    payment.status = "succeeded" if intent.status == "succeeded" else ("processing" if intent.status == "processing" else "failed")
    bill.status = {"succeeded": "paid", "processing": "processing"}.get(payment.status, "failed")
    await audit.record(
        db,
        event_type=f"payment.{payment.status}",
        agent_id="warden",
        household_id=bill.household_id,
        detail={
            "approval_id": str(approval.id),
            "payee": payee.name,
            "amount": str(bill.amount),
            "stripe_payment_intent": intent.id,
            "livemode": bool(intent.livemode),
        },
    )
    if payment.status == "failed":
        raise ExecutionError(f"Stripe returned status {intent.status!r}.")
    return {
        "status": payment.status,
        "payment_id": str(payment.id),
        "stripe_payment_intent": intent.id,
        "livemode": bool(intent.livemode),
        "amount": str(bill.amount),
        "payee": payee.name,
    }


async def _cancel_subscription(db: AsyncSession, approval: ApprovalRequest) -> dict:
    subscription = await db.get(Subscription, uuid.UUID(approval.payload["subscription_id"]), with_for_update=True)
    if subscription is None or subscription.household_id != approval.household_id:
        raise ExecutionError("The subscription no longer exists.")
    if subscription.status != "active":
        raise ExecutionError(f"The subscription is already {subscription.status}.")
    household = await db.get(Household, subscription.household_id)
    subscription.status = "cancel_requested"
    letter = (
        f"To {subscription.merchant_name} customer service,\n\n"
        f"Please cancel the recurring charge of ${subscription.last_amount} on this account, effective "
        f"immediately, and confirm the cancellation in writing. Do not renew or charge again.\n\n"
        f"Date: {date.today().isoformat()}\n"
        f"Account holder: {household.name if household else ''}"
    )
    await audit.record(
        db,
        event_type="subscription.cancel_requested",
        agent_id="warden",
        household_id=subscription.household_id,
        detail={"approval_id": str(approval.id), "merchant": subscription.merchant_name, "amount": str(subscription.last_amount)},
    )
    return {
        "status": "manual_step_required",
        "merchant": subscription.merchant_name,
        "cancellation_letter": letter,
        "next_step": (
            "Send this to the merchant (website, email, or phone). If they keep charging, the bank can "
            "block future charges from this merchant."
        ),
    }
