"""Ledger's code_sandbox tool — Fase 3.

E2B rather than a locally-managed Docker/Firecracker sandbox: it's
purpose-built for exactly this (isolated, ephemeral, no network path
back to this host by default) and running it managed means the
one-founder team isn't also operating sandbox escape hardening solo
(see build-backlog.md, bloqueante #3 — no CTO yet).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.tools.errors import ToolNotConfiguredError


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int


def _require_key() -> str:
    key = get_settings().e2b_api_key
    if not key:
        raise ToolNotConfiguredError(
            "No E2B_API_KEY configured — Ledger's code_sandbox tool is inert until "
            "Fase 3 budget lands. See README."
        )
    return key


async def run_python(code: str, *, timeout_seconds: int = 30) -> SandboxResult:
    api_key = _require_key()

    # Lazy import — see app/tools/search.py for why.
    from e2b_code_interpreter import AsyncSandbox

    sandbox = await AsyncSandbox.create(api_key=api_key, timeout=timeout_seconds)
    try:
        execution = await sandbox.run_code(code)
        return SandboxResult(
            stdout="".join(execution.logs.stdout),
            stderr="".join(execution.logs.stderr),
            exit_code=0 if execution.error is None else 1,
        )
    finally:
        await sandbox.kill()
