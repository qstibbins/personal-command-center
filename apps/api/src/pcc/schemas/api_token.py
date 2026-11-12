from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pcc.auth.principals import SCOPE_CAPTURES_READ, SCOPE_CAPTURES_WRITE

AllowedScope = Literal["captures:read", "captures:write"]
ALLOWED_SCOPES: frozenset[str] = frozenset({SCOPE_CAPTURES_READ, SCOPE_CAPTURES_WRITE})


class ApiTokenCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    scopes: list[AllowedScope] = Field(min_length=1)
    expires_at: datetime | None = None
    created_by_email: str = Field(min_length=3, max_length=320)

    @field_validator("label")
    @classmethod
    def trim_label(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Label cannot be blank")
        return trimmed

    @field_validator("created_by_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        trimmed = value.strip().lower()
        if "@" not in trimmed or "." not in trimmed.split("@")[-1]:
            raise ValueError("created_by_email must look like an email address")
        return trimmed

    @field_validator("scopes")
    @classmethod
    def unique_known_scopes(cls, value: list[AllowedScope]) -> list[str]:
        # Preserve request order while deduplicating.
        seen: list[str] = []
        for scope in value:
            if scope not in ALLOWED_SCOPES:
                raise ValueError(f"Unsupported scope: {scope}")
            if scope not in seen:
                seen.append(scope)
        if not seen:
            raise ValueError("At least one scope is required")
        return seen


class ApiTokenRead(BaseModel):
    """Metadata only — never includes the raw token or hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    token_prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    created_by_email: str


class ApiTokenCreated(ApiTokenRead):
    """Creation response: raw token shown once."""

    token: str
