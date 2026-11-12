"""Owner-operated API token management (via Next.js + service credential)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pcc.api.deps import get_db
from pcc.auth.dependencies import require_service_principal
from pcc.auth.principals import AuthPrincipal
from pcc.schemas.api_token import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from pcc.services.api_tokens import create_api_token, list_api_tokens, revoke_api_token

router = APIRouter(
    prefix="/api/v1/api-tokens",
    tags=["api-tokens"],
)


@router.post("", response_model=ApiTokenCreated, status_code=201)
def post_api_token(
    payload: ApiTokenCreate,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_service_principal)],
):
    return create_api_token(db, payload)


@router.get("", response_model=list[ApiTokenRead])
def get_api_tokens(
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_service_principal)],
):
    return list_api_tokens(db)


@router.post("/{token_id}/revoke", response_model=ApiTokenRead)
def post_revoke_api_token(
    token_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[AuthPrincipal, Depends(require_service_principal)],
):
    return revoke_api_token(db, token_id)
