#!/usr/bin/env python3
"""Verify Alembic head and Auth.js / API-token tables after migrate (M3.5b.1).

Expects DATABASE_URL (SQLAlchemy ``postgresql+psycopg://`` or libpq
``postgresql://`` form). Intended to run inside the production API image
(or any environment with SQLAlchemy + psycopg). Exits 0 on success.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

EXPECTED_HEAD = "0004_api_tokens"
REQUIRED_TABLES = (
    "alembic_version",
    "captures",
    "users",
    "accounts",
    "sessions",
    "verification_token",
    "api_tokens",
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

    print(f"OK: alembic={EXPECTED_HEAD}; tables=" + ",".join(REQUIRED_TABLES))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — CI script surface
        print(f"schema verification failed: {exc}", file=sys.stderr)
        raise
