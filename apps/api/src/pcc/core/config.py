from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pcc.core.database_url import normalize_database_url


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://pcc:local_dev_only_change_me@localhost:5432/pcc"
    redis_url: str = "redis://localhost:6379/0"
    # Shared secret for Next.js → FastAPI (server-only). Empty rejects all
    # authenticated requests. Optional previous value supports dual-read rotation.
    pcc_service_credential: str = ""
    pcc_service_credential_previous: str = ""
    # deployment environment: "production" disables OpenAPI docs UI.
    pcc_env: str = "development"
    # Phase 1A chat default provider (mock requires no API keys).
    pcc_default_chat_provider: str = "mock"
    # Gates abandoned-run recovery only — does NOT enforce single-process deploy.
    # MVP requires exactly one active pcc-api process and no overlapping rolling
    # instances; violating that can finalize live peer runs as abandoned.
    pcc_chat_assume_single_worker: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_database_url(value)
        return value

    @property
    def is_production(self) -> bool:
        return self.pcc_env.strip().lower() == "production"

    @property
    def expose_api_docs(self) -> bool:
        """OpenAPI /docs /redoc are off in production (ADR 0004)."""
        return not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
