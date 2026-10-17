"""Celery tasks. Import side effect registers them with celery_app.

`run_due_monitors` is intentionally a heartbeat, not a real monitor
runner: it proves Celery + Redis + beat scheduling work end to end
(true today, testable with zero API keys) without pretending any
monitor actually got checked. Per-monitor logic is target-specific
(RSS diff, price watch, page-change detection...) and none of that
exists yet — wiring it up is real Fase 6 work, not a stub to fake here.
"""
from __future__ import annotations

from app.celery_app import celery_app


@celery_app.task(name="sentinel.run_due_monitors")
def run_due_monitors() -> dict:
    return {
        "status": "heartbeat ok",
        "note": "beat schedule + Redis broker confirmed working; no monitor checkers implemented yet",
    }


@celery_app.task(name="agents.run_due")
def run_due_agents() -> list[dict]:
    """Starts the custom agents whose weekly/monthly run is due."""
    import asyncio

    from app.custom_agents import run_due
    from app.db import engine

    async def go():
        try:
            return await run_due()
        finally:
            # Each task runs in a fresh event loop; don't keep pooled
            # connections bound to a loop that's about to close.
            await engine.dispose()

    return asyncio.run(go())
