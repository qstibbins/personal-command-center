"""Centralized FastAPI authentication and authorization.

Service-credential verification for Next.js → FastAPI, plus hashed scoped
API tokens for non-browser clients (ADR 0003).
"""

from pcc.auth.dependencies import require_scopes, require_service_principal
from pcc.auth.principals import (
    SCOPE_CAPTURES_READ,
    SCOPE_CAPTURES_WRITE,
    AuthPrincipal,
)

__all__ = [
    "SCOPE_CAPTURES_READ",
    "SCOPE_CAPTURES_WRITE",
    "AuthPrincipal",
    "require_scopes",
    "require_service_principal",
]
