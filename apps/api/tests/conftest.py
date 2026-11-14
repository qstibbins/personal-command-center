import os

import pytest
from auth_helpers import TEST_SERVICE_CREDENTIAL
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from pcc.api.deps import get_db
from pcc.core.config import get_settings
from pcc.db.base import Base
from pcc.main import app


def _database_disabled():
    raise RuntimeError("Use the db_client fixture for tests that reach the database")
    yield  # pragma: no cover


@pytest.fixture(autouse=True)
def configure_service_credential(monkeypatch):
    """Configure a known service credential for every test (fail-closed auth)."""
    monkeypatch.setenv("PCC_SERVICE_CREDENTIAL", TEST_SERVICE_CREDENTIAL)
    monkeypatch.delenv("PCC_SERVICE_CREDENTIAL_PREVIOUS", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def block_unisolated_database():
    """Fail loudly if any test reaches get_db without the isolated pcc_test fixture."""
    app.dependency_overrides[get_db] = _database_disabled
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_SERVICE_CREDENTIAL}"}


def _bind_test_database():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("Set TEST_DATABASE_URL to the isolated pcc_test database")

    url = make_url(database_url)
    if url.database != "pcc_test":
        pytest.fail("Refusing to modify a database other than pcc_test")

    from pcc.db import session as db_session
    from pcc.services import chat_abort

    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    original_engine = db_session.engine
    original_session_local = db_session.SessionLocal

    Base.metadata.create_all(engine)
    db_session.engine = engine
    db_session.SessionLocal = session_factory
    chat_abort.clear_all_for_tests()

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    def cleanup():
        app.dependency_overrides.pop(get_db, None)
        chat_abort.clear_all_for_tests()
        db_session.SessionLocal = original_session_local
        db_session.engine = original_engine
        Base.metadata.drop_all(engine)
        engine.dispose()

    return cleanup


@pytest.fixture
def db_client(auth_headers):
    cleanup = _bind_test_database()
    try:
        with TestClient(app) as client:
            # Default authorized headers for capture workflow tests. Auth is
            # still verified against the configured service credential.
            client.headers.update(auth_headers)
            yield client
    finally:
        cleanup()


@pytest.fixture
def raw_db_client():
    """Isolated DB client with no default Authorization header."""
    cleanup = _bind_test_database()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        cleanup()
