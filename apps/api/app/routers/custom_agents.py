"""Custom agents for a household: list, make, change, delete.

Anyone in the household who can see the accounts can make one (it reads
those accounts). The person who made it and the account owner can change
or delete it. Every change goes to the family's activity log.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit, custom_agents
from app.db import get_db
from app.deps import get_current_user
from app.households import SCOPE_VIEW_ACCOUNTS, Membership, require_member
from app.models import CustomAgent, User
from app.schemas import CustomAgentCreate, CustomAgentResponse, CustomAgentUpdate

router = APIRouter(prefix="/households/{household_id}/agents", tags=["custom-agents"])


async def _response(db: AsyncSession, agent: CustomAgent, membership: Membership, user: User) -> CustomAgentResponse:
    creator = await db.get(User, agent.created_by_user_id) if agent.created_by_user_id else None
    return CustomAgentResponse(
        id=agent.id,
        ref=custom_agents.ref(agent.id),
        household_id=agent.household_id,
        name=agent.name,
        instructions=agent.instructions,
        kind=agent.kind,
        schedule=agent.schedule,
        next_run_at=agent.next_run_at,
        last_run_at=agent.last_run_at,
        created_at=agent.created_at,
        created_by=(creator.display_name or creator.email) if creator else None,
        can_edit=membership.is_elder or agent.created_by_user_id == user.id,
    )


def _check_name(name: str) -> str:
    name = name.strip()
    if name.lower() in custom_agents.RESERVED_NAMES:
        raise HTTPException(status_code=422, detail=f"{name} is one of Warden's own agents. Pick another name.")
    return name


async def _editable(db: AsyncSession, household_id: uuid.UUID, agent_id: uuid.UUID, user: User) -> tuple[CustomAgent, Membership]:
    membership = await require_member(db, household_id, user)
    agent = await db.get(CustomAgent, agent_id)
    if agent is None or agent.household_id != household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if not (membership.is_elder or agent.created_by_user_id == user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the person who made this agent or the account owner can change it.")
    return agent, membership


@router.get("", response_model=list[CustomAgentResponse])
async def list_agents(
    household_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[CustomAgentResponse]:
    membership = await require_member(db, household_id, user)
    agents = (
        await db.execute(select(CustomAgent).where(CustomAgent.household_id == household_id).order_by(CustomAgent.created_at))
    ).scalars().all()
    return [await _response(db, a, membership, user) for a in agents]


@router.post("", response_model=CustomAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    household_id: uuid.UUID,
    body: CustomAgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomAgentResponse:
    membership = await require_member(db, household_id, user)
    if not membership.has(SCOPE_VIEW_ACCOUNTS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agents read the accounts, so you need permission to see them first. The account owner can allow it on the Family page.",
        )
    count = await db.scalar(select(func.count()).select_from(CustomAgent).where(CustomAgent.household_id == household_id))
    if (count or 0) >= custom_agents.MAX_PER_HOUSEHOLD:
        raise HTTPException(status_code=409, detail=f"A family can have up to {custom_agents.MAX_PER_HOUSEHOLD} agents. Delete one to make another.")
    agent = CustomAgent(
        household_id=household_id,
        created_by_user_id=user.id,
        name=_check_name(body.name),
        instructions=body.instructions.strip(),
        kind=body.kind,
        schedule=body.schedule,
        next_run_at=custom_agents.next_run(body.schedule, datetime.now(timezone.utc)),
    )
    db.add(agent)
    await db.flush()
    await audit.record(
        db,
        event_type="agent.created",
        user_id=user.id,
        household_id=household_id,
        detail={"name": agent.name, "schedule": agent.schedule, "by": membership.member.display_name},
    )
    await db.commit()
    await db.refresh(agent)
    return await _response(db, agent, membership, user)


@router.patch("/{agent_id}", response_model=CustomAgentResponse)
async def update_agent(
    household_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: CustomAgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomAgentResponse:
    agent, membership = await _editable(db, household_id, agent_id, user)
    if body.name is not None:
        agent.name = _check_name(body.name)
    if body.instructions is not None:
        agent.instructions = body.instructions.strip()
    if body.kind is not None:
        agent.kind = body.kind
    if body.schedule is not None and body.schedule != agent.schedule:
        agent.schedule = body.schedule
        agent.next_run_at = custom_agents.next_run(body.schedule, datetime.now(timezone.utc))
    await audit.record(
        db,
        event_type="agent.updated",
        user_id=user.id,
        household_id=household_id,
        detail={"name": agent.name, "schedule": agent.schedule, "by": membership.member.display_name},
    )
    await db.commit()
    await db.refresh(agent)
    return await _response(db, agent, membership, user)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    household_id: uuid.UUID,
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    agent, membership = await _editable(db, household_id, agent_id, user)
    name = agent.name
    await db.delete(agent)
    await audit.record(
        db,
        event_type="agent.deleted",
        user_id=user.id,
        household_id=household_id,
        detail={"name": name, "by": membership.member.display_name},
    )
    await db.commit()
