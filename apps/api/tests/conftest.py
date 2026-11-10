
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from pcc.api.captures import get_db
from pcc.db.base import Base
from pcc.main import app
import pcc.db.models  # Register models with Base


@pytest.fixture
def db_client():
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
