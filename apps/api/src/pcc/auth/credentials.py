"""Credential verification for FastAPI callers.

Today only the server-to-server service credential is implemented. API token
verification hooks in here later without changing route dependencies.
"""

from __future__ import annotations

import secrets

from pcc.auth.principals import SERVICE_CREDENTIAL_SCOPES, AuthPrincipal
from pcc.core.config import Settings


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


def verify_api_token(token: str, settings: Settings) -> AuthPrincipal | None:
    """Placeholder for future hashed, scoped, revocable API tokens (ADR 0003)."""
    _ = token, settings
    return None


def verify_bearer_token(token: str, settings: Settings) -> AuthPrincipal | None:
    """Resolve a bearer token to a principal, or None if unrecognized."""
    principal = verify_service_credential(token, settings)
    if principal is not None:
        return principal
    return verify_api_token(token, settings)
