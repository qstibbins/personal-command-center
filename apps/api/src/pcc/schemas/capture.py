"""Captures schemas."""
import re
from datetime import datetime
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
)

MAX_URL_LENGTH = 2048
MAX_TEXT_LENGTH = 100_000

_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)
_HOST_LABEL = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)")


def _is_valid_host(host: str) -> bool:
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        ip_address(host)
        return True
    except ValueError:
        pass
    host = host.removesuffix(".")
    if not host or len(host) > 253:
        return False
    return all(_HOST_LABEL.fullmatch(label) for label in host.lower().split("."))


def _validate_http_url(value: str) -> None:
    """Validate only; the caller stores the trimmed original string."""
    if len(value) > MAX_URL_LENGTH:
        raise ValueError(f"URL must be at most {MAX_URL_LENGTH} characters")
    if any(char.isspace() or not char.isprintable() for char in value):
        raise ValueError("URL cannot contain spaces or control characters")

    message = "URL must be an absolute http:// or https:// address with a valid host"
    try:
        parts = urlsplit(value)
        parsed = _HTTP_URL_ADAPTER.validate_python(value)
    except (ValueError, ValidationError):
        raise ValueError(message) from None

    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError(message)
    if "@" in parts.netloc:
        raise ValueError("URL cannot contain a username or password")
    if not parsed.host or not _is_valid_host(parsed.host):
        raise ValueError(message)


class CaptureCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_type: Literal["text", "url"]
    title: str | None = Field(default=None, max_length=300)
    content: str

    @field_validator("title")
    @classmethod
    def blank_title_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str, info: ValidationInfo) -> str:
        if not value:
            raise ValueError("Capture content cannot be blank")
        if info.data.get("source_type") == "url":
            _validate_http_url(value)
        elif len(value) > MAX_TEXT_LENGTH:
            raise ValueError(f"Text must be at most {MAX_TEXT_LENGTH:,} characters")
        return value


class CaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_type: str
    title: str | None
    content: str
    status: str
    created_at: datetime
    updated_at: datetime
