"""API token lifecycle: create, list, revoke (hashed storage only)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from pcc.auth.token_crypto import generate_api_token
from pcc.db.models import ApiToken
from pcc.schemas.api_token import ApiTokenCreate, ApiTokenCreated, ApiTokenRead


def create_api_token(db: Session, payload: ApiTokenCreate) -> ApiTokenCreated:
    if payload.expires_at is not None:
        expires = payload.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= datetime.now(UTC):
            raise HTTPException(
                status_code=getattr(
                    status, "HTTP_422_UNPROCESSABLE_CONTENT", 422
                ),
                detail="expires_at must be in the future",
            )
        payload = payload.model_copy(update={"expires_at": expires})

    raw, token_hash, token_prefix = generate_api_token()
    row = ApiToken(
        label=payload.label,
        token_prefix=token_prefix,
        token_hash=token_hash,
        scopes=list(payload.scopes),
        expires_at=payload.expires_at,
        created_by_email=payload.created_by_email,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return ApiTokenCreated(
        id=row.id,
        label=row.label,
        token_prefix=row.token_prefix,
        scopes=list(row.scopes),
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_by_email=row.created_by_email,
        token=raw,
    )


def list_api_tokens(db: Session) -> list[ApiTokenRead]:
    rows = db.scalars(
        select(ApiToken).order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
    ).all()
    return [
        ApiTokenRead(
            id=row.id,
            label=row.label,
            token_prefix=row.token_prefix,
            scopes=list(row.scopes),
            created_at=row.created_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            created_by_email=row.created_by_email,
        )
        for row in rows
    ]


def revoke_api_token(db: Session, token_id: uuid.UUID) -> ApiTokenRead:
    row = db.get(ApiToken, token_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        db.add(row)
        db.commit()
        db.refresh(row)

    return ApiTokenRead(
        id=row.id,
        label=row.label,
        token_prefix=row.token_prefix,
        scopes=list(row.scopes),
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_by_email=row.created_by_email,
    )
