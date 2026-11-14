"""Unit tests for MockProvider and provider registry (Phase 1A.2 PR2).

No database, no network.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from pcc.providers import (
    MOCK_MODEL_ID,
    MOCK_PROVIDER_ID,
    ChatMessageDTO,
    MockProvider,
    ProviderAdapter,
    collect_stream,
    get_provider,
    list_registered_provider_ids,
)
from pcc.providers.mock import ECHO_PREFIX


def _user(content: str) -> ChatMessageDTO:
    return ChatMessageDTO(role="user", content=content)


def _messages(*contents: str) -> list[ChatMessageDTO]:
    return [_user(content) for content in contents]


def _stream(
    provider: MockProvider,
    messages: list[ChatMessageDTO],
    *,
    abort: threading.Event | None = None,
) -> list:
    return list(
        provider.stream(
            model=MOCK_MODEL_ID,
            messages=messages,
            tools=None,
            temperature=None,
            max_output_tokens=None,
            abort=abort or threading.Event(),
        )
    )


def test_mock_provider_satisfies_protocol():
    assert isinstance(MockProvider(), ProviderAdapter)


def test_capabilities_declaration():
    caps = MockProvider().capabilities(MOCK_MODEL_ID)
    assert caps == {
        "streaming": True,
        "tools": False,
        "vision": False,
        "system_prompt": True,
        "max_context_tokens": 8192,
        "supports_cancellation": True,
    }


def test_list_models():
    assert MockProvider().list_models() == [
        {"provider": MOCK_PROVIDER_ID, "model": MOCK_MODEL_ID}
    ]


def test_deterministic_echo_response():
    events = _stream(MockProvider(chunk_size=4, delay_seconds=0), _messages("hello"))
    types = [event["type"] for event in events]
    assert types[0] == "message_start"
    assert types[-2] == "usage"
    assert types[-1] == "message_end"
    assert "content_delta" in types

    text = "".join(event.get("delta", "") for event in events if event["type"] == "content_delta")
    assert text == f"{ECHO_PREFIX}hello"
    assert events[-1]["status"] == "complete"
    assert events[-1]["finish_reason"] == "stop"


def test_streaming_event_order():
    events = _stream(MockProvider(chunk_size=3, delay_seconds=0), _messages("abcdef"))
    types = [event["type"] for event in events]
    assert types[0] == "message_start"
    assert all(t == "content_delta" for t in types[1:-2])
    assert types[-2] == "usage"
    assert types[-1] == "message_end"
    # Chunks are ordered prefixes of the full echo
    deltas = [event["delta"] for event in events if event["type"] == "content_delta"]
    assert "".join(deltas) == f"{ECHO_PREFIX}abcdef"
    assert all(len(delta) <= 3 for delta in deltas)


def test_usage_reporting():
    messages = [
        ChatMessageDTO(role="system", content="sys"),
        ChatMessageDTO(role="user", content="hi"),
    ]
    events = _stream(MockProvider(delay_seconds=0), messages)
    usage_events = [event for event in events if event["type"] == "usage"]
    assert len(usage_events) == 1
    usage = usage_events[0]["usage"]
    joined = "syshi"
    output = f"{ECHO_PREFIX}hi"
    assert usage["input_tokens"] == len(joined) // 4
    assert usage["output_tokens"] == len(output) // 4
    assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
    assert usage["cost_micros"] == 0


def test_context_overflow_fails_before_deltas():
    events = _stream(
        MockProvider(delay_seconds=0),
        _messages("MOCK:ERROR:context_overflow"),
    )
    types = [event["type"] for event in events]
    assert types == ["message_start", "error"]
    assert events[1]["error_code"] == "context_overflow"
    assert not any(event["type"] == "content_delta" for event in events)


def test_rate_limited_after_one_delta():
    events = _stream(
        MockProvider(chunk_size=8, delay_seconds=0),
        _messages("MOCK:ERROR:rate_limited"),
    )
    types = [event["type"] for event in events]
    assert types[0] == "message_start"
    assert types[1] == "content_delta"
    assert types[2] == "error"
    assert events[2]["error_code"] == "rate_limited"
    assert "usage" not in types
    assert "message_end" not in types


def test_empty_hook_emits_empty_completion():
    events = _stream(MockProvider(delay_seconds=0), _messages("MOCK:EMPTY"))
    types = [event["type"] for event in events]
    assert types == ["message_start", "usage", "message_end"]
    assert events[1]["usage"]["output_tokens"] == 0
    assert events[2]["finish_reason"] == "stop"


def test_mock_hooks_disabled_in_production_mode():
    provider = MockProvider(allow_test_hooks=False, delay_seconds=0)
    events = _stream(provider, _messages("MOCK:ERROR:context_overflow"))
    text = "".join(event.get("delta", "") for event in events if event["type"] == "content_delta")
    assert text == f"{ECHO_PREFIX}MOCK:ERROR:context_overflow"
    assert not any(event["type"] == "error" for event in events)


def test_cancellation_mid_stream():
    abort = threading.Event()
    provider = MockProvider(chunk_size=2, delay_seconds=0)
    stream = provider.stream(
        model=MOCK_MODEL_ID,
        messages=_messages("abcdefghijklmnop"),
        tools=None,
        temperature=None,
        max_output_tokens=None,
        abort=abort,
    )
    assert next(stream)["type"] == "message_start"
    assert next(stream)["type"] == "content_delta"
    abort.set()
    remaining = list(stream)
    assert remaining[-1]["type"] == "error"
    assert remaining[-1]["error_code"] == "cancelled"
    assert not any(event["type"] == "message_end" for event in remaining)


def test_abort_before_start():
    abort = threading.Event()
    abort.set()
    events = _stream(MockProvider(), _messages("hello"), abort=abort)
    assert [event["type"] for event in events] == ["error"]
    assert events[0]["error_code"] == "cancelled"


def test_iterator_close_cleanup():
    provider = MockProvider(chunk_size=1, delay_seconds=0)
    stream = provider.stream(
        model=MOCK_MODEL_ID,
        messages=_messages("cleanup-me"),
        tools=None,
        temperature=None,
        max_output_tokens=None,
        abort=threading.Event(),
    )
    assert next(stream)["type"] == "message_start"
    assert next(stream)["type"] == "content_delta"
    stream.close()  # should not raise


def test_complete_convenience():
    result = MockProvider(delay_seconds=0).complete(
        model=MOCK_MODEL_ID,
        messages=_messages("world"),
    )
    assert result["content"] == f"{ECHO_PREFIX}world"
    assert result["finish_reason"] == "stop"
    assert result["error_code"] is None
    assert result["usage"] is not None
    assert result["usage"]["cost_micros"] == 0


def test_collect_stream_helper_matches_complete():
    provider = MockProvider(delay_seconds=0)
    via_complete = provider.complete(model=MOCK_MODEL_ID, messages=_messages("x"))
    via_helper = collect_stream(
        provider.stream(
            model=MOCK_MODEL_ID,
            messages=_messages("x"),
            tools=None,
            temperature=None,
            max_output_tokens=None,
            abort=threading.Event(),
        )
    )
    assert via_helper["content"] == via_complete["content"]
    assert via_helper["usage"] == via_complete["usage"]


def test_registry_returns_mock_by_default(monkeypatch):
    monkeypatch.setenv("PCC_ENV", "development")
    monkeypatch.setenv("PCC_DEFAULT_CHAT_PROVIDER", "mock")
    from pcc.core.config import get_settings

    get_settings.cache_clear()
    try:
        provider = get_provider()
        assert provider.id() == MOCK_PROVIDER_ID
        assert isinstance(provider, MockProvider)
        assert provider._allow_test_hooks is True
    finally:
        get_settings.cache_clear()


def test_registry_disables_hooks_in_production(monkeypatch):
    monkeypatch.setenv("PCC_ENV", "production")
    from pcc.core.config import get_settings

    get_settings.cache_clear()
    try:
        provider = get_provider("mock")
        assert isinstance(provider, MockProvider)
        assert provider._allow_test_hooks is False
    finally:
        get_settings.cache_clear()


def test_registry_unknown_provider():
    settings = SimpleNamespace(
        pcc_default_chat_provider="mock",
        is_production=False,
    )
    with pytest.raises(ValueError, match="Unknown chat provider"):
        get_provider("openai", settings=settings)  # type: ignore[arg-type]


def test_list_registered_provider_ids():
    assert list_registered_provider_ids() == [MOCK_PROVIDER_ID]


def test_uses_last_user_message_only():
    messages = [
        ChatMessageDTO(role="system", content="ignore"),
        ChatMessageDTO(role="user", content="first"),
        ChatMessageDTO(role="assistant", content="prior"),
        ChatMessageDTO(role="user", content="second"),
    ]
    events = _stream(MockProvider(delay_seconds=0), messages)
    text = "".join(event.get("delta", "") for event in events if event["type"] == "content_delta")
    assert text == f"{ECHO_PREFIX}second"
