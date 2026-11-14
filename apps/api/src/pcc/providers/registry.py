"""Provider registry — resolve adapters by name (Phase 1A.2 PR2)."""

from __future__ import annotations

from pcc.core.config import Settings, get_settings
from pcc.providers.base import ProviderAdapter
from pcc.providers.mock import MOCK_PROVIDER_ID, MockProvider

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
    """
    resolved_settings = settings if settings is not None else get_settings()
    provider_name = (name or resolved_settings.pcc_default_chat_provider).strip().lower()
    if provider_name == MOCK_PROVIDER_ID:
        return MockProvider(allow_test_hooks=not resolved_settings.is_production)
    raise ValueError(
        f"Unknown chat provider {provider_name!r}; known: {sorted(_KNOWN_PROVIDERS)}"
    )


def list_registered_provider_ids() -> list[str]:
    return sorted(_KNOWN_PROVIDERS)
