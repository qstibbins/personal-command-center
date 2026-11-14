"""Alembic upgrade/downgrade against PostgreSQL for chat schema (Phase 1A.2 PR1).

Exercises the real migration path (not create_all) so CI fails if revision
0005_chat_schema does not apply cleanly from 0004_api_tokens.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from pcc.core.config import get_settings

PREVIOUS_HEAD = "0004_api_tokens"
CHAT_HEAD = "0005_chat_schema"
CHAT_TABLES = ("conversations", "messages", "message_usage", "chat_runs")


def _api_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    """Build Alembic config; env.py reads DATABASE_URL via get_settings()."""
    cfg = Config(str(_api_root() / "alembic.ini"))
    cfg.set_main_option("script_location", str(_api_root() / "migrations"))
    return cfg


def _require_pcc_test_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("Set TEST_DATABASE_URL to the isolated pcc_test database")
    url = make_url(database_url)
    if url.database != "pcc_test":
        pytest.fail("Refusing to modify a database other than pcc_test")
    return database_url


def _reset_public_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO CURRENT_USER"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    engine.dispose()


def _alembic_version(database_url: str) -> str | None:
    engine = create_engine(database_url)
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar_one()
        if exists is None:
            engine.dispose()
            return None
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    engine.dispose()
    return version


def _table_exists(database_url: str, table: str) -> bool:
    engine = create_engine(database_url)
    with engine.connect() as conn:
        found = conn.execute(
            text("SELECT to_regclass(:name)"),
            {"name": f"public.{table}"},
        ).scalar_one()
    engine.dispose()
    return found == table


def _index_exists(database_url: str, index_name: str) -> bool:
    engine = create_engine(database_url)
    with engine.connect() as conn:
        found = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND indexname = :name"
            ),
            {"name": index_name},
        ).scalar_one_or_none()
    engine.dispose()
    return found == index_name


@pytest.fixture
def alembic_db_url(monkeypatch):
    """Point Alembic env.py at pcc_test and isolate the public schema."""
    database_url = _require_pcc_test_url()
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    _reset_public_schema(database_url)
    yield database_url
    _reset_public_schema(database_url)
    get_settings.cache_clear()


def test_alembic_upgrade_head_creates_chat_schema(alembic_db_url):
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    assert _alembic_version(alembic_db_url) == CHAT_HEAD
    for table in CHAT_TABLES:
        assert _table_exists(alembic_db_url, table), f"missing table {table}"

    assert _table_exists(alembic_db_url, "captures")
    assert _table_exists(alembic_db_url, "api_tokens")
    assert _table_exists(alembic_db_url, "sessions")

    assert _index_exists(alembic_db_url, "uq_chat_runs_one_running_per_conversation")
    assert _index_exists(alembic_db_url, "uq_conversations_source_external_id")
    assert _index_exists(alembic_db_url, "uq_messages_conversation_source_external_id")
    assert _index_exists(alembic_db_url, "uq_messages_conversation_id_sequence")

    engine = create_engine(alembic_db_url)
    with engine.connect() as conn:
        # next_sequence present with default semantics
        conn.execute(text("SELECT next_sequence FROM conversations WHERE false"))
        pred = conn.execute(
            text(
                "SELECT pg_get_expr(indpred, indrelid) "
                "FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = 'uq_chat_runs_one_running_per_conversation'"
            )
        ).scalar_one()
        assert "running" in pred
    engine.dispose()


def test_alembic_downgrade_to_previous_removes_chat_tables(alembic_db_url):
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    command.downgrade(cfg, PREVIOUS_HEAD)

    assert _alembic_version(alembic_db_url) == PREVIOUS_HEAD
    for table in CHAT_TABLES:
        assert not _table_exists(alembic_db_url, table), f"table still present: {table}"

    # Prior schema preserved
    assert _table_exists(alembic_db_url, "api_tokens")
    assert _table_exists(alembic_db_url, "captures")
    assert _table_exists(alembic_db_url, "sessions")

    # Re-upgrade for CI confidence that the revision is re-applicable
    command.upgrade(cfg, "head")
    assert _alembic_version(alembic_db_url) == CHAT_HEAD
    for table in CHAT_TABLES:
        assert _table_exists(alembic_db_url, table)
