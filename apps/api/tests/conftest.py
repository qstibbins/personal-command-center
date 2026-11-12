import os

import pytest
from auth_helpers import TEST_SERVICE_CREDENTIAL
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from pcc.api.captures import get_db
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


@pytest.fixture
def db_client(auth_headers):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("Set TEST_DATABASE_URL to the isolated pcc_test database")

    url = make_url(database_url)
    if url.database != "pcc_test":
        pytest.fail("Refusing to modify a database other than pcc_test")

    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False)

    Base.metadata.create_all(engine)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            # Default authorized headers for capture workflow tests. Auth is
            # still verified against the configured service credential.
            client.headers.update(auth_headers)
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def raw_db_client():
    """Isolated DB client with no default Authorization header."""
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("Set TEST_DATABASE_URL to the isolated pcc_test database")

    url = make_url(database_url)
    if url.database != "pcc_test":
        pytest.fail("Refusing to modify a database other than pcc_test")

    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False)

    Base.metadata.create_all(engine)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()
