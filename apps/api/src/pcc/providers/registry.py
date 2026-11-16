"""Provider registry — resolve adapters by name (Phase 1A.2 PR2)."""

from __future__ import annotations

from pcc.core.config import Settings, get_settings
from pcc.providers.base import ProviderAdapter
from pcc.providers.mock import (
    MOCK_PROVIDER_ID,
    STREAM_TEST_CHUNK_SIZE,
    STREAM_TEST_DELAY_SECONDS,
    MockProvider,
)

_KNOWN_PROVIDERS = frozenset({MOCK_PROVIDER_ID})


def get_provider(
    name: str | None = None,
    *,
    settings: Settings | None = None,
) -> ProviderAdapter:
    """Return a provider adapter.

    Defaults to ``settings.pcc_default_chat_provider`` (``mock`` in 1A).
    Unknown names raise ``ValueError``. Missing real-provider keys must not
    break boot when the default remains mock — real adapters arrive post-1A.

    ``PCC_MOCK_STREAM_TEST`` enables fixed-length timed streaming for manual
    Stop validation. It does not enable ``MOCK:*`` hooks (those stay off when
    ``PCC_ENV=production``).
    """
    resolved_settings = settings if settings is not None else get_settings()
    provider_name = (name or resolved_settings.pcc_default_chat_provider).strip().lower()
    if provider_name == MOCK_PROVIDER_ID:
        allow_hooks = not resolved_settings.is_production
        if resolved_settings.pcc_mock_stream_test:
            return MockProvider(
                allow_test_hooks=allow_hooks,
                stream_test=True,
                chunk_size=STREAM_TEST_CHUNK_SIZE,
                delay_seconds=STREAM_TEST_DELAY_SECONDS,
            )
        return MockProvider(allow_test_hooks=allow_hooks)
    raise ValueError(
        f"Unknown chat provider {provider_name!r}; known: {sorted(_KNOWN_PROVIDERS)}"
    )


def list_registered_provider_ids() -> list[str]:
    return sorted(_KNOWN_PROVIDERS)
