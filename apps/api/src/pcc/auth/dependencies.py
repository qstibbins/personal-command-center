from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pcc.auth.credentials import verify_bearer_token
from pcc.auth.principals import AuthPrincipal
from pcc.core.config import Settings, get_settings

# auto_error=False so missing credentials become a uniform 401 from this module
# rather than FastAPI's default WWW-Authenticate challenge shape alone.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthPrincipal:
    """Authenticate the caller. Does not check scopes."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = verify_bearer_token(credentials.credentials, settings)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_scopes(*required_scopes: str):
    """FastAPI dependency factory: authenticate, then require all given scopes."""

    if not required_scopes:
        raise ValueError("require_scopes() needs at least one scope")

    required = frozenset(required_scopes)

    def dependency(
        principal: Annotated[AuthPrincipal, Depends(get_principal)],
    ) -> AuthPrincipal:
        if not required.issubset(principal.scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return dependency
