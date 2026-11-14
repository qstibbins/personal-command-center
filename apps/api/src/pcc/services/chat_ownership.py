"""Owner-email helpers for chat row scoping (Phase 1A).

Matches Auth.js allowlist normalization: trim + lower. Application claim /
orchestration logic is intentionally out of scope for PR1.
"""

from __future__ import annotations

from typing import Any


def normalize_owner_email(email: str) -> str:
    """Normalize an owner email the same way as the website allowlist."""
    return email.strip().lower()


def owner_email_equals(column: Any, email: str) -> Any:
    """SQLAlchemy filter comparing a column to a normalized owner email."""
    return column == normalize_owner_email(email)
