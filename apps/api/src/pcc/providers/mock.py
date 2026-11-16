"""Deterministic mock chat provider (Phase 1A.2 PR2).

No network, credentials, DB sessions, or auth. Test hooks (``MOCK:*``) are
gated off when ``allow_test_hooks`` is false (production).

Optional ``stream_test`` mode (env ``PCC_MOCK_STREAM_TEST``) emits a fixed,
timed assistant reply so progressive streaming and Stop can be validated
without long user messages. Disabled by default; independent of ``MOCK:*``.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Literal

from pcc.providers.base import (
    ChatMessageDTO,
    CompleteResult,
    ModelRef,
    ProviderCapabilities,
    StreamEvent,
    ToolSpec,
    UsageInfo,
    collect_stream,
)

MOCK_PROVIDER_ID = "mock"
MOCK_MODEL_ID = "mock-echo-v1"
ECHO_PREFIX = "Echo: "
DEFAULT_CHUNK_SIZE = 5
DEFAULT_DELAY_SECONDS = 0.0
SLOW_DELAY_SECONDS = 0.05

# Fixed stream-test payload (~200 chars). With STREAM_TEST_CHUNK_SIZE=4 and
# STREAM_TEST_DELAY_SECONDS=0.2 → ~50 chunks ≈ 10s of observable streaming.
STREAM_TEST_RESPONSE = (
    "STREAM-TEST: Fixed mock reply for progressive streaming and Stop "
    "validation. Short user messages still produce this timed output. "
    "Chunks: 0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ — end of stream-test."
)
STREAM_TEST_CHUNK_SIZE = 4
STREAM_TEST_DELAY_SECONDS = 0.2

MockHook = Literal[
    "none",
    "error_rate_limited",
    "error_context_overflow",
    "slow",
    "empty",
]


class MockProvider:
    """Sync ``ProviderAdapter`` that echoes the last user message."""

    def __init__(
        self,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        allow_test_hooks: bool = True,
        stream_test: bool = False,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        self._chunk_size = chunk_size
        self._delay_seconds = delay_seconds
        self._allow_test_hooks = allow_test_hooks
        self._stream_test = stream_test
        self._sleep = sleep if sleep is not None else time.sleep

    def id(self) -> str:
        return MOCK_PROVIDER_ID

    def capabilities(self, model: str) -> ProviderCapabilities:
        _ = model
        return ProviderCapabilities(
            streaming=True,
            tools=False,
            vision=False,
            system_prompt=True,
            max_context_tokens=8192,
            supports_cancellation=True,
        )

    def list_models(self) -> list[ModelRef]:
        return [ModelRef(provider=MOCK_PROVIDER_ID, model=MOCK_MODEL_ID)]

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
        _ = (model, tools, temperature, max_output_tokens)

        if abort.is_set():
            yield StreamEvent(
                type="error",
                error_code="cancelled",
                message="Aborted before stream start",
            )
            return

        last_user = _last_user_content(messages)
        hook, payload = _parse_hook(last_user, allow_test_hooks=self._allow_test_hooks)

        yield StreamEvent(type="message_start", role="assistant")

        if hook == "error_context_overflow":
            yield StreamEvent(
                type="error",
                error_code="context_overflow",
                message="Mock context overflow",
            )
            return

        if hook == "empty":
            usage = _usage_for(messages, "")
            yield StreamEvent(type="usage", usage=usage)
            yield StreamEvent(
                type="message_end",
                status="complete",
                finish_reason="stop",
            )
            return

        if self._stream_test and hook == "none":
            output = STREAM_TEST_RESPONSE
            delay = self._delay_seconds
        else:
            output = f"{ECHO_PREFIX}{payload}"
            delay = (
                SLOW_DELAY_SECONDS
                if hook == "slow" and self._delay_seconds == DEFAULT_DELAY_SECONDS
                else self._delay_seconds
            )

        emitted_any_delta = False
        for chunk in _chunk_text(output, self._chunk_size):
            if abort.is_set():
                yield StreamEvent(
                    type="error",
                    error_code="cancelled",
                    message="Aborted during stream",
                )
                return
            if delay:
                self._sleep(delay)
                if abort.is_set():
                    yield StreamEvent(
                        type="error",
                        error_code="cancelled",
                        message="Aborted during stream",
                    )
                    return
            yield StreamEvent(type="content_delta", delta=chunk)
            emitted_any_delta = True

            if hook == "error_rate_limited" and emitted_any_delta:
                yield StreamEvent(
                    type="error",
                    error_code="rate_limited",
                    message="Mock rate limited",
                )
                return

        if abort.is_set():
            yield StreamEvent(
                type="error",
                error_code="cancelled",
                message="Aborted during stream",
            )
            return

        usage = _usage_for(messages, output)
        yield StreamEvent(type="usage", usage=usage)
        yield StreamEvent(
            type="message_end",
            status="complete",
            finish_reason="stop",
        )

    def complete(
        self,
        *,
        model: str,
        messages: list[ChatMessageDTO],
        tools: list[ToolSpec] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        abort: threading.Event | None = None,
    ) -> CompleteResult:
        """Optional non-stream convenience: drain ``stream()`` into one result."""
        return collect_stream(
            self.stream(
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                abort=abort or threading.Event(),
            )
        )


def _last_user_content(messages: list[ChatMessageDTO]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content") or ""
    return ""


def _parse_hook(content: str, *, allow_test_hooks: bool) -> tuple[MockHook, str]:
    if not allow_test_hooks:
        return "none", content

    stripped = content.strip()
    if stripped == "MOCK:EMPTY" or stripped.startswith("MOCK:EMPTY"):
        return "empty", ""
    if stripped.startswith("MOCK:SLOW"):
        rest = stripped[len("MOCK:SLOW") :].lstrip()
        return "slow", rest or "slow"
    if stripped.startswith("MOCK:ERROR:rate_limited"):
        return "error_rate_limited", stripped
    if stripped.startswith("MOCK:ERROR:context_overflow"):
        return "error_context_overflow", stripped
    return "none", content


def _chunk_text(text: str, chunk_size: int) -> Iterator[str]:
    if not text:
        return
    for index in range(0, len(text), chunk_size):
        yield text[index : index + chunk_size]


def _usage_for(messages: list[ChatMessageDTO], output: str) -> UsageInfo:
    joined = "".join(message.get("content") or "" for message in messages)
    input_tokens = len(joined) // 4
    output_tokens = len(output) // 4
    return UsageInfo(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_micros=0,
    )
