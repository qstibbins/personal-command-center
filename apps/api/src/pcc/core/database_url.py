"""Normalize database URLs for SQLAlchemy + psycopg3."""

from __future__ import annotations


def normalize_database_url(url: str) -> str:
    """Return a SQLAlchemy URL that uses the psycopg (v3) driver.

    Render and many managed Postgres providers supply ``postgresql://`` or
    ``postgres://`` URLs. SQLAlchemy 2 with psycopg3 expects
    ``postgresql+psycopg://``. Auth.js / ``pg`` continue to use plain
    ``postgresql://`` (see ``apps/web/auth-db.ts`` rewrite).
    """
    trimmed = url.strip()
    if trimmed.startswith("postgresql+psycopg://"):
        return trimmed
    if trimmed.startswith("postgresql://"):
        return "postgresql+psycopg://" + trimmed.removeprefix("postgresql://")
    if trimmed.startswith("postgres://"):
        return "postgresql+psycopg://" + trimmed.removeprefix("postgres://")
    return trimmed
