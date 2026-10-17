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
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Identity,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
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
    app/supabase_auth.py). The id is the Supabase user id; the row is made
    at sign-up or first login (app/routers/auth.py), or earlier by the
    on_auth_user_created trigger where that exists.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # What the person agreed to at sign-up, and when (consent records).
    terms_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    age_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when they turn notification emails off (unsubscribe link or
    # Settings). Sign-in codes still go out: those are the login itself.
    email_opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


class AuthSession(Base):
    """A Supabase session this API accepts. A Supabase access token alone
    isn't enough: its `session_id` must be here, which only happens after
    sign-up or after both login steps (password, then emailed code). A
    session obtained any other way — straight from Supabase with just a
    password, or just an emailed link — is rejected."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)  # Supabase session_id
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # "signup" | "login"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginChallenge(Base):
    """One password check. Failed ones count toward the rate limit; a
    successful one opens a short window to enter the emailed code."""

    __tablename__ = "login_challenges"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    codes_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    code_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Warden MVP: every money conversation happens inside one household,
    # so the agent's tools know whose accounts they may read.
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # None = free routing across the whole fleet (Milo decides). A list of
    # one agent id = a 1:1 chat. 2+ = a group chat. Mirrors the frontend's
    # `activeParticipants` state from frontend-design-system.md (v7).
    active_participants: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # Set while an agent turn is running so two turns can't interleave in
    # one history. A timestamp, not a flag, so a crashed turn frees itself.
    agent_busy_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.seq")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("seq", name="uq_messages_seq"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Strict insertion order. created_at can't provide it: Postgres now()
    # is the transaction's start time, so an agent turn's rows tie.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "user" | "agent" | "tool" | "system". "tool" rows hold tool results and
    # are never shown in the UI; "system" rows are Warden events (an
    # approval resolved, a payment settled) shown to everyone.
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Display text. For agent rows, the concatenated text blocks.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # The exact Messages API content this row contributed, replayed
    # verbatim on every later turn (thinking blocks included) — the
    # history is append-only, never rewritten. See app/agent/history.py.
    api_content: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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
    # Nobody decided in time. Treated exactly like a denial: nothing runs.
    expired = "expired"


class ApprovalRequest(Base):
    """The HITL gate. An agent with `requires_approval_for` on an action
    (see app/agents/definitions.py) must create one of these and block on
    it before executing — never execute first and log after."""

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Who asked. Kept nullable so the household's record of a request
    # survives the requester deleting their account.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # One plain-language sentence the approver reads before deciding.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ApprovalStatus] = mapped_column(
        SqlEnum(ApprovalStatus, name="approval_status", native_enum=False, length=20, validate_strings=True),
        default=ApprovalStatus.pending,
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # What happened when an approved action ran: {"status": "succeeded" |
    # "failed", ...}. Null until execution — approval and execution are
    # separate facts and the audit log records both.
    execution_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


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
    # The family-shared view of the log filters on this. Nullable because
    # account-level events (a credential created) belong to no household.
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("households.id", ondelete="SET NULL"), nullable=True, index=True
    )
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


# ---------------------------------------------------------------------------
# Warden MVP — families protecting an older parent's money.
#
# A household has two kinds of members: the elder whose accounts are
# watched, and one or more approvers (usually an adult child) who release
# anything irreversible. An approver sees nothing until the elder grants
# consent, and the elder can revoke it at any time — see app/households.py.
# ---------------------------------------------------------------------------


class MemberRole(str, enum.Enum):
    elder = "elder"
    approver = "approver"


class MemberStatus(str, enum.Enum):
    invited = "invited"
    active = "active"
    removed = "removed"


def _str_enum(enum_cls: type[enum.Enum], name: str) -> SqlEnum:
    return SqlEnum(enum_cls, name=name, native_enum=False, length=20, validate_strings=True)


class Household(Base):
    __tablename__ = "households"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list["HouseholdMember"]] = relationship(back_populates="household", order_by="HouseholdMember.invited_at")


class HouseholdMember(Base):
    __tablename__ = "household_members"
    __table_args__ = (UniqueConstraint("household_id", "email", name="uq_member_email_per_household"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Null until the invite is accepted by a signed-in user with this email.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[MemberRole] = mapped_column(_str_enum(MemberRole, "member_role"), nullable=False)
    status: Mapped[MemberStatus] = mapped_column(
        _str_enum(MemberStatus, "member_status"), default=MemberStatus.invited, nullable=False
    )
    # sha256 of the invite token; the token itself is only ever in the link.
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    household: Mapped["Household"] = relationship(back_populates="members")


class Consent(Base):
    """The elder's explicit permission for one approver. Never updated in
    place except to stamp `revoked_at`; granting again creates a new row,
    so the history of who could see what, and when, is preserved."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    elder_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("household_members.id", ondelete="CASCADE"), nullable=False
    )
    approver_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("household_members.id", ondelete="CASCADE"), nullable=False
    )
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    # Which wording of the consent screen the elder agreed to.
    text_version: Mapped[str] = mapped_column(String(20), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BankConnection(Base):
    """One Plaid Item (one login at one bank). The Plaid access token lives
    in the vault (`credentials`), never in this row."""

    __tablename__ = "bank_connections"

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("household_members.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), default="plaid", nullable=False)
    provider_item_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    credential_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credentials.id", ondelete="RESTRICT"), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bank_connections.id", ondelete="CASCADE"), nullable=False
    )
    provider_account_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mask: Mapped[str | None] = mapped_column(String(10), nullable=True)
    type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subtype: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    available_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BankTransaction(Base):
    """Plaid's sign convention is kept as-is: a positive amount is money
    leaving the account, a negative amount is money coming in."""

    __tablename__ = "bank_transactions"
    __table_args__ = (Index("ix_bank_transactions_household_date", "household_id", "date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)
    provider_transaction_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertStatus(str, enum.Enum):
    open = "open"
    confirmed_legit = "confirmed_legit"
    confirmed_fraud = "confirmed_fraud"
    dismissed = "dismissed"


class Alert(Base):
    """Something Warden's detector (app/detection.py) thinks the family
    should look at. Re-running detection never duplicates an alert: the
    (household, kind, dedupe_key) triple is unique."""

    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("household_id", "kind", "dedupe_key", name="uq_alert_dedupe"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bank_transactions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # "low" | "medium" | "high"
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[AlertStatus] = mapped_column(
        _str_enum(AlertStatus, "alert_status"), default=AlertStatus.open, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Subscription(Base):
    """A recurring charge detected from transaction history."""

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("household_id", "merchant_key", name="uq_subscription_merchant"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    merchant_key: Mapped[str] = mapped_column(String(200), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # "subscription" (cancellable) or "bill" (utilities, insurance, rent).
    kind: Mapped[str] = mapped_column(String(20), default="subscription", nullable=False)
    average_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    last_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cadence_days: Mapped[int] = mapped_column(Integer, nullable=False)
    charge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_charged_on: Mapped[date] = mapped_column(Date, nullable=False)
    last_charged_on: Mapped[date] = mapped_column(Date, nullable=False)
    # "active" | "cancel_requested" | "cancelled"
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Payee(Base):
    """Someone Warden may pay. `blocked` is set when the family marks a
    charge from them as fraud — Warden then refuses to propose paying them."""

    __tablename__ = "payees"
    __table_args__ = (UniqueConstraint("household_id", "name", name="uq_payee_name_per_household"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Stripe Connect account that receives the funds directly, so the money
    # never sits with Warden (see docs/money-plan.md).
    stripe_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payees.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # "open" | "pending_approval" | "processing" | "paid" | "failed" | "cancelled"
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomAgent(Base):
    """An agent a family member made for one job ("review last month's
    spending"). It runs on the same model as Milo with read-only tools —
    it can look things up and report, never move money or change anything.
    Its instructions are the person's own words and are treated as a job
    description, not as permissions."""

    __tablename__ = "custom_agents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="blob")  # mascot shape
    # "manual" | "weekly" (Mondays) | "monthly" (the 1st)
    schedule: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id", ondelete="RESTRICT"), nullable=False)
    approval_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="stripe", nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    livemode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # "processing" | "succeeded" | "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
