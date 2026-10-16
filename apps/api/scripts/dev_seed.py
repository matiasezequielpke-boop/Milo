"""Local development seed: one family with three months of bank history.

    APP_ENV=development python -m scripts.dev_seed

For working on the UI without Plaid keys (or without network to Plaid).
The transactions are written straight to the database and marked with
provider "dev-seed" — they are NOT Plaid data and this never runs outside
APP_ENV=development. Detection, alerts, and subscriptions are then produced
by the real detector (app/monitoring.py), exactly as after a Plaid sync.

Sign in with dev login as ana@example.com (approver) or rosa@example.com
(account owner).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app import vault
from app.config import get_settings
from app.db import SessionLocal
from app.households import ALL_SCOPES, CONSENT_TEXT_VERSION
from app.models import (
    BankAccount,
    BankConnection,
    BankTransaction,
    Bill,
    Consent,
    Credential,
    Household,
    HouseholdMember,
    MemberRole,
    MemberStatus,
    Payee,
    User,
)
from app.monitoring import run_detection

TODAY = date.today()


async def _user(db, email: str, name: str) -> User:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, display_name=name)
        db.add(user)
        await db.flush()
    return user


async def main() -> None:
    if get_settings().app_env != "development":
        raise SystemExit("dev_seed only runs with APP_ENV=development.")
    async with SessionLocal() as db:
        ana = await _user(db, "ana@example.com", "Ana")
        rosa = await _user(db, "rosa@example.com", "Rosa")
        household = Household(name="Rosa's accounts", created_by_user_id=ana.id)
        db.add(household)
        await db.flush()
        now = datetime.now(timezone.utc)
        ana_m = HouseholdMember(household_id=household.id, user_id=ana.id, email=ana.email, display_name="Ana",
                                role=MemberRole.approver, status=MemberStatus.active, joined_at=now)
        rosa_m = HouseholdMember(household_id=household.id, user_id=rosa.id, email=rosa.email, display_name="Rosa",
                                 role=MemberRole.elder, status=MemberStatus.active, joined_at=now)
        db.add_all([ana_m, rosa_m])
        await db.flush()
        db.add(Consent(household_id=household.id, elder_member_id=rosa_m.id, approver_member_id=ana_m.id,
                       scopes=list(ALL_SCOPES), text_version=CONSENT_TEXT_VERSION))
        cred = Credential(user_id=rosa.id, name=f"dev-seed:{uuid.uuid4()}", encrypted_value=vault.encrypt("dev-seed"))
        db.add(cred)
        await db.flush()
        conn = BankConnection(household_id=household.id, owner_member_id=rosa_m.id, provider="dev-seed",
                              provider_item_id=f"dev-seed-{uuid.uuid4()}", credential_id=cred.id,
                              institution_name="Dev seed bank (not Plaid)", status="seed")
        db.add(conn)
        await db.flush()
        acct = BankAccount(household_id=household.id, connection_id=conn.id, provider_account_id=f"dev-{uuid.uuid4()}",
                           name="Everyday Checking", mask="4412", type="depository", subtype="checking",
                           current_balance=Decimal("6240.18"), available_balance=Decimal("6140.18"))
        db.add(acct)
        await db.flush()

        rows: list[tuple[int, str, str | None, str]] = []
        for i in range(13):
            rows.append((3 + 7 * i, "SAFEWAY #1234", "Safeway", f"{58 + (i * 7) % 23}.{(i * 37) % 100:02d}"))
            rows.append((5 + 7 * i, "CVS PHARMACY 0042", "CVS", f"{12 + (i * 5) % 19}.49"))
        for i in range(4):
            rows.append((8 + 30 * i, "NETFLIX.COM", "Netflix", "15.49"))
            rows.append((12 + 30 * i, "CONED UTILITY PMT", "ConEd", f"{79 + i * 3}.20"))
            rows.append((15 + 30 * i, "SOCIAL SECURITY", None, "-2140.00"))
        for i in range(2):
            rows.append((4 + 30 * i, "PRIMEVIDEO TRIAL CONVERSION", "Prime Video", "14.99"))
        rows += [
            (1, "GIFT CARD MALL #3", None, "500.00"),
            (2, "TECH SUPPORT SERVICES LLC", "Tech Support Services", "349.99"),
        ]
        for i, (days_ago, name, merchant, amount) in enumerate(rows):
            db.add(BankTransaction(household_id=household.id, account_id=acct.id,
                                   provider_transaction_id=f"dev-seed-{uuid.uuid4()}", amount=Decimal(amount),
                                   date=TODAY - timedelta(days=days_ago), name=name, merchant_name=merchant))
        payee = Payee(household_id=household.id, name="ConEd")
        db.add(payee)
        await db.flush()
        db.add(Bill(household_id=household.id, payee_id=payee.id, amount=Decimal("88.20"),
                    due_date=TODAY + timedelta(days=9), reference="acct 4412-889", created_by_user_id=rosa.id))
        await db.flush()
        alerts = await run_detection(db, household.id)
        await db.commit()
        print(f"Seeded household {household.id} with {len(rows)} transactions; {len(alerts)} alerts raised by the detector.")


if __name__ == "__main__":
    asyncio.run(main())
