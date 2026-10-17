"""Scheduled jobs for hosts without a Celery worker (Vercel Cron).

Vercel calls these paths on the schedule in apps/api/vercel.json and sends
`Authorization: Bearer $CRON_SECRET`. Without CRON_SECRET set, the
endpoints refuse every call.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, status

from app import custom_agents
from app.config import get_settings

router = APIRouter(prefix="/internal/cron", tags=["cron"], include_in_schema=False)

# Vercel functions stop at 300 s here; leave room to finish the run in flight.
_BUDGET_SECONDS = 200


@router.get("/agents")
async def run_scheduled_agents(authorization: str | None = Header(default=None)) -> dict:
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not allowed")
    runs = await custom_agents.run_due(budget_seconds=_BUDGET_SECONDS)
    return {"runs": runs}
