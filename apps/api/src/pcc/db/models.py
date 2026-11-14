import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pcc.db.base import Base


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

class Capture(Base):
    __tablename__ = "captures"

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('text', 'url')",
            name="ck_captures_source_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'processed', 'failed')",
            name="ck_captures_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class ApiToken(Base):
    """Hashed, scoped, revocable bearer API tokens for non-browser clients."""

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    label: Mapped[str] = mapped_column(String(100), nullable=False)

    # Non-secret display prefix (e.g. "pcc_at_AbCd"); never enough to authenticate.
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False)

    # SHA-256 hex digest of the raw bearer token. Unique.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # JSON array of scope strings, e.g. ["captures:read"].
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Allowlisted operator email recorded at issuance (audit).
    created_by_email: Mapped[str] = mapped_column(String(320), nullable=False)


class Conversation(Base):
    """Provider-neutral chat conversation (Phase 1A)."""

    __tablename__ = "conversations"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="ck_conversations_status",
        ),
        CheckConstraint(
            "source IN ('pcc', 'import:chatgpt', 'import:other')",
            name="ck_conversations_source",
        ),
        CheckConstraint(
            "next_sequence >= 1",
            name="ck_conversations_next_sequence_positive",
        ),
        Index(
            "ix_conversations_owner_email_updated_at",
            "owner_email",
            desc("updated_at"),
        ),
        Index(
            "uq_conversations_source_external_id",
            "source",
            "source_external_id",
            unique=True,
            postgresql_where=text("source_external_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    owner_email: Mapped[str] = mapped_column(String(320), nullable=False)

    title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
    )

    default_provider: Mapped[str] = mapped_column(String(64), nullable=False)

    default_model: Mapped[str] = mapped_column(String(128), nullable=False)

    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    next_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="pcc",
        server_default="pcc",
    )

    source_external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["ChatRun"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(Base):
    """Provider-neutral chat message within a conversation."""

    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')",
            name="ck_messages_role",
        ),
        CheckConstraint(
            "status IN ('complete', 'streaming', 'partial', 'failed')",
            name="ck_messages_status",
        ),
        UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_messages_conversation_id_sequence",
        ),
        Index(
            "uq_messages_conversation_source_external_id",
            "conversation_id",
            "source_external_id",
            unique=True,
            postgresql_where=text("source_external_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    owner_email: Mapped[str] = mapped_column(String(320), nullable=False)

    role: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False)

    content_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )

    content_parts: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)

    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    parent_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_external_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    usage: Mapped["MessageUsage | None"] = relationship(
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )


class MessageUsage(Base):
    """Token/latency/cost usage for an assistant (or tool) message completion."""

    __tablename__ = "message_usage"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        primary_key=True,
    )

    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    cost_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    message: Mapped["Message"] = relationship(back_populates="usage")


class ChatRun(Base):
    """One assistant generation attempt for a conversation (cancel token = id)."""

    __tablename__ = "chat_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'cancelled', 'failed')",
            name="ck_chat_runs_status",
        ),
        CheckConstraint(
            "cancel_reason IS NULL OR cancel_reason IN "
            "('client_stop', 'disconnect', 'superseded')",
            name="ck_chat_runs_cancel_reason",
        ),
        Index(
            "uq_chat_runs_one_running_per_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        Index(
            "ix_chat_runs_conversation_id_started_at",
            "conversation_id",
            desc("started_at"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    owner_email: Mapped[str] = mapped_column(String(320), nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False)

    provider: Mapped[str] = mapped_column(String(64), nullable=False)

    model: Mapped[str] = mapped_column(String(128), nullable=False)

    request_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    response_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    cancel_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="runs")

