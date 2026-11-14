"""Provider-neutral chat adapter contract (Phase 1A.2 PR2).

Sync ``Iterator[StreamEvent]`` streaming matches the existing FastAPI +
SQLAlchemy ``SessionLocal`` stack. Adapters must not open DB sessions, own
auth, or persist conversations — that belongs to the orchestrator (PR3+).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Literal, NotRequired, Protocol, TypedDict, runtime_checkable

# Normalized provider / orchestrator error codes (architecture §C3).
# ``run_in_progress`` is orchestrator-only and must not be emitted by adapters.
ProviderErrorCode = Literal[
    "provider_unavailable",
    "rate_limited",
    "context_overflow",
    "cancelled",
    "content_filtered",
    "invalid_request",
    "internal",
]

StreamEventType = Literal[
    "message_start",
    "content_delta",
    "message_end",
    "usage",
    "error",
]

MessageRole = Literal["system", "user", "assistant", "tool"]

FinishReason = Literal["stop", "length", "error", "cancelled"]


class ProviderCapabilities(TypedDict):
    streaming: bool
    tools: bool
    vision: bool
    system_prompt: bool
    max_context_tokens: int | None
    supports_cancellation: bool


class ChatMessageDTO(TypedDict):
    role: MessageRole
    content: str


class ModelRef(TypedDict):
    provider: str
    model: str


class ToolSpec(TypedDict):
    """Forward-compatible tool descriptor; adapters receive ``tools=None`` in 1A."""

    name: str
    description: str
    input_schema: dict
    read_only: bool


class UsageInfo(TypedDict, total=False):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_micros: int


class StreamEvent(TypedDict):
    """Adapter-level stream event.

    Wire/SSE shapes add ``run_id`` / ``message_id`` in the orchestrator (PR3).
    Adapters emit only the fields listed here.
    """

    type: StreamEventType
    role: NotRequired[MessageRole]
    delta: NotRequired[str]
    status: NotRequired[Literal["complete", "partial", "failed"]]
    finish_reason: NotRequired[FinishReason]
    usage: NotRequired[UsageInfo]
    error_code: NotRequired[ProviderErrorCode]
    message: NotRequired[str]


class CompleteResult(TypedDict):
    """Optional non-stream convenience result assembled from a stream."""

    content: str
    finish_reason: FinishReason
    usage: UsageInfo | None
    error_code: ProviderErrorCode | None
    error_message: str | None
    events: list[StreamEvent]


@runtime_checkable
class ProviderAdapter(Protocol):
    """Sync provider adapter. Real vendor SDKs plug in behind this Protocol."""

    def id(self) -> str:
        """Stable provider id, e.g. ``mock``, ``openai``, ``anthropic``, ``google``."""
        ...

    def capabilities(self, model: str) -> ProviderCapabilities:
        ...

    def list_models(self) -> list[ModelRef]:
        ...

    def stream(
        self,
        *,
        model: str,
        messages: list[ChatMessageDTO],
        tools: list[ToolSpec] | None,
        temperature: float | None,
        max_output_tokens: int | None,
        abort: threading.Event,
    ) -> Iterator[StreamEvent]:
        """Yield normalized stream events. Honor ``abort`` between chunks."""
        ...


def collect_stream(events: Iterator[StreamEvent]) -> CompleteResult:
    """Drain a stream into a ``CompleteResult`` (optional ``complete()`` helper)."""
    content_parts: list[str] = []
    collected: list[StreamEvent] = []
    usage: UsageInfo | None = None
    finish_reason: FinishReason = "stop"
    error_code: ProviderErrorCode | None = None
    error_message: str | None = None

    for event in events:
        collected.append(event)
        event_type = event["type"]
        if event_type == "content_delta":
            content_parts.append(event.get("delta") or "")
        elif event_type == "usage":
            usage = event.get("usage")
        elif event_type == "message_end":
            finish_reason = event.get("finish_reason") or "stop"
        elif event_type == "error":
            error_code = event.get("error_code") or "internal"
            error_message = event.get("message")
            finish_reason = "cancelled" if error_code == "cancelled" else "error"

    return CompleteResult(
        content="".join(content_parts),
        finish_reason=finish_reason,
        usage=usage,
        error_code=error_code,
        error_message=error_message,
        events=collected,
    )
