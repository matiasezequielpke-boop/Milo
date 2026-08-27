"""Append-only audit log helper — the other half of Fase 5.

Every sensitive action (an approval requested/approved/denied, a vault
credential used, a purchase executed) goes through `record()`. Nothing
in this codebase should ever UPDATE or DELETE a row in audit_log —
there's deliberately no function here that does either.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLogEntry


async def record(
    db: AsyncSession,
    *,
    event_type: str,
    user_id: uuid.UUID | None = None,
    agent_id: str | None = None,
    detail: dict | None = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        event_type=event_type,
        user_id=user_id,
        agent_id=agent_id,
        detail=detail or {},
    )
    db.add(entry)
    await db.flush()
    return entry
