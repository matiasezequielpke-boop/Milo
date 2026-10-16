"""Rebuilds the Messages API history for a conversation from stored rows.

The history is append-only: every assistant turn is stored exactly as the
API returned it (thinking blocks included) and replayed byte-for-byte on
every later request. Never edit or drop earlier rows — newer models bind
thinking blocks to the exact prefix that produced them, and an edited
prefix also throws away the prompt cache.

Row roles map to API roles like this:
  user   -> user       (context block + what the person typed)
  agent  -> assistant  (full content blocks)
  tool   -> user       (tool_result blocks for the preceding assistant turn)
  system -> user       (<warden_event> text: an approval was resolved, ...)

Consecutive user-role entries are fine — the API merges them into one
turn. The one ordering rule that matters: tool_result blocks must
immediately follow the assistant turn that asked for them, so a Warden
event that lands while a turn is mid-flight is held back until after
that turn's tool results. The placement is a pure function of the stored
rows, so it's identical on every replay.
"""
from __future__ import annotations

from app.models import Message


def _has_tool_use(content: list | None) -> bool:
    return any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content or [])


def build_api_messages(rows: list[Message]) -> list[dict]:
    messages: list[dict] = []
    held_events: list[dict] = []
    awaiting_tool_results = False

    def flush_events() -> None:
        while held_events:
            messages.append(held_events.pop(0))

    for row in rows:
        if row.role == "system":
            event = {"role": "user", "content": row.api_content or [{"type": "text", "text": row.content}]}
            if awaiting_tool_results:
                held_events.append(event)
            else:
                messages.append(event)
            continue

        if row.role == "tool":
            messages.append({"role": "user", "content": row.api_content or []})
            awaiting_tool_results = False
            flush_events()
            continue

        if awaiting_tool_results:
            # An assistant tool_use with no stored results (the turn was cut
            # off before tools ran). Never happens with the runner's atomic
            # writes; skipping a dangling turn here would edit history, so
            # surface it instead of sending a request the API will reject.
            raise ValueError(f"conversation history has a tool_use without results before message {row.id}")

        if row.role == "agent":
            content = row.api_content or [{"type": "text", "text": row.content}]
            messages.append({"role": "assistant", "content": content})
            awaiting_tool_results = _has_tool_use(row.api_content)
        else:  # user
            messages.append({"role": "user", "content": row.api_content or [{"type": "text", "text": row.content}]})

    flush_events()
    return messages
