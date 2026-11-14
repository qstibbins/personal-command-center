"""Pydantic schemas for chat API (Phase 1A.2 PR3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pcc.services.chat_ownership import normalize_owner_email

ConversationStatus = Literal["active", "archived", "deleted"]


def _validate_owner_email(value: str) -> str:
    trimmed = normalize_owner_email(value)
    if not trimmed or "@" not in trimmed or "." not in trimmed.split("@")[-1]:
        raise ValueError("owner_email must look like an email address")
    return trimmed


class OwnerEmailMixin(BaseModel):
    owner_email: str = Field(min_length=3, max_length=320)

    @field_validator("owner_email")
    @classmethod
    def normalize_owner(cls, value: str) -> str:
        return _validate_owner_email(value)


class ConversationCreate(OwnerEmailMixin):
    title: str | None = Field(default=None, max_length=300)
    default_provider: str = Field(default="mock", min_length=1, max_length=64)
    default_model: str = Field(default="mock-echo-v1", min_length=1, max_length=128)
    system_prompt: str | None = None

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class ConversationUpdate(OwnerEmailMixin):
    title: str | None = Field(default=None, max_length=300)
    status: Literal["active", "archived"] | None = None

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class ConversationDelete(OwnerEmailMixin):
    pass


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_email: str
    title: str | None
    status: str
    default_provider: str
    default_model: str
    system_prompt: str | None
    next_sequence: int
    source: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class MessageCreate(OwnerEmailMixin):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("content cannot be blank")
        return trimmed


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    owner_email: str
    role: str
    status: str
    content_text: str
    provider: str | None
    model: str | None
    sequence: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ChatRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    owner_email: str
    status: str
    provider: str
    model: str
    request_message_id: uuid.UUID | None
    response_message_id: uuid.UUID | None
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    cancel_reason: str | None


class ChatRunCancel(OwnerEmailMixin):
    pass


class ChatErrorBody(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | None = None
