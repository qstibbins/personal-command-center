"""Conversation CRUD helpers (Phase 1A.2 PR3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pcc.db.models import Conversation, Message
from pcc.schemas.chat import ConversationCreate, ConversationUpdate
from pcc.services.chat_ownership import normalize_owner_email, owner_email_equals


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
    conversation = get_conversation(
        db,
        conversation_id=conversation_id,
        owner_email=owner_email,
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
