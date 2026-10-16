"""Conversations + the SSE streaming endpoint — the one seam between this
API and the Next.js frontend (see README's L1/L2 split).

Warden MVP: a conversation that belongs to a household runs the live
Milo/Warden agent (app/agent/runner.py) — real Claude, real tools, money
actions gated on family approval. Household-less conversations keep the
original single-call gateway path below.

Which agent answers is intentionally simple for now: a 1:1 chat
(`active_participants` has exactly one agent id) always routes to that
agent; anything else (free routing or a group chat) routes to Milo. A
real intent router across a group — the client-side `INTENTS` engine
described in claude/frontend-design-system.md v5 — is future LangGraph
coordinator work, not reimplemented here. This is a known simplification,
not a stand-in for a fake response: whichever agent answers, the answer
itself is either a real model completion or a clear "no model configured"
error, never scripted content.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import run_turn
from app.agents.definitions import get_agent
from app.db import SessionLocal, get_db
from app.deps import get_current_user
from app.households import require_member
from app.gateway import CompletionRequest, ModelNotConfiguredError, stream_complete
from app.models import Conversation, Message, User
from app.schemas import ChatRequest, ConversationCreateRequest, ConversationResponse, MessageResponse

router = APIRouter(prefix="/conversations", tags=["chat"])

_ROLE_TO_LITELLM = {"user": "user", "agent": "assistant", "system": "system"}


def _pick_responding_agent(conversation: Conversation) -> str:
    participants = conversation.active_participants
    if participants and len(participants) == 1:
        return participants[0]
    return "milo"


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Conversation:
    if body.household_id is not None:
        await require_member(db, body.household_id, current_user)
    conversation = Conversation(
        user_id=current_user.id,
        household_id=body.household_id,
        title=body.title,
        active_participants=body.active_participants,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    household_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Conversation]:
    query = select(Conversation).where(Conversation.user_id == current_user.id)
    if household_id:
        query = query.where(Conversation.household_id == household_id)
    result = await db.execute(query.order_by(Conversation.updated_at.desc()))
    return list(result.scalars().all())


async def _get_owned_conversation(conversation_id: str, db: AsyncSession, current_user: User) -> Conversation:
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if conversation.household_id is not None:
        # Leaving the household revokes access to its conversations too.
        await require_member(db, conversation.household_id, current_user)
    return conversation


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Message]:
    await _get_owned_conversation(conversation_id, db, current_user)
    # Tool-result rows are plumbing for the model, never shown to people.
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role != "tool")
        .order_by(Message.seq)
    )
    return [m for m in result.scalars().all() if m.role != "agent" or m.content.strip()]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    conversation = await _get_owned_conversation(conversation_id, db, current_user)
    if conversation.household_id is not None:
        return StreamingResponse(
            run_turn(conversation.id, current_user.id, body.content),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    agent_id = _pick_responding_agent(conversation)
    agent = get_agent(agent_id)  # 404s fast if active_participants somehow holds an unknown id

    user_message = Message(conversation_id=conversation.id, role="user", content=body.content)
    db.add(user_message)
    await db.commit()

    history_result = await db.execute(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.seq)
    )
    history = history_result.scalars().all()
    litellm_messages = [{"role": "system", "content": agent.system_prompt}] + [
        {"role": _ROLE_TO_LITELLM.get(m.role, "user"), "content": m.content} for m in history
    ]

    async def event_stream():
        yield _sse("start", {"agent_id": agent_id, "model": body.model})
        full_text = ""
        try:
            async for delta in stream_complete(
                CompletionRequest(model=body.model, messages=litellm_messages, stream=True)
            ):
                full_text += delta
                yield _sse("delta", {"content": delta})
        except ModelNotConfiguredError as exc:
            yield _sse("error", {"message": str(exc)})
            return
        except Exception as exc:  # provider/network failure — surface it, don't swallow it
            yield _sse("error", {"message": f"Model call failed: {exc}"})
            return

        async with SessionLocal() as write_session:
            agent_message = Message(
                conversation_id=conversation.id,
                role="agent",
                agent_id=agent_id,
                model=body.model,
                content=full_text,
            )
            write_session.add(agent_message)
            await write_session.execute(
                Conversation.__table__.update()
                .where(Conversation.id == conversation.id)
                .values(updated_at=func.now())
            )
            await write_session.commit()
            await write_session.refresh(agent_message)
        yield _sse("done", {"message_id": str(agent_message.id)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
