"""Credential verification for FastAPI callers.

Resolves the Next.js service credential or a hashed, scoped, revocable API
token (ADR 0003 / Milestone 3.4).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pcc.auth.principals import SERVICE_CREDENTIAL_SCOPES, AuthPrincipal
from pcc.auth.token_crypto import hash_api_token
from pcc.core.config import Settings
from pcc.db.models import ApiToken


def _secure_equals(provided: str, expected: str) -> bool:
    """Constant-time equality; empty values never match (fail closed)."""
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)


def verify_service_credential(token: str, settings: Settings) -> AuthPrincipal | None:
    """Match the configured service credential (current or previous for rotation)."""
    if _secure_equals(token, settings.pcc_service_credential):
        return AuthPrincipal(
            subject="service:nextjs",
            scopes=SERVICE_CREDENTIAL_SCOPES,
            auth_method="service_credential",
        )
    if _secure_equals(token, settings.pcc_service_credential_previous):
        return AuthPrincipal(
            subject="service:nextjs",
            scopes=SERVICE_CREDENTIAL_SCOPES,
            auth_method="service_credential_previous",
        )
    return None


def verify_api_token(token: str, db: Session) -> AuthPrincipal | None:
    """Look up a hashed API token. Rejects revoked and expired tokens."""
    if not token:
        return None

    token_hash = hash_api_token(token)
    row = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash))
    if row is None:
        return None
    if row.revoked_at is not None:
        return None

    if row.expires_at is not None:
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= datetime.now(UTC):
            return None

    scopes = frozenset(str(scope) for scope in (row.scopes or []))
    if not scopes:
        return None

    return AuthPrincipal(
        subject=f"api_token:{row.id}",
        scopes=scopes,
        auth_method="api_token",
    )


def verify_bearer_token(
    token: str, settings: Settings, db: Session
) -> AuthPrincipal | None:
    """Resolve a bearer token to a principal, or None if unrecognized."""
    principal = verify_service_credential(token, settings)
    if principal is not None:
        return principal
    return verify_api_token(token, db)
