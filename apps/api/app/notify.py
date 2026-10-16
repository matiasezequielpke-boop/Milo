"""Outbound notifications: ntfy.sh push and transactional email.

ntfy is free for a single public topic, which is why it's the Fase 1
push channel instead of something requiring its own paid account. Email
goes through Resend (approval requests and invites need to reach a family
member who isn't looking at the app). Both follow the same "degrade
instead of fake it" pattern as the model gateway: with no topic / no key,
the call is a no-op that returns False, and callers surface that (e.g.
the invite endpoint hands back the link to share by hand).

Notification failures never block the action that triggered them — a
payment that settled stays settled even if the email about it bounced.
"""
from __future__ import annotations

import html
import logging

import httpx

from app.config import get_settings

NTFY_BASE_URL = "https://ntfy.sh"
RESEND_URL = "https://api.resend.com/emails"

logger = logging.getLogger(__name__)


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


async def send_email(to: list[str], subject: str, body: str, *, link: str | None = None) -> bool:
    """Plain, readable email — the recipient may be in their 70s. Returns
    False (no-op) if RESEND_API_KEY isn't set."""
    settings = get_settings()
    if not settings.resend_api_key or not to:
        return False

    paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in body.split("\n") if line.strip())
    button = (
        f'<p><a href="{html.escape(link)}" style="display:inline-block;padding:12px 20px;'
        'background:#000;color:#fff;text-decoration:none;border-radius:8px">Open Warden</a></p>'
        if link
        else ""
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": to,
                "subject": subject,
                "html": f'<div style="font-family:system-ui,sans-serif;font-size:16px;line-height:1.5">{paragraphs}{button}</div>',
                "text": body + (f"\n\n{link}" if link else ""),
            },
        )
        response.raise_for_status()
    return True


async def notify_people(emails: list[str], subject: str, body: str, *, link: str | None = None) -> bool:
    """Email + push, swallowing delivery errors (logged, never raised)."""
    delivered = False
    try:
        delivered = await send_email(emails, subject, body, link=link) or delivered
    except httpx.HTTPError:
        logger.exception("email delivery failed: %s", subject)
    try:
        delivered = await push(subject, body) or delivered
    except httpx.HTTPError:
        logger.exception("push delivery failed: %s", subject)
    return delivered
