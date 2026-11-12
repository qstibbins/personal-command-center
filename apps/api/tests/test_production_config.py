"""Production configuration, docs lockdown, and readiness (Milestone 3.5b)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pcc.core.config import get_settings
from pcc.main import create_app


def _app_with_env(monkeypatch, **env: str):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return create_app()


def test_docs_enabled_outside_production(monkeypatch):
    application = _app_with_env(monkeypatch, PCC_ENV="development")
    client = TestClient(application)
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_disabled_in_production(monkeypatch):
    application = _app_with_env(monkeypatch, PCC_ENV="production")
    client = TestClient(application)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    # Liveness still works without auth.
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_settings_normalizes_render_database_url(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://pcc:secret@dpg-xxx-a/pcc",
    )
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "secret" in settings.database_url
    get_settings.cache_clear()


def test_ready_returns_503_when_database_unavailable(monkeypatch):
    application = _app_with_env(monkeypatch, PCC_ENV="production")

    class BoomEngine:
        def connect(self):
            raise OSError("connection refused")

    monkeypatch.setattr("pcc.main.engine", BoomEngine())
    client = TestClient(application)
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["database"] == "error"
    # Must not leak exception details
    assert "connection refused" not in response.text


def test_ready_ok_when_database_responds(monkeypatch):
    application = _app_with_env(monkeypatch, PCC_ENV="production")

    class OkConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            return None

    class OkEngine:
        def connect(self):
            return OkConn()

    monkeypatch.setattr("pcc.main.engine", OkEngine())
    client = TestClient(application)
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "pcc-api",
        "database": "ok",
    }


def test_is_production_property(monkeypatch):
    monkeypatch.setenv("PCC_ENV", "Production")
    get_settings.cache_clear()
    assert get_settings().is_production is True
    assert get_settings().expose_api_docs is False
    get_settings.cache_clear()
