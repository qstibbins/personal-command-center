"""Provider-neutral chat adapters (Phase 1A).

MVP ships ``MockProvider`` only. Future OpenAI / Anthropic / Gemini adapters
implement the same ``ProviderAdapter`` Protocol — see ``README.md``.
"""

from pcc.providers.base import (
    ChatMessageDTO,
    CompleteResult,
    ModelRef,
    ProviderAdapter,
    ProviderCapabilities,
    StreamEvent,
    ToolSpec,
    UsageInfo,
    collect_stream,
)
from pcc.providers.mock import (
    MOCK_MODEL_ID,
    MOCK_PROVIDER_ID,
    STREAM_TEST_RESPONSE,
    MockProvider,
)
from pcc.providers.registry import get_provider, list_registered_provider_ids

__all__ = [
    "MOCK_MODEL_ID",
    "MOCK_PROVIDER_ID",
    "STREAM_TEST_RESPONSE",
    "ChatMessageDTO",
    "CompleteResult",
    "MockProvider",
    "ModelRef",
    "ProviderAdapter",
    "ProviderCapabilities",
    "StreamEvent",
    "ToolSpec",
    "UsageInfo",
    "collect_stream",
    "get_provider",
    "list_registered_provider_ids",
]
