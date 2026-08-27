"""Pydantic request/response models for the API layer."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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


class ConversationResponse(BaseModel):
    id: uuid.UUID
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
    agent_id: str
    action_type: str
    payload: dict
    status: str
    requested_at: datetime
    resolved_at: datetime | None


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
