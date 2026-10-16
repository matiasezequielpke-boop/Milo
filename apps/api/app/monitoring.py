"""Runs the detector over a household's transactions and persists what it
finds: new alerts (deduplicated), and the current set of recurring
charges. Then tells the family about anything new.

Called after every bank sync (app/plaid_service.py) — the "watch the
accounts" half of Warden. The detector itself is pure (app/detection.py).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, notify
from app.config import get_settings
from app.detection import Txn, detect
from app.households import SCOPE_RECEIVE_ALERTS, members_with_scope
from app.models import Alert, BankTransaction, Household, Subscription

# Enough history to know what's normal for this person and to see
# yearly subscriptions; the per-charge rules only look at the last 30 days.
HISTORY_DAYS = 400


async def run_detection(db: AsyncSession, household_id: uuid.UUID, *, today: date | None = None) -> list[Alert]:
    today = today or date.today()
    result = await db.execute(
        select(BankTransaction).where(
            BankTransaction.household_id == household_id,
            BankTransaction.removed.is_(False),
            BankTransaction.date >= today - timedelta(days=HISTORY_DAYS),
        )
    )
    rows = list(result.scalars())
    by_id = {str(r.id): r for r in rows}
    txns = [
        Txn(
            id=str(r.id),
            date=r.date,
            amount=r.amount,
            name=r.name,
            merchant_name=r.merchant_name,
            pending=r.pending,
            category=r.category,
        )
        for r in rows
    ]
    detection = detect(txns, today=today)

    new_alert_ids: list[uuid.UUID] = []
    for f in detection.findings:
        stmt = (
            pg_insert(Alert)
            .values(
                id=uuid.uuid4(),
                household_id=household_id,
                transaction_id=by_id[f.transaction_id].id if f.transaction_id in by_id else None,
                kind=f.kind,
                dedupe_key=f.dedupe_key,
                severity=f.severity,
                title=f.title,
                reasons=f.reasons,
                status="open",
            )
            .on_conflict_do_nothing(constraint="uq_alert_dedupe")
            .returning(Alert.id)
        )
        inserted = (await db.execute(stmt)).scalar_one_or_none()
        if inserted is not None:
            new_alert_ids.append(inserted)

    for s in detection.streams:
        stmt = pg_insert(Subscription).values(
            id=uuid.uuid4(),
            household_id=household_id,
            merchant_key=s.merchant_key,
            merchant_name=s.merchant_name,
            kind=s.kind,
            average_amount=s.average_amount,
            last_amount=s.last_amount,
            cadence_days=s.cadence_days,
            charge_count=s.charge_count,
            first_charged_on=s.first_date,
            last_charged_on=s.dates[-1],
            status="active",
        )
        await db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_subscription_merchant",
                set_={
                    "merchant_name": stmt.excluded.merchant_name,
                    "kind": stmt.excluded.kind,
                    "average_amount": stmt.excluded.average_amount,
                    "last_amount": stmt.excluded.last_amount,
                    "cadence_days": stmt.excluded.cadence_days,
                    "charge_count": stmt.excluded.charge_count,
                    "last_charged_on": stmt.excluded.last_charged_on,
                },
            )
        )

    if not new_alert_ids:
        return []
    alerts = list((await db.execute(select(Alert).where(Alert.id.in_(new_alert_ids)))).scalars())
    for alert in alerts:
        await audit.record(
            db,
            event_type="alert.raised",
            agent_id="sentinel",
            household_id=household_id,
            detail={"alert_id": str(alert.id), "kind": alert.kind, "severity": alert.severity, "title": alert.title},
        )
    return alerts


async def notify_alerts(db: AsyncSession, household_id: uuid.UUID, alerts: list[Alert]) -> None:
    """Medium and high alerts go out right away; low ones (a price
    increase) wait for the person to open the app."""
    urgent = [a for a in alerts if a.severity in ("medium", "high")]
    if not urgent:
        return
    household = await db.get(Household, household_id)
    recipients = [m.email for m in await members_with_scope(db, household_id, SCOPE_RECEIVE_ALERTS)]
    lines = [f"• {a.title}" for a in urgent[:5]]
    if len(urgent) > 5:
        lines.append(f"…and {len(urgent) - 5} more.")
    body = (
        f"Warden noticed something on {household.name if household else 'the account'} that's worth a look:\n"
        + "\n".join(lines)
        + "\nOpen Warden to mark each one as fine or as fraud."
    )
    await notify.notify_people(
        recipients,
        "Warden: please check a charge" if len(urgent) == 1 else f"Warden: {len(urgent)} charges to check",
        body,
        link=f"{get_settings().web_app_url.rstrip('/')}/alerts",
    )
