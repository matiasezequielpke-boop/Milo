"""Demo mode: a ready-made family so the product can be shown without
sign-in. Only mounted behaviour when DEMO_MODE is on (404 otherwise).

`POST /demo/bootstrap` is idempotent: it makes sure the two demo people
exist, that Rosa owns a household with Ana as her approver, and that Rosa
has granted Ana consent. It creates no bank data — accounts still come
from Plaid (sandbox), alerts from the real detector.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.config import get_settings
from app.db import get_db
from app.households import ALL_SCOPES, CONSENT_TEXT_VERSION, active_scopes
from app.models import Consent, Household, HouseholdMember, MemberRole, MemberStatus, User

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoPerson(BaseModel):
    email: str
    name: str
    role: str
    token: str


class DemoBootstrap(BaseModel):
    household_id: str
    household_name: str
    people: list[DemoPerson]


async def _user(db: AsyncSession, email: str, name: str) -> User:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, display_name=name)
        db.add(user)
        await db.flush()
    return user


@router.post("/bootstrap", response_model=DemoBootstrap)
async def bootstrap(db: AsyncSession = Depends(get_db)) -> DemoBootstrap:
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    owner_email, approver_email = settings.demo_owner_email.lower(), settings.demo_approver_email.lower()
    owner = await _user(db, owner_email, "Rosa")
    approver = await _user(db, approver_email, "Ana")

    row = (
        await db.execute(
            select(HouseholdMember, Household)
            .join(Household, Household.id == HouseholdMember.household_id)
            .where(
                HouseholdMember.user_id == owner.id,
                HouseholdMember.role == MemberRole.elder,
                HouseholdMember.status == MemberStatus.active,
            )
            .order_by(Household.created_at)
        )
    ).first()
    now = datetime.now(timezone.utc)
    if row is None:
        household = Household(name="Rosa's accounts", created_by_user_id=approver.id)
        db.add(household)
        await db.flush()
        elder_m = HouseholdMember(
            household_id=household.id, user_id=owner.id, email=owner_email, display_name="Rosa",
            role=MemberRole.elder, status=MemberStatus.active, joined_at=now,
        )
        db.add(elder_m)
        await db.flush()
        await audit.record(
            db, event_type="household.created", user_id=approver.id, household_id=household.id,
            detail={"name": household.name, "creator_role": "approver", "demo": True},
        )
    else:
        elder_m, household = row

    approver_m = (
        await db.execute(
            select(HouseholdMember).where(
                HouseholdMember.household_id == household.id, HouseholdMember.email == approver_email
            )
        )
    ).scalar_one_or_none()
    if approver_m is None:
        approver_m = HouseholdMember(
            household_id=household.id, user_id=approver.id, email=approver_email, display_name="Ana",
            role=MemberRole.approver, status=MemberStatus.active, joined_at=now,
        )
        db.add(approver_m)
        await db.flush()
        db.add(
            Consent(
                household_id=household.id, elder_member_id=elder_m.id, approver_member_id=approver_m.id,
                scopes=list(ALL_SCOPES), text_version=CONSENT_TEXT_VERSION,
            )
        )
        await audit.record(
            db, event_type="consent.granted", user_id=owner.id, household_id=household.id,
            detail={"approver": "Ana", "scopes": list(ALL_SCOPES), "text_version": CONSENT_TEXT_VERSION},
        )
    await db.commit()
    # Consent stays whatever Rosa last chose in the app; bootstrap never re-grants it.
    _ = await active_scopes(db, approver_m)
    return DemoBootstrap(
        household_id=str(household.id),
        household_name=household.name,
        people=[
            DemoPerson(email=owner_email, name="Rosa", role="elder", token=f"demo:{owner_email}"),
            DemoPerson(email=approver_email, name="Ana", role="approver", token=f"demo:{approver_email}"),
        ],
    )
