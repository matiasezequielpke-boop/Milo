"""Persisted, votable suggestions board.

Same rationale as waitlist.py: this was client-only state in the
prototype (frontend-design-system.md v6), seeded with four rows
explicitly labeled "Example". This router keeps that same distinction
— `is_example` — so seed content is never confused with real user
submissions once this is wired to real accounts.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import Suggestion, SuggestionVote, User
from app.schemas import SuggestionCreateRequest, SuggestionResponse

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


async def _to_response(db: AsyncSession, suggestion: Suggestion, current_user: User | None) -> SuggestionResponse:
    vote_count_result = await db.execute(
        select(func.count(SuggestionVote.id)).where(SuggestionVote.suggestion_id == suggestion.id)
    )
    votes = vote_count_result.scalar_one()

    voted_by_me = False
    if current_user is not None:
        mine = await db.execute(
            select(SuggestionVote).where(
                SuggestionVote.suggestion_id == suggestion.id,
                SuggestionVote.user_id == current_user.id,
            )
        )
        voted_by_me = mine.scalar_one_or_none() is not None

    return SuggestionResponse(
        id=suggestion.id,
        title=suggestion.title,
        description=suggestion.description,
        is_example=suggestion.is_example,
        votes=votes,
        voted_by_me=voted_by_me,
        created_at=suggestion.created_at,
    )


@router.get("", response_model=list[SuggestionResponse])
async def list_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> list[SuggestionResponse]:
    result = await db.execute(select(Suggestion).order_by(Suggestion.created_at.desc()))
    suggestions = result.scalars().all()
    return [await _to_response(db, s, current_user) for s in suggestions]


@router.post("", response_model=SuggestionResponse, status_code=status.HTTP_201_CREATED)
async def create_suggestion(
    body: SuggestionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SuggestionResponse:
    suggestion = Suggestion(
        author_user_id=current_user.id,
        title=body.title,
        description=body.description,
        is_example=False,
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    return await _to_response(db, suggestion, current_user)


@router.post("/{suggestion_id}/vote", response_model=SuggestionResponse)
async def vote(
    suggestion_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SuggestionResponse:
    result = await db.execute(select(Suggestion).where(Suggestion.id == suggestion_id))
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")

    # Pre-check rather than insert-and-catch-IntegrityError: voting twice
    # should be a plain no-op, and relying on a rollback to make it one
    # adds a failure mode (see app/db.py's pool_pre_ping note) for no
    # benefit — the race window between check and insert is irrelevant
    # here since a double vote is harmless even if it slipped through.
    existing_vote = await db.execute(
        select(SuggestionVote).where(
            SuggestionVote.suggestion_id == suggestion.id,
            SuggestionVote.user_id == current_user.id,
        )
    )
    if existing_vote.scalar_one_or_none() is None:
        db.add(SuggestionVote(suggestion_id=suggestion.id, user_id=current_user.id))
        await db.commit()
    return await _to_response(db, suggestion, current_user)
