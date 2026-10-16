"""Pydantic request/response models for the API layer."""
from __future__ import annotations

import uuid
from datetime import date as _date
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
# No RegisterRequest/LoginRequest/TokenResponse here anymore — Supabase
# Auth issues tokens directly to the frontend. This backend only ever
# reads a user back out (see app/deps.py, app/supabase_auth.py).

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    created_at: datetime


# --- Waitlist ---

class WaitlistSignupRequest(BaseModel):
    email: EmailStr


class WaitlistSignupResponse(BaseModel):
    email: str
    created_at: datetime
    already_on_list: bool = False


# --- Suggestions ---

class SuggestionCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)


class SuggestionResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    is_example: bool
    votes: int
    voted_by_me: bool
    created_at: datetime


# --- Conversations / chat ---

class ConversationCreateRequest(BaseModel):
    title: str | None = None
    active_participants: list[str] | None = None
    household_id: uuid.UUID | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    household_id: uuid.UUID | None = None
    title: str | None
    active_participants: list[str] | None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    agent_id: str | None
    model: str | None
    content: str
    created_at: datetime


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    model: str = "claude"


# --- Approvals (HITL) ---

class ApprovalCreateRequest(BaseModel):
    agent_id: str
    action_type: str
    payload: dict = Field(default_factory=dict)
    conversation_id: uuid.UUID | None = None


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    household_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    agent_id: str
    action_type: str
    payload: dict
    summary: str | None = None
    status: str
    requested_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None = None
    execution_result: dict | None = None
    can_resolve: bool = False


class ApprovalResolveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


# --- Credentials (vault) ---

class CredentialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1)


class CredentialResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
    # deliberately no `value` field — plaintext never leaves app/vault.py


# --- Monitors (Sentinel / Fase 6) ---

class MonitorCreateRequest(BaseModel):
    description: str = Field(min_length=3, max_length=1000)
    check_interval_seconds: int = Field(default=3600, ge=300, le=86400)


class MonitorResponse(BaseModel):
    id: uuid.UUID
    description: str
    check_interval_seconds: int
    is_active: bool
    last_checked_at: datetime | None
    last_result: str | None
    created_at: datetime


# --- Warden: households, consent, money data ---


class MemberInvite(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["elder", "approver"]


class HouseholdCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    my_role: Literal["elder", "approver"]
    my_display_name: str = Field(min_length=1, max_length=120)
    # Usually the other half of the pair: the parent if I'm the adult
    # child, or the child if I'm the parent setting this up myself.
    invite: MemberInvite | None = None


class MemberResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    status: str
    is_me: bool = False
    scopes: list[str] = Field(default_factory=list)


class InviteResult(BaseModel):
    member: MemberResponse
    # Only returned when the invite email couldn't be sent (no email
    # provider configured), so the inviter can share it by hand.
    invite_link: str | None = None
    emailed: bool = False


class ConsentResponse(BaseModel):
    id: uuid.UUID
    approver_member_id: uuid.UUID
    scopes: list[str]
    text_version: str
    granted_at: datetime
    revoked_at: datetime | None


class HouseholdResponse(BaseModel):
    id: uuid.UUID
    name: str
    my_member_id: uuid.UUID
    my_role: str
    my_scopes: list[str]
    members: list[MemberResponse]
    consents: list[ConsentResponse]
    created_at: datetime


class HouseholdCreateResponse(BaseModel):
    household: HouseholdResponse
    invite: InviteResult | None = None


class InviteAcceptRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class InvitePreviewResponse(BaseModel):
    household_name: str
    invited_email: str
    display_name: str
    role: str


class ConsentGrantRequest(BaseModel):
    approver_member_id: uuid.UUID
    scopes: list[Literal["view_accounts", "receive_alerts", "approve_actions"]] = Field(min_length=1)


class AuditEntryResponse(BaseModel):
    id: int
    event_type: str
    agent_id: str | None
    actor: str | None
    detail: dict
    created_at: datetime


class BankAccountResponse(BaseModel):
    id: uuid.UUID
    name: str
    mask: str | None
    type: str | None
    subtype: str | None
    current_balance: Decimal | None
    available_balance: Decimal | None
    currency: str
    institution_name: str | None


class TransactionResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    amount: Decimal
    currency: str
    date: _date
    name: str
    merchant_name: str | None
    category: str | None
    pending: bool


class AlertResponse(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    title: str
    reasons: list[str]
    status: str
    transaction: TransactionResponse | None
    created_at: datetime
    resolved_at: datetime | None


class AlertResolveRequest(BaseModel):
    resolution: Literal["confirmed_legit", "confirmed_fraud", "dismissed"]


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    merchant_name: str
    kind: str
    average_amount: Decimal
    last_amount: Decimal
    cadence_days: int
    charge_count: int
    last_charged_on: _date
    status: str


class BillResponse(BaseModel):
    id: uuid.UUID
    payee_name: str
    payee_blocked: bool
    amount: Decimal
    currency: str
    due_date: _date | None
    reference: str | None
    status: str
    created_at: datetime


class BillCreateRequest(BaseModel):
    payee_name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    due_date: _date | None = None
    reference: str | None = Field(default=None, max_length=200)


class PlaidLinkTokenResponse(BaseModel):
    link_token: str
    expiration: datetime | None = None


class PlaidExchangeRequest(BaseModel):
    public_token: str = Field(min_length=5, max_length=500)
    institution_name: str | None = Field(default=None, max_length=200)


class SyncResult(BaseModel):
    connections: int
    accounts: int
    added: int
    modified: int
    removed: int
    new_alerts: int


class SandboxTransactionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    date: _date | None = None
