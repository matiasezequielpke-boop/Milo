"""Household membership, invites, and consent — the access-control core.

Every Warden endpoint and agent tool that touches money data goes through
`require_member()` + `require_scope()` here. The rules:

- The elder always sees and controls their own household.
- An approver sees nothing — not balances, not transactions, not alerts —
  until the elder grants consent, and loses access the moment the elder
  revokes it. If the elder never consents, nothing irreversible can ever be
  approved, so nothing irreversible ever happens.
- Only approvers release gated actions (`approve_actions` scope). The elder
  is told about every one of them.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Consent, Household, HouseholdMember, MemberRole, MemberStatus, User

# What an approver can be granted. The elder picks; the consent screen
# explains each one in plain words (apps/web).
SCOPE_VIEW_ACCOUNTS = "view_accounts"
SCOPE_RECEIVE_ALERTS = "receive_alerts"
SCOPE_APPROVE_ACTIONS = "approve_actions"
ALL_SCOPES = (SCOPE_VIEW_ACCOUNTS, SCOPE_RECEIVE_ALERTS, SCOPE_APPROVE_ACTIONS)

# Bump when the consent screen's wording changes, so each Consent row
# records exactly what the elder agreed to.
CONSENT_TEXT_VERSION = "2026-10-v1"


@dataclass
class Membership:
    member: HouseholdMember
    household: Household
    scopes: frozenset[str]

    @property
    def is_elder(self) -> bool:
        return self.member.role == MemberRole.elder

    def has(self, scope: str) -> bool:
        return scope in self.scopes


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_invite_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_invite_token(token)


def invite_link(token: str) -> str:
    return f"{get_settings().web_app_url.rstrip('/')}/invite/{token}"


async def active_scopes(db: AsyncSession, member: HouseholdMember) -> frozenset[str]:
    if member.status != MemberStatus.active:
        return frozenset()
    if member.role == MemberRole.elder:
        # The elder controls their own data; they never approve their own
        # payments (that's what the approver is for), so no approve scope.
        return frozenset({SCOPE_VIEW_ACCOUNTS, SCOPE_RECEIVE_ALERTS})
    result = await db.execute(
        select(Consent.scopes).where(
            Consent.approver_member_id == member.id,
            Consent.household_id == member.household_id,
            Consent.revoked_at.is_(None),
        )
    )
    scopes: set[str] = set()
    for row in result.scalars():
        scopes.update(row)
    return frozenset(scopes)


async def get_membership(db: AsyncSession, household_id: uuid.UUID | str, user: User) -> Membership | None:
    try:
        hid = household_id if isinstance(household_id, uuid.UUID) else uuid.UUID(str(household_id))
    except ValueError:
        return None
    result = await db.execute(
        select(HouseholdMember, Household)
        .join(Household, Household.id == HouseholdMember.household_id)
        .where(
            HouseholdMember.household_id == hid,
            HouseholdMember.user_id == user.id,
            HouseholdMember.status == MemberStatus.active,
        )
    )
    row = result.first()
    if row is None:
        return None
    member, household = row
    return Membership(member=member, household=household, scopes=await active_scopes(db, member))


async def require_member(db: AsyncSession, household_id: uuid.UUID | str, user: User) -> Membership:
    membership = await get_membership(db, household_id, user)
    if membership is None:
        # 404, not 403: don't confirm a household exists to non-members.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household not found")
    return membership


def require_scope(membership: Membership, scope: str) -> None:
    if not membership.has(scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{membership.household.name} hasn't given you permission for this yet "
                f"({scope}). Only the account owner can grant it."
            ),
        )


def require_elder(membership: Membership) -> None:
    if not membership.is_elder:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the account owner can do this.",
        )


async def members_with_scope(db: AsyncSession, household_id: uuid.UUID, scope: str) -> list[HouseholdMember]:
    result = await db.execute(
        select(HouseholdMember).where(
            HouseholdMember.household_id == household_id, HouseholdMember.status == MemberStatus.active
        )
    )
    members = list(result.scalars())
    return [m for m in members if scope in await active_scopes(db, m)]


async def elders(db: AsyncSession, household_id: uuid.UUID) -> list[HouseholdMember]:
    result = await db.execute(
        select(HouseholdMember).where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.role == MemberRole.elder,
            HouseholdMember.status == MemberStatus.active,
        )
    )
    return list(result.scalars())


async def revoke_consents(db: AsyncSession, household_id: uuid.UUID, approver_member_id: uuid.UUID) -> int:
    result = await db.execute(
        select(Consent).where(
            Consent.household_id == household_id,
            Consent.approver_member_id == approver_member_id,
            Consent.revoked_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    count = 0
    for consent in result.scalars():
        consent.revoked_at = now
        count += 1
    return count
