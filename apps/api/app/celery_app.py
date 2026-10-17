"""Celery app — Fase 6 background-work infra.

Redis as both broker and result backend, matching docker-compose.yml.
Run the worker with:

    celery -A app.celery_app worker --loglevel=info

...and the beat scheduler (for the periodic Sentinel heartbeat) with:

    celery -A app.celery_app beat --loglevel=info
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery("milo", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    # Sentinel's heartbeat. Real per-monitor checkers don't exist yet
    # (see app/tasks.py) — this just proves the Celery + Redis wiring
    # works end to end, which costs nothing and needs no API key.
    "sentinel-heartbeat": {
        "task": "sentinel.run_due_monitors",
        "schedule": crontab(minute="*/5"),
    },
    # Custom agents' weekly/monthly runs (app/custom_agents.py).
    "custom-agents": {
        "task": "agents.run_due",
        "schedule": crontab(minute="*/15"),
    },
}

celery_app.autodiscover_tasks(["app"])
