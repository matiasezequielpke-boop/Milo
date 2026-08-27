"""Scout's computer_use tool — Fase 4, deliberately last and deliberately
the thinnest scaffold in app/tools/.

Both the architecture blueprint and Scout's own system prompt
(app/agents/definitions.py) call browser automation "the most fragile
capability in this system," and build-backlog.md orders it after the
sandbox specifically because it's the third new risk surface, not the
first. Unlike search.py and sandbox.py — thin wrappers around one
provider's SDK — a real implementation here is an actual agentic loop:
Claude's computer-use tool driving Playwright screenshot-by-screenshot,
with its own error recovery, timeout, and cost-control story. Building
half of that loop now, untestable without a live Anthropic key, would
produce something that looks done and isn't. So this stays an honest
gate until Fase 4 is actually next.
"""
from __future__ import annotations

from app.config import get_settings
from app.tools.errors import ToolNotConfiguredError


def _require_key() -> str:
    key = get_settings().anthropic_api_key
    if not key:
        raise ToolNotConfiguredError(
            "No ANTHROPIC_API_KEY configured — Scout's computer_use tool needs "
            "Claude's computer-use capability, which needs Fase 0 budget first. See README."
        )
    return key


async def run_browser_task(instruction: str) -> str:
    """Drive a real browser via Claude's computer-use tool + Playwright.

    Raises ToolNotConfiguredError pre-Fase-0 (no key at all) and
    NotImplementedError even with a key present — the actual
    screenshot/act/observe loop is Fase 4 work, ordered last in
    build-backlog.md on purpose. Do not stub this out with a fake
    browser result; leave it failing loudly until it's really built.
    """
    _require_key()
    raise NotImplementedError(
        "computer_use is gated correctly but not yet implemented — see this module's "
        "docstring and build-backlog.md Fase 4."
    )
