"""Households: create, invite, accept, consent, and the shared audit log.

The person who sets Warden up is usually the adult child (the buyer),
but either side can start: `my_role` says which one I am, and `invite`
brings in the other. Nobody sees the elder's money until the elder has
joined and granted consent — see app/households.py for the rules.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, notify
from app.db import get_db
from app.deps import get_current_user
from app.households import (
    CONSENT_TEXT_VERSION,
    SCOPE_VIEW_ACCOUNTS,
    Membership,
    active_scopes,
    hash_invite_token,
    invite_link,
    new_invite_token,
    require_elder,
    require_member,
    require_scope,
    revoke_consents,
)
from app.models import AuditLogEntry, Consent, Household, HouseholdMember, MemberRole, MemberStatus, User
from app.schemas import (
    AuditEntryResponse,
    ConsentGrantRequest,
    ConsentResponse,
    HouseholdCreateRequest,
    HouseholdCreateResponse,
    HouseholdResponse,
    InviteAcceptRequest,
    InvitePreviewResponse,
    InviteResult,
    MemberInvite,
    MemberResponse,
)

router = APIRouter(prefix="/households", tags=["households"])


async def _household_response(db: AsyncSession, household: Household, me: HouseholdMember) -> HouseholdResponse:
    members_result = await db.execute(
        select(HouseholdMember)
        .where(HouseholdMember.household_id == household.id, HouseholdMember.status != MemberStatus.removed)
        .order_by(HouseholdMember.invited_at)
    )
    consents_result = await db.execute(
        select(Consent).where(Consent.household_id == household.id).order_by(Consent.granted_at.desc())
    )
    members = []
    for m in members_result.scalars():
        members.append(
            MemberResponse(
                id=m.id,
                email=m.email,
                display_name=m.display_name,
                role=m.role.value,
                status=m.status.value,
                is_me=m.id == me.id,
                scopes=sorted(await active_scopes(db, m)),
            )
        )
    return HouseholdResponse(
        id=household.id,
        name=household.name,
        my_member_id=me.id,
        my_role=me.role.value,
        my_scopes=sorted(await active_scopes(db, me)),
        members=members,
        consents=[
            ConsentResponse(
                id=c.id,
                approver_member_id=c.approver_member_id,
                scopes=c.scopes,
                text_version=c.text_version,
                granted_at=c.granted_at,
                revoked_at=c.revoked_at,
            )
            for c in consents_result.scalars()
        ],
        created_at=household.created_at,
    )


async def _invite(
    db: AsyncSession, household: Household, inviter: User, inviter_name: str, invite: MemberInvite
) -> tuple[HouseholdMember, str]:
    token, token_hash = new_invite_token()
    member = HouseholdMember(
        household_id=household.id,
        email=invite.email.lower(),
        display_name=invite.display_name,
        role=MemberRole(invite.role),
        status=MemberStatus.invited,
        invite_token_hash=token_hash,
    )
    db.add(member)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"{invite.email} is already part of this household."
        ) from exc
    await audit.record(
        db,
        event_type="household.member_invited",
        user_id=inviter.id,
        household_id=household.id,
        detail={"email": member.email, "role": member.role.value, "invited_by": inviter_name},
    )
    return member, token


async def _send_invite(member: HouseholdMember, household: Household, inviter_name: str, token: str) -> InviteResult:
    link = invite_link(token)
    if member.role == MemberRole.elder:
        body = (
            f"Hi {member.display_name},\n"
            f"{inviter_name} set up Warden for {household.name}. Warden watches your bank accounts for "
            "scams and odd charges, and it never moves money without a family member's approval.\n"
            "Nothing is shared until you say so. Open the link to see exactly what would be shared and decide."
        )
    else:
        body = (
            f"Hi {member.display_name},\n"
            f"{inviter_name} would like you to be the family approver on Warden for {household.name}. "
            "You'll be asked before any payment or cancellation happens, and alerted about suspicious charges."
        )
    emailed = await notify.notify_people([member.email], f"{inviter_name} invited you to Warden", body, link=link)
    return InviteResult(
        member=MemberResponse(
            id=member.id,
            email=member.email,
            display_name=member.display_name,
            role=member.role.value,
            status=member.status.value,
        ),
        invite_link=None if emailed else link,
        emailed=emailed,
    )


@router.post("", response_model=HouseholdCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_household(
    body: HouseholdCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HouseholdCreateResponse:
    if body.invite and body.invite.email.lower() == current_user.email.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite someone other than yourself.")
    if body.invite and body.my_role == "approver" and body.invite.role == "approver":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A household needs the account owner (elder) in it."
        )
    if body.my_role == "elder" and body.invite and body.invite.role == "elder":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite an approver, not a second owner.")

    household = Household(name=body.name, created_by_user_id=current_user.id)
    db.add(household)
    await db.flush()
    me = HouseholdMember(
        household_id=household.id,
        user_id=current_user.id,
        email=current_user.email.lower(),
        display_name=body.my_display_name,
        role=MemberRole(body.my_role),
        status=MemberStatus.active,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(me)
    await db.flush()
    await audit.record(
        db,
        event_type="household.created",
        user_id=current_user.id,
        household_id=household.id,
        detail={"name": household.name, "creator_role": body.my_role},
    )
    invited: tuple[HouseholdMember, str] | None = None
    if body.invite:
        invited = await _invite(db, household, current_user, body.my_display_name, body.invite)
    await db.commit()

    invite_result = None
    if invited:
        invite_result = await _send_invite(invited[0], household, body.my_display_name, invited[1])
    return HouseholdCreateResponse(household=await _household_response(db, household, me), invite=invite_result)


@router.get("", response_model=list[HouseholdResponse])
async def list_households(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[HouseholdResponse]:
    result = await db.execute(
        select(HouseholdMember, Household)
        .join(Household, Household.id == HouseholdMember.household_id)
        .where(HouseholdMember.user_id == current_user.id, HouseholdMember.status == MemberStatus.active)
        .order_by(Household.created_at)
    )
    return [await _household_response(db, household, member) for member, household in result.all()]


@router.get("/{household_id}", response_model=HouseholdResponse)
async def get_household(
    household_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> HouseholdResponse:
    membership = await require_member(db, household_id, current_user)
    return await _household_response(db, membership.household, membership.member)


@router.post("/{household_id}/members", response_model=InviteResult, status_code=status.HTTP_201_CREATED)
async def invite_member(
    household_id: uuid.UUID,
    body: MemberInvite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InviteResult:
    membership = await require_member(db, household_id, current_user)
    if body.role == "elder":
        existing = await db.execute(
            select(HouseholdMember).where(
                HouseholdMember.household_id == household_id,
                HouseholdMember.role == MemberRole.elder,
                HouseholdMember.status != MemberStatus.removed,
            )
        )
        if existing.first() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This household already has an owner.")
    member, token = await _invite(db, membership.household, current_user, membership.member.display_name, body)
    await db.commit()
    return await _send_invite(member, membership.household, membership.member.display_name, token)


async def _member_by_token(db: AsyncSession, token: str) -> tuple[HouseholdMember, Household]:
    result = await db.execute(
        select(HouseholdMember, Household)
        .join(Household, Household.id == HouseholdMember.household_id)
        .where(
            HouseholdMember.invite_token_hash == hash_invite_token(token),
            HouseholdMember.status == MemberStatus.invited,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This invite link is invalid or was already used.")
    return row[0], row[1]


@router.get("/invites/{token}", response_model=InvitePreviewResponse)
async def preview_invite(token: str, db: AsyncSession = Depends(get_db)) -> InvitePreviewResponse:
    """Unauthenticated on purpose: the invite page shows who invited you
    and for what *before* asking you to sign in."""
    member, household = await _member_by_token(db, token)
    return InvitePreviewResponse(
        household_name=household.name,
        invited_email=member.email,
        display_name=member.display_name,
        role=member.role.value,
    )


@router.post("/invites/accept", response_model=HouseholdResponse)
async def accept_invite(
    body: InviteAcceptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HouseholdResponse:
    member, household = await _member_by_token(db, body.token)
    if member.email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This invite is for {member.email}. Sign in with that email to accept it.",
        )
    member.user_id = current_user.id
    member.status = MemberStatus.active
    member.joined_at = datetime.now(timezone.utc)
    member.invite_token_hash = None  # single use
    await audit.record(
        db,
        event_type="household.member_joined",
        user_id=current_user.id,
        household_id=household.id,
        detail={"email": member.email, "role": member.role.value},
    )
    await db.commit()
    return await _household_response(db, household, member)


async def _approver_member(db: AsyncSession, membership: Membership, member_id: uuid.UUID) -> HouseholdMember:
    result = await db.execute(
        select(HouseholdMember).where(
            HouseholdMember.id == member_id,
            HouseholdMember.household_id == membership.household.id,
            HouseholdMember.role == MemberRole.approver,
            HouseholdMember.status != MemberStatus.removed,
        )
    )
    approver = result.scalar_one_or_none()
    if approver is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approver not found in this household.")
    return approver


@router.post("/{household_id}/consents", response_model=HouseholdResponse, status_code=status.HTTP_201_CREATED)
async def grant_consent(
    household_id: uuid.UUID,
    body: ConsentGrantRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HouseholdResponse:
    membership = await require_member(db, household_id, current_user)
    require_elder(membership)
    approver = await _approver_member(db, membership, body.approver_member_id)
    scopes = sorted(set(body.scopes))
    if "approve_actions" in scopes and SCOPE_VIEW_ACCOUNTS not in scopes:
        # Approving a payment you can't see the context of isn't consent.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approving actions requires also seeing the accounts.",
        )
    # Replace, don't merge: the latest grant is exactly what's allowed now.
    await revoke_consents(db, membership.household.id, approver.id)
    db.add(
        Consent(
            household_id=membership.household.id,
            elder_member_id=membership.member.id,
            approver_member_id=approver.id,
            scopes=scopes,
            text_version=CONSENT_TEXT_VERSION,
        )
    )
    await audit.record(
        db,
        event_type="consent.granted",
        user_id=current_user.id,
        household_id=membership.household.id,
        detail={"approver": approver.display_name, "scopes": scopes, "text_version": CONSENT_TEXT_VERSION},
    )
    await db.commit()
    if approver.status == MemberStatus.active:
        await notify.notify_people(
            [approver.email],
            f"{membership.member.display_name} gave you access on Warden",
            f"{membership.member.display_name} allowed you to: {', '.join(s.replace('_', ' ') for s in scopes)}.",
        )
    return await _household_response(db, membership.household, membership.member)


@router.post("/{household_id}/consents/{approver_member_id}/revoke", response_model=HouseholdResponse)
async def revoke_consent(
    household_id: uuid.UUID,
    approver_member_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HouseholdResponse:
    membership = await require_member(db, household_id, current_user)
    require_elder(membership)
    approver = await _approver_member(db, membership, approver_member_id)
    revoked = await revoke_consents(db, membership.household.id, approver.id)
    await audit.record(
        db,
        event_type="consent.revoked",
        user_id=current_user.id,
        household_id=membership.household.id,
        detail={"approver": approver.display_name, "consents_revoked": revoked},
    )
    await db.commit()
    return await _household_response(db, membership.household, membership.member)


@router.get("/{household_id}/audit", response_model=list[AuditEntryResponse])
async def household_audit(
    household_id: uuid.UUID,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AuditEntryResponse]:
    """The family-shared log: who asked for what, who approved or blocked
    it, and what Warden executed. Entries carry payees and amounts, so an
    approver needs the elder's view_accounts consent to read it, same as
    the accounts themselves."""
    membership = await require_member(db, household_id, current_user)
    require_scope(membership, SCOPE_VIEW_ACCOUNTS)
    result = await db.execute(
        select(AuditLogEntry, User.email)
        .outerjoin(User, User.id == AuditLogEntry.user_id)
        .where(AuditLogEntry.household_id == household_id)
        .order_by(AuditLogEntry.id.desc())
        .limit(max(1, min(limit, 500)))
    )
    return [
        AuditEntryResponse(
            id=entry.id,
            event_type=entry.event_type,
            agent_id=entry.agent_id,
            actor=email,
            detail=entry.detail,
            created_at=entry.created_at,
        )
        for entry, email in result.all()
    ]
