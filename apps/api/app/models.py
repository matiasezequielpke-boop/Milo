"""SQLAlchemy ORM models — the L4 data layer.

Fase 1 tables: users, conversations, messages, waitlist signups, and a
votable suggestions board (the "Ahora" item from the backlog — the
cheapest, highest-value fix: these were client-only state in the
prototype and reset on every reload).

Fase 5 tables live here too (approval_requests, credentials, audit_log)
since the vault and HITL gate don't require any paid model API — there
was no reason to wait on Fase 0 budget to build them.

Fase 2 scaffold: documents / document_chunks with a pgvector column,
left unpopulated until a real embeddings provider is configured.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    """Mirrors auth.users, one row per Supabase-authenticated account.

    No password field — Supabase Auth owns credentials entirely (see
    app/supabase_auth.py). This row is created automatically by the
    on_auth_user_created trigger the moment someone verifies their
    email OTP; this app only ever reads it, never inserts into it.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # None = free routing across the whole fleet (Milo decides). A list of
    # one agent id = a 1:1 chat. 2+ = a group chat. Mirrors the frontend's
    # `activeParticipants` state from frontend-design-system.md (v7).
    active_participants: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "agent" | "system"
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(50), nullable=True)  # one of gateway.MODEL_MAP's keys
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class WaitlistSignup(Base):
    __tablename__ = "waitlist_signups"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Suggestion(Base):
    __tablename__ = "suggestions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Mirrors the frontend's four seed rows explicitly labeled "Example" —
    # never presented as real user data.
    is_example: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    votes: Mapped[list["SuggestionVote"]] = relationship(back_populates="suggestion", cascade="all, delete-orphan")


class SuggestionVote(Base):
    __tablename__ = "suggestion_votes"
    __table_args__ = (UniqueConstraint("suggestion_id", "user_id", name="uq_suggestion_vote_once"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    suggestion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suggestions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    suggestion: Mapped["Suggestion"] = relationship(back_populates="votes")


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"


class ApprovalRequest(Base):
    """The HITL gate. An agent with `requires_approval_for` on an action
    (see app/agents/definitions.py) must create one of these and block on
    it before executing — never execute first and log after."""

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[ApprovalStatus] = mapped_column(
        SqlEnum(ApprovalStatus, name="approval_status", native_enum=False, length=20, validate_strings=True),
        default=ApprovalStatus.pending,
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Credential(Base):
    """A user-supplied secret Warden may use on their behalf. `encrypted_value`
    is Fernet ciphertext (see app/vault.py) — the plaintext never touches the
    database, logs, or the audit trail."""

    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_credential_name_per_user"),)


class AuditLogEntry(Base):
    """Append-only. Nothing updates or deletes a row here — see app/audit.py."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    """Fase 2 (RAG) scaffold — Scribe's source material. Populated once
    file upload + an embeddings provider exist; the table is real today,
    the pipeline that fills it is not."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # text-embedding-3-small / voyage-3-lite dimension; adjust if the
    # embeddings provider chosen at Fase 2 differs.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)


class Monitor(Base):
    """A Fase 6 background watch — "let me know when X happens." The Celery
    beat heartbeat (app/celery_app.py, app/tasks.py) enumerates due rows
    here; it does not yet know how to *check* any of them for real — that's
    target-specific (RSS diff, price watch, page change...) and undefined
    until a real one gets built. The schema and the schedule are real; the
    checker is not."""

    __tablename__ = "monitors"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(50), default="sentinel", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
