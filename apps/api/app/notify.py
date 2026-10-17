"""Outbound notifications: transactional email (Resend) and ntfy.sh push.

Email goes one message per recipient, so nobody sees anyone else's
address and each carries its own unsubscribe link (footer link plus
`List-Unsubscribe` / one-click headers, RFC 8058). People who turned
notification emails off are skipped. Sign-in codes are not sent from here
— Supabase sends those, and they're the login itself, so they can't be
turned off.

The ntfy push goes to one shared topic, which anyone who knows its name
can read, so it only ever says that something needs attention — never an
amount, a payee or a name.

Both follow the "degrade instead of fake it" pattern: with no key / no
topic the call is a no-op that returns False, and callers surface that
(e.g. the invite endpoint hands back the link to share by hand).
Notification failures never block the action that triggered them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import logging
import uuid

import httpx
from sqlalchemy import select

from app.config import get_settings

NTFY_BASE_URL = "https://ntfy.sh"
RESEND_URL = "https://api.resend.com/emails"

logger = logging.getLogger(__name__)


# --- unsubscribe tokens -------------------------------------------------

def _sign(data: bytes) -> str:
    key = hashlib.sha256(f"email-unsubscribe:{get_settings().app_secret_key}".encode()).digest()
    return base64.urlsafe_b64encode(hmac.new(key, data, hashlib.sha256).digest()[:18]).decode().rstrip("=")


def unsubscribe_token(user_id: uuid.UUID) -> str:
    """Signed, non-expiring: an unsubscribe link must keep working."""
    return f"{user_id.hex}.{_sign(user_id.bytes)}"


def read_unsubscribe_token(token: str) -> uuid.UUID | None:
    try:
        raw, signature = token.split(".", 1)
        user_id = uuid.UUID(hex=raw)
    except ValueError:
        return None
    return user_id if hmac.compare_digest(signature, _sign(user_id.bytes)) else None


def _footer_lines(unsubscribe_url: str | None) -> list[str]:
    settings = get_settings()
    lines = ["You're getting this because you're part of a family on Warden."]
    if unsubscribe_url:
        lines.append(f"Turn off these emails: {unsubscribe_url}")
    business = settings.business_name + (f", {settings.business_address}" if settings.business_address else "")
    lines.append(business + (f" · {settings.contact_email}" if settings.contact_email else ""))
    return lines


# --- delivery -----------------------------------------------------------

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


async def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    link: str | None = None,
    unsubscribe_url: str | None = None,
    one_click_url: str | None = None,
) -> bool:
    """Plain, readable email to one person — they may be in their 70s.
    Returns False (no-op) if RESEND_API_KEY isn't set."""
    settings = get_settings()
    if not settings.resend_api_key or not to:
        return False

    footer = _footer_lines(unsubscribe_url)
    paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in body.split("\n") if line.strip())
    button = (
        f'<p><a href="{html.escape(link)}" style="display:inline-block;padding:12px 20px;'
        'background:#8f3d1c;color:#fff;text-decoration:none;border-radius:8px">Open Warden</a></p>'
        if link
        else ""
    )
    footer_html = "<br>".join(
        (
            f'Turn off these emails: <a href="{html.escape(unsubscribe_url)}" style="color:#555">unsubscribe</a>'
            if unsubscribe_url and line.startswith("Turn off")
            else html.escape(line)
        )
        for line in footer
    )
    payload: dict = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": (
            f'<div style="font-family:system-ui,sans-serif;font-size:16px;line-height:1.5;color:#1a1410">{paragraphs}{button}'
            f'<hr style="border:0;border-top:1px solid #ddd;margin:24px 0 12px">'
            f'<p style="font-size:13px;color:#555">{footer_html}</p></div>'
        ),
        "text": body + (f"\n\n{link}" if link else "") + "\n\n--\n" + "\n".join(footer),
    }
    if unsubscribe_url:
        # One-click (RFC 8058) needs an endpoint that accepts a POST, i.e. the
        # API; without a public API URL, mail apps get the plain page link.
        headers = {"List-Unsubscribe": f"<{one_click_url or unsubscribe_url}>"}
        if one_click_url:
            headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        payload["headers"] = headers
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(RESEND_URL, headers={"Authorization": f"Bearer {settings.resend_api_key}"}, json=payload)
        response.raise_for_status()
    return True


async def _recipients(emails: list[str]) -> list[tuple[str, uuid.UUID | None]]:
    """Drops people who turned notification emails off; returns the rest
    with their user id (None for someone without an account yet, e.g. an
    invite)."""
    from app.db import SessionLocal
    from app.models import User

    wanted = sorted({e.strip().lower() for e in emails if e and e.strip()})
    if not wanted:
        return []
    async with SessionLocal() as db:
        users = {u.email.lower(): u for u in (await db.execute(select(User).where(User.email.in_(wanted)))).scalars()}
    out: list[tuple[str, uuid.UUID | None]] = []
    for email in wanted:
        user = users.get(email)
        if user is not None and user.email_opt_out_at is not None:
            continue
        out.append((email, user.id if user else None))
    return out


async def notify_people(emails: list[str], subject: str, body: str, *, link: str | None = None) -> bool:
    """Email each person + a content-free push, swallowing delivery errors
    (logged, never raised). Returns whether any email went out."""
    settings = get_settings()
    emailed = False
    for email, user_id in await _recipients(emails):
        token = unsubscribe_token(user_id) if user_id else None
        unsubscribe_url = f"{settings.web_app_url.rstrip('/')}/unsubscribe?token={token}" if token else None
        one_click_url = (
            f"{settings.public_api_url.rstrip('/')}/email/unsubscribe?token={token}" if token and settings.public_api_url else None
        )
        try:
            emailed = (
                await send_email(email, subject, body, link=link, unsubscribe_url=unsubscribe_url, one_click_url=one_click_url)
                or emailed
            )
        except httpx.HTTPError:
            logger.exception("email delivery failed")
    try:
        await push("Warden", "Something in Warden needs your attention. Open the app to see it.")
    except httpx.HTTPError:
        logger.exception("push delivery failed")
    return emailed
