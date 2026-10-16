"""One chat turn: the person's message in, Milo's streamed answer out, with
as many tool rounds as the model needs in between.

The loop is written by hand (not the SDK tool runner) because each round
has to be persisted atomically — the assistant turn and its tool results
in one commit — so the stored history is always replayable, and because
approval requests created by a tool are announced to the UI and the
family as soon as they're committed.

SSE events emitted (consumed by apps/web):
  start    {agent_id, model}
  delta    {content}                      streamed text
  tool     {name, status, agent}          a tool started
  approval {approval}                     an approval request was created
  reset    {}                             discard streamed text (refusal)
  error    {message}
  done     {message_id}
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone

import anthropic
from sqlalchemy import select, update

from app import warden
from app.agent.history import build_api_messages
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOL_DEFINITIONS, TOOLS_BY_NAME, ToolContext, run_tool
from app.config import get_settings
from app.db import SessionLocal
from app.households import SCOPE_APPROVE_ACTIONS, SCOPE_VIEW_ACCOUNTS, get_membership
from app.models import Conversation, Message, User

logger = logging.getLogger(__name__)

# Models that accept server-side refusal fallbacks with `fallbacks: "default"`.
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_BUSY_FOR = timedelta(minutes=5)
_MAX_TOKENS = 16000


class AgentNotConfiguredError(RuntimeError):
    pass


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _client() -> anthropic.AsyncAnthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise AgentNotConfiguredError(
            "ANTHROPIC_API_KEY is not set, so Milo can't answer yet. Nothing here is scripted — "
            "the chat stays off until a real model key is configured."
        )
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, base_url=settings.warden_api_base_url)


def context_block(membership, today: date) -> dict:
    role = "account owner (elder)" if membership.is_elder else "family approver"
    can_view = "yes" if membership.has(SCOPE_VIEW_ACCOUNTS) else "no (owner hasn't granted it)"
    can_approve = "yes" if membership.has(SCOPE_APPROVE_ACTIONS) else "no"
    return {
        "type": "text",
        "text": (
            f"<context>Today: {today.isoformat()}. Household: {membership.household.name}. "
            f"You're talking with {membership.member.display_name}, the {role}. "
            f"Can see accounts: {can_view}. Can approve actions: {can_approve}.</context>"
        ),
    }


def _request_kwargs(model: str, messages: list[dict]) -> dict:
    settings = get_settings()
    kwargs: dict = {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "system": [{"type": "text", "text": SYSTEM_PROMPT}],
        "tools": TOOL_DEFINITIONS,
        "messages": messages,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": settings.warden_effort},
        # Caches tools + system + history up to the newest turn.
        "cache_control": {"type": "ephemeral"},
    }
    if model in _FALLBACK_MODELS:
        kwargs["betas"] = [_FALLBACK_BETA]
        kwargs["fallbacks"] = "default"
    return kwargs


async def _claim(db, conversation_id: uuid.UUID) -> bool:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            (Conversation.agent_busy_until.is_(None)) | (Conversation.agent_busy_until < now),
        )
        .values(agent_busy_until=now + _BUSY_FOR)
        .returning(Conversation.id)
    )
    claimed = result.scalar_one_or_none() is not None
    await db.commit()
    return claimed


async def _release(conversation_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(update(Conversation).where(Conversation.id == conversation_id).values(agent_busy_until=None))
        await db.commit()


async def run_turn(conversation_id: uuid.UUID, user_id: uuid.UUID, text: str) -> AsyncIterator[str]:
    settings = get_settings()
    model = settings.warden_model
    async with SessionLocal() as db:
        conversation = await db.get(Conversation, conversation_id)
        user = await db.get(User, user_id)
        membership = await get_membership(db, conversation.household_id, user) if conversation and user else None
        if membership is None:
            yield _sse("error", {"message": "You're no longer a member of this household."})
            return
        if not await _claim(db, conversation_id):
            yield _sse("error", {"message": "Milo is still answering the previous message. Try again in a moment."})
            return

        try:
            client = _client()
        except AgentNotConfiguredError as exc:
            await _release(conversation_id)
            yield _sse("error", {"message": str(exc)})
            return

        try:
            db.add(
                Message(
                    conversation_id=conversation_id,
                    role="user",
                    author_user_id=user.id,
                    content=text,
                    api_content=[context_block(membership, date.today()), {"type": "text", "text": text}],
                )
            )
            await db.commit()
            yield _sse("start", {"agent_id": "milo", "model": model})

            last_message_id: uuid.UUID | None = None
            for _round in range(settings.warden_max_tool_rounds):
                rows = (
                    await db.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.seq))
                ).scalars().all()
                messages = build_api_messages(list(rows))

                try:
                    async with client.beta.messages.stream(**_request_kwargs(model, messages)) as stream:
                        async for event in stream:
                            if event.type == "text":
                                yield _sse("delta", {"content": event.text})
                            elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                                tool = TOOLS_BY_NAME.get(event.content_block.name)
                                yield _sse(
                                    "tool",
                                    {
                                        "name": event.content_block.name,
                                        "status": tool.status_text if tool else event.content_block.name,
                                        "agent": tool.agent if tool else "milo",
                                    },
                                )
                        final = await stream.get_final_message()
                except ValueError:
                    # Tool input JSON the SDK couldn't parse at all (eager
                    # streaming). Nothing was persisted; re-run the round.
                    logger.warning("unparseable tool input; retrying round")
                    yield _sse("reset", {})
                    continue
                except anthropic.AuthenticationError:
                    yield _sse("error", {"message": "The model API key was rejected. Check ANTHROPIC_API_KEY."})
                    return
                except anthropic.RateLimitError:
                    yield _sse("error", {"message": "Milo is getting too many requests right now. Try again in a minute."})
                    return
                except anthropic.APIStatusError as exc:
                    logger.exception("model call failed")
                    yield _sse("error", {"message": f"The model call failed ({exc.status_code}). Try again."})
                    return
                except anthropic.APIConnectionError:
                    yield _sse("error", {"message": "Couldn't reach the model. Check the connection and try again."})
                    return

                tool_uses = [b for b in final.content if b.type == "tool_use"]

                if final.stop_reason == "refusal":
                    # A declined turn is discarded, not stored: the partial
                    # text never becomes part of the replayed history.
                    yield _sse("reset", {})
                    yield _sse("error", {"message": "Milo can't help with that request."})
                    return
                if final.stop_reason == "max_tokens" and tool_uses:
                    yield _sse("reset", {})
                    yield _sse("error", {"message": "That answer ran too long. Try asking in smaller steps."})
                    return

                visible = "".join(b.text for b in final.content if b.type == "text")
                assistant = Message(
                    conversation_id=conversation_id,
                    role="agent",
                    agent_id="milo",
                    model=final.model,
                    content=visible,
                    api_content=[b.to_dict(mode="json") for b in final.content],
                )
                db.add(assistant)

                if final.stop_reason == "pause_turn":
                    await db.commit()
                    continue

                if not tool_uses:
                    await db.commit()
                    last_message_id = assistant.id
                    break

                ctx = ToolContext(
                    db=db, user=user, membership=membership, conversation_id=conversation_id, created_approvals=[]
                )
                results = []
                for block in tool_uses:
                    content, is_error = await run_tool(ctx, block.name, block.input)
                    result = {"type": "tool_result", "tool_use_id": block.id, "content": content}
                    if is_error:
                        result["is_error"] = True
                    results.append(result)
                db.add(Message(conversation_id=conversation_id, role="tool", content="", api_content=results))
                # The assistant turn, its tool results, and any approval
                # request a tool created land together or not at all.
                await db.commit()
                last_message_id = assistant.id

                for approval in ctx.created_approvals:
                    yield _sse(
                        "approval",
                        {
                            "approval": {
                                "id": str(approval.id),
                                "summary": approval.summary,
                                "action_type": approval.action_type,
                                "status": approval.status.value,
                            }
                        },
                    )
                    await warden.notify_requested(db, approval)
                # Re-read permissions for the next round (consent can change).
                membership = await get_membership(db, conversation.household_id, user) or membership
            else:
                yield _sse("error", {"message": "Milo needed too many steps for that. Try a simpler request."})

            await db.execute(
                update(Conversation).where(Conversation.id == conversation_id).values(updated_at=datetime.now(timezone.utc))
            )
            await db.commit()
            yield _sse("done", {"message_id": str(last_message_id) if last_message_id else None})
        except Exception:
            # Anything unexpected (a DB error mid-tool): the round's writes
            # were never committed, so the history stays replayable.
            logger.exception("agent turn failed")
            await db.rollback()
            yield _sse("error", {"message": "Something went wrong on our side. Nothing was changed. Try again."})
        finally:
            await _release(conversation_id)
