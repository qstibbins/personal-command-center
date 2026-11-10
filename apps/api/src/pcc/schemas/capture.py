"""Captures schemas."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CaptureCreate(BaseModel):
    source_type: Literal["text", "url"]
    title: str | None = Field(default=None, max_length=300)
    content: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_content(self):
        if not self.content.strip():
            raise ValueError("Capture content cannot be blank")
        return self


class CaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_type: str
    title: str | None
    content: str
    status: str
    created_at: datetime
    updated_at: datetime
