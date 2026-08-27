"""ntfy.sh push notifications.

ntfy is free for a single public topic, which is why it's the Fase 1
push channel instead of something requiring its own paid account. If
`NTFY_TOPIC` isn't set, `push()` is a silent no-op — same "degrade
instead of fake it" pattern as the model gateway and every other
budget-gated integration in this codebase.
"""
from __future__ import annotations

import httpx

from app.config import get_settings

NTFY_BASE_URL = "https://ntfy.sh"


async def push(title: str, message: str, *, priority: str = "default") -> bool:
    """Send a push notification. Returns False (no-op) if no topic is configured."""
    settings = get_settings()
    if not settings.ntfy_topic:
        return False

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{NTFY_BASE_URL}/{settings.ntfy_topic}",
            content=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority},
        )
        response.raise_for_status()
    return True
