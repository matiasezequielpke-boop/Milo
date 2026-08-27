"""Sentinel's watch list — Fase 6 scaffold.

Creating/listing/deleting a monitor works today and is fully real. What
each monitor actually *does* when it comes due is not — see app/tasks.py.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import Monitor, User
from app.schemas import MonitorCreateRequest, MonitorResponse

router = APIRouter(prefix="/monitors", tags=["monitors"])


@router.get("", response_model=list[MonitorResponse])
async def list_monitors(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Monitor]:
    result = await db.execute(select(Monitor).where(Monitor.user_id == current_user.id))
    return list(result.scalars().all())


@router.post("", response_model=MonitorResponse, status_code=status.HTTP_201_CREATED)
async def create_monitor(
    body: MonitorCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Monitor:
    monitor = Monitor(
        user_id=current_user.id,
        description=body.description,
        check_interval_seconds=body.check_interval_seconds,
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)
    return monitor


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_monitor(
    monitor_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> None:
    result = await db.execute(select(Monitor).where(Monitor.id == monitor_id, Monitor.user_id == current_user.id))
    monitor = result.scalar_one_or_none()
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    await db.delete(monitor)
    await db.commit()
