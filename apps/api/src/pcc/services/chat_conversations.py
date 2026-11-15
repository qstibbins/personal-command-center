"""Conversation CRUD helpers (Phase 1A.2 PR3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pcc.db.models import ChatRun, Conversation, Message
from pcc.schemas.chat import ConversationCreate, ConversationUpdate
from pcc.services.chat_ownership import normalize_owner_email, owner_email_equals
from pcc.services.chat_recovery import ActiveRunError, recover_abandoned_runs_locked


class ChatNotFoundError(Exception):
    pass


def create_conversation(db: Session, data: ConversationCreate) -> Conversation:
    conversation = Conversation(
        id=uuid.uuid4(),
        owner_email=normalize_owner_email(data.owner_email),
        title=data.title,
        default_provider=data.default_provider,
        default_model=data.default_model,
        system_prompt=data.system_prompt,
        status="active",
        source="pcc",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(
    db: Session,
    *,
    owner_email: str,
    limit: int = 50,
) -> list[Conversation]:
    owner = normalize_owner_email(owner_email)
    statement = (
        select(Conversation)
        .where(
            owner_email_equals(Conversation.owner_email, owner),
            Conversation.status != "deleted",
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())


def get_conversation(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    owner_email: str,
    include_deleted: bool = False,
) -> Conversation:
    owner = normalize_owner_email(owner_email)
    conversation = db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.owner_email != owner
        or (conversation.status == "deleted" and not include_deleted)
    ):
        raise ChatNotFoundError("Conversation not found")
    return conversation


def update_conversation(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    data: ConversationUpdate,
) -> Conversation:
    conversation = get_conversation(
        db,
        conversation_id=conversation_id,
        owner_email=data.owner_email,
    )
    if data.title is not None:
        conversation.title = data.title
    if data.status is not None:
        conversation.status = data.status
    conversation.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(conversation)
    return conversation


def soft_delete_conversation(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    owner_email: str,
) -> Conversation:
    """Soft-delete under row lock; refuse while a live run is active (HTTP 409).

    Abandoned (no local abort handle) running rows are recovered first so a
    crash cannot permanently block deletion under the single-worker assumption.
    """
    owner = normalize_owner_email(owner_email)
    conversation = (
        db.execute(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.owner_email == owner,
                Conversation.status != "deleted",
            )
            .with_for_update()
        )
        .scalar_one_or_none()
    )
    if conversation is None:
        raise ChatNotFoundError("Conversation not found")

    # Finalize crash leftovers before testing for a live stream.
    recover_abandoned_runs_locked(db, conversation_id=conversation_id)

    live_run_id = db.scalar(
        select(ChatRun.id).where(
            ChatRun.conversation_id == conversation_id,
            ChatRun.status == "running",
        )
    )
    if live_run_id is not None:
        # Remaining running rows are locally active (or recovery disabled).
        raise ActiveRunError(
            "Cannot delete conversation while a reply is in progress"
        )

    conversation.status = "deleted"
    conversation.deleted_at = datetime.now(UTC)
    conversation.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_messages(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    owner_email: str,
    limit: int = 200,
) -> list[Message]:
    get_conversation(
        db,
        conversation_id=conversation_id,
        owner_email=owner_email,
    )
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sequence.asc(), Message.id.asc())
        .limit(limit)
    )
    return list(db.scalars(statement).all())
