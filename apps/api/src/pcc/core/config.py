from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://pcc:local_dev_only_change_me@localhost:5432/pcc"
    redis_url: str = "redis://localhost:6379/0"
    # Shared secret for Next.js → FastAPI (server-only). Empty rejects all
    # authenticated requests. Optional previous value supports dual-read rotation.
    pcc_service_credential: str = ""
    pcc_service_credential_previous: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
