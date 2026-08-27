"""Persisted early-access waitlist.

Per claude/frontend-design-system.md (v6): email-only, no payment
gateway. Per claude/build-backlog.md's "orden sugerido", this is the
single highest-ROI item in the whole backlog — it was client-only
state in the prototype and reset on every page reload, silently
losing every real signup. This is the fix: same email-only capture,
now durable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import WaitlistSignup
from app.schemas import WaitlistSignupRequest, WaitlistSignupResponse

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


@router.post("", response_model=WaitlistSignupResponse)
async def join_waitlist(body: WaitlistSignupRequest, db: AsyncSession = Depends(get_db)) -> WaitlistSignupResponse:
    existing = await db.execute(select(WaitlistSignup).where(WaitlistSignup.email == body.email))
    row = existing.scalar_one_or_none()
    if row is not None:
        return WaitlistSignupResponse(email=row.email, created_at=row.created_at, already_on_list=True)

    signup = WaitlistSignup(email=body.email)
    db.add(signup)
    await db.commit()
    await db.refresh(signup)
    return WaitlistSignupResponse(email=signup.email, created_at=signup.created_at, already_on_list=False)


@router.get("/count")
async def waitlist_count(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(WaitlistSignup))
    return {"count": len(result.scalars().all())}
