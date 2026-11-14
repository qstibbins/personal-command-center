#!/usr/bin/env python3
"""Verify Alembic head and required tables/indexes after migrate.

Expects DATABASE_URL (SQLAlchemy ``postgresql+psycopg://`` or libpq
``postgresql://`` form). Intended to run inside the production API image
(or any environment with SQLAlchemy + psycopg). Exits 0 on success.

Phase 1A.2 PR1: includes provider-neutral chat tables and critical indexes.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

EXPECTED_HEAD = "0005_chat_schema"
REQUIRED_TABLES = (
    "alembic_version",
    "captures",
    "users",
    "accounts",
    "sessions",
    "verification_token",
    "api_tokens",
    "conversations",
    "messages",
    "message_usage",
    "chat_runs",
)

# Partial / named indexes that enforce chat invariants (Phase 1A.1 §B7).
REQUIRED_INDEXES = (
    "uq_conversations_source_external_id",
    "uq_messages_conversation_id_sequence",
    "uq_messages_conversation_source_external_id",
    "uq_chat_runs_one_running_per_conversation",
    "ix_conversations_owner_email_updated_at",
    "ix_chat_runs_conversation_id_started_at",
)


def normalize_database_url(url: str) -> str:
    """Match apps/api normalization so Render-style URLs work."""
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def main() -> int:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = create_engine(normalize_database_url(raw))
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if head != EXPECTED_HEAD:
            print(
                f"alembic head mismatch: expected {EXPECTED_HEAD!r}, got {head!r}",
                file=sys.stderr,
            )
            return 1

        for table in REQUIRED_TABLES:
            found = conn.execute(
                text("SELECT to_regclass(:name)"),
                {"name": f"public.{table}"},
            ).scalar_one()
            if found != table:
                print(f"missing required table: {table}", file=sys.stderr)
                return 1

        # Columns Auth.js + token APIs depend on.
        conn.execute(text('SELECT "sessionToken" FROM sessions WHERE false'))
        conn.execute(text('SELECT "emailVerified" FROM users WHERE false'))
        conn.execute(text("SELECT token_hash, scopes, revoked_at FROM api_tokens WHERE false"))

        # Critical chat columns (next_sequence + ownership + import hooks).
        conn.execute(
            text(
                "SELECT owner_email, next_sequence, source, source_external_id, "
                "default_provider, default_model, status, deleted_at "
                "FROM conversations WHERE false"
            )
        )
        conn.execute(
            text(
                "SELECT conversation_id, owner_email, role, status, sequence, "
                "content_text, source_external_id, parent_message_id "
                "FROM messages WHERE false"
            )
        )
        conn.execute(
            text(
                "SELECT message_id, input_tokens, output_tokens, total_tokens, "
                "latency_ms, cost_micros FROM message_usage WHERE false"
            )
        )
        conn.execute(
            text(
                "SELECT conversation_id, owner_email, status, provider, model, "
                "request_message_id, response_message_id, cancel_reason "
                "FROM chat_runs WHERE false"
            )
        )

        for index_name in REQUIRED_INDEXES:
            found = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND indexname = :name"
                ),
                {"name": index_name},
            ).scalar_one_or_none()
            if found != index_name:
                print(f"missing required index: {index_name}", file=sys.stderr)
                return 1

        # Confirm one-running-run index is partial on status = 'running'.
        running_pred = conn.execute(
            text(
                "SELECT pg_get_expr(indpred, indrelid) "
                "FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = 'uq_chat_runs_one_running_per_conversation'"
            )
        ).scalar_one_or_none()
        if running_pred is None or "running" not in running_pred:
            print(
                "uq_chat_runs_one_running_per_conversation missing "
                f"running predicate: {running_pred!r}",
                file=sys.stderr,
            )
            return 1

    print(
        f"OK: alembic={EXPECTED_HEAD}; tables="
        + ",".join(REQUIRED_TABLES)
        + "; indexes="
        + ",".join(REQUIRED_INDEXES)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — CI script surface
        print(f"schema verification failed: {exc}", file=sys.stderr)
        raise
