"""Centralized FastAPI authentication and authorization.

Milestone 3.2 implements service-credential verification for Next.js → FastAPI
calls. The principal + scope dependency surface is the extension point for
future revocable API tokens (ADR 0003).
"""

from pcc.auth.dependencies import require_scopes
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
]
