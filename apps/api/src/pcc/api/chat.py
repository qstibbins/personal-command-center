"""Chat conversation and streaming routes (Phase 1A.2 PR3)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from pcc.api.deps import get_db
from pcc.auth.dependencies import require_chat_service_principal
from pcc.auth.principals import (
    SCOPE_CHAT_READ,
    SCOPE_CHAT_WRITE,
    AuthPrincipal,
)
from pcc.schemas.chat import (
    ChatRunCancel,
    ChatRunRead,
    ConversationCreate,
    ConversationDelete,
    ConversationRead,
    ConversationUpdate,
    MessageCreate,
    MessageRead,
)
from pcc.services.chat_conversations import (
    ChatNotFoundError,
    create_conversation,
    list_conversations,
    list_messages,
    soft_delete_conversation,
    update_conversation,
)
from pcc.services.chat_orchestrator import (
    RunInProgressError,
    cancel_run,
    claim_turn,
    iter_sse_for_claim,
)
from pcc.services.chat_ownership import normalize_owner_email

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def _parse_owner_query(owner_email: str) -> str:
    try:
        normalized = normalize_owner_email(owner_email)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_owner_email", "message": "Invalid owner_email"},
        ) from exc
    if not normalized or "@" not in normalized or "." not in normalized.split("@")[-1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_owner_email", "message": "Invalid owner_email"},
        )
    return normalized


@router.get("/conversations", response_model=list[ConversationRead])
def get_conversations(
    _principal: Annotated[
        AuthPrincipal, Depends(require_chat_service_principal(SCOPE_CHAT_READ))
    ],
    db: Annotated[Session, Depends(get_db)],
    owner_email: Annotated[str, Query(min_length=3, max_length=320)],
    limit: int = Query(default=50, ge=1, le=100),
):
    owner = _parse_owner_query(owner_email)
    return list_conversations(db, owner_email=owner, limit=limit)


@router.post("/conversations", response_model=ConversationRead, status_code=201)
def post_conversation(
    payload: ConversationCreate,
    _principal: Annotated[
        AuthPrincipal, Depends(require_chat_service_principal(SCOPE_CHAT_WRITE))
    ],
    db: Annotated[Session, Depends(get_db)],
):
    return create_conversation(db, payload)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation_route(
    conversation_id: uuid.UUID,
    _principal: Annotated[
        AuthPrincipal, Depends(require_chat_service_principal(SCOPE_CHAT_READ))
    ],
    db: Annotated[Session, Depends(get_db)],
    owner_email: Annotated[str, Query(min_length=3, max_length=320)],
):
    from pcc.services.chat_conversations import get_conversation

    owner = _parse_owner_query(owner_email)
    try:
        return get_conversation(
            db, conversation_id=conversation_id, owner_email=owner
        )
    except ChatNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def patch_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    _principal: Annotated[
        AuthPrincipal, Depends(require_chat_service_principal(SCOPE_CHAT_WRITE))
    ],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return update_conversation(
            db, conversation_id=conversation_id, data=payload
        )
    except ChatNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc


@router.delete("/conversations/{conversation_id}", response_model=ConversationRead)
def delete_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationDelete,
    _principal: Annotated[
        AuthPrincipal, Depends(require_chat_service_principal(SCOPE_CHAT_WRITE))
    ],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return soft_delete_conversation(
            db,
            conversation_id=conversation_id,
            owner_email=payload.owner_email,
        )
    except ChatNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
)
def get_messages(
    conversation_id: uuid.UUID,
    _principal: Annotated[
        AuthPrincipal, Depends(require_chat_service_principal(SCOPE_CHAT_READ))
    ],
    db: Annotated[Session, Depends(get_db)],
    owner_email: Annotated[str, Query(min_length=3, max_length=320)],
    limit: int = Query(default=200, ge=1, le=500),
):
    owner = _parse_owner_query(owner_email)
    try:
        return list_messages(
            db,
            conversation_id=conversation_id,
            owner_email=owner,
            limit=limit,
        )
    except ChatNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc


@router.post("/conversations/{conversation_id}/messages")
def post_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    _principal: Annotated[
        AuthPrincipal, Depends(require_chat_service_principal(SCOPE_CHAT_WRITE))
    ],
):
    """Start a mock provider stream (SSE). Uses short DB txns inside orchestrator."""
    try:
        claim = claim_turn(
            conversation_id=conversation_id,
            owner_email=payload.owner_email,
            content=payload.content,
        )
    except ChatNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
    except RunInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "run_in_progress",
                "message": str(exc) or "A reply is already in progress",
            },
        ) from exc

    return StreamingResponse(
        iter_sse_for_claim(claim),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/cancel", response_model=ChatRunRead)
def post_cancel_run(
    run_id: uuid.UUID,
    payload: ChatRunCancel,
    _principal: Annotated[
        AuthPrincipal, Depends(require_chat_service_principal(SCOPE_CHAT_WRITE))
    ],
    response: Response,
):
    try:
        run = cancel_run(run_id=run_id, owner_email=payload.owner_email)
    except ChatNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": str(exc)},
        ) from exc
    response.status_code = status.HTTP_200_OK
    return run
