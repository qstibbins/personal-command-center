"""Add provider-neutral chat tables (conversations, messages, usage, runs).

Revision ID: 0005_chat_schema
Revises: 0004_api_tokens

Phase 1A.2 PR1 — schema foundation only. No orchestration or claim logic.
Includes next_sequence, import provenance partial uniques, and one-running-run
partial unique index (see Phase 1A.1 architecture §B / §B7).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_chat_schema"
down_revision: Union[str, None] = "0004_api_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column("default_provider", sa.String(length=64), nullable=False),
        sa.Column("default_model", sa.String(length=128), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column(
            "next_sequence",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(length=64),
            server_default="pcc",
            nullable=False,
        ),
        sa.Column("source_external_id", sa.String(length=256), nullable=True),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="ck_conversations_status",
        ),
        sa.CheckConstraint(
            "source IN ('pcc', 'import:chatgpt', 'import:other')",
            name="ck_conversations_source",
        ),
        sa.CheckConstraint(
            "next_sequence >= 1",
            name="ck_conversations_next_sequence_positive",
        ),
    )
    op.create_index(
        "ix_conversations_owner_email_updated_at",
        "conversations",
        ["owner_email", sa.text("updated_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_conversations_source_external_id",
        "conversations",
        ["source", "source_external_id"],
        unique=True,
        postgresql_where=sa.text("source_external_id IS NOT NULL"),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "content_text",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "content_parts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("parent_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("source_external_id", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('system', 'user', 'assistant', 'tool')",
            name="ck_messages_role",
        ),
        sa.CheckConstraint(
            "status IN ('complete', 'streaming', 'partial', 'failed')",
            name="ck_messages_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_message_id"],
            ["messages.id"],
            name="fk_messages_parent_message_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name="uq_messages_conversation_id_sequence",
        ),
    )
    op.create_index(
        "uq_messages_conversation_source_external_id",
        "messages",
        ["conversation_id", "source_external_id"],
        unique=True,
        postgresql_where=sa.text("source_external_id IS NOT NULL"),
    )

    op.create_table(
        "message_usage",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_micros", sa.BigInteger(), nullable=True),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_message_usage_message_id",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "chat_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("request_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'cancelled', 'failed')",
            name="ck_chat_runs_status",
        ),
        sa.CheckConstraint(
            "cancel_reason IS NULL OR cancel_reason IN "
            "('client_stop', 'disconnect', 'superseded')",
            name="ck_chat_runs_cancel_reason",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_chat_runs_conversation_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_chat_runs_one_running_per_conversation",
        "chat_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "ix_chat_runs_conversation_id_started_at",
        "chat_runs",
        ["conversation_id", sa.text("started_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_runs_conversation_id_started_at",
        table_name="chat_runs",
    )
    op.drop_index(
        "uq_chat_runs_one_running_per_conversation",
        table_name="chat_runs",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_table("chat_runs")

    op.drop_table("message_usage")

    op.drop_index(
        "uq_messages_conversation_source_external_id",
        table_name="messages",
        postgresql_where=sa.text("source_external_id IS NOT NULL"),
    )
    op.drop_table("messages")

    op.drop_index(
        "uq_conversations_source_external_id",
        table_name="conversations",
        postgresql_where=sa.text("source_external_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_conversations_owner_email_updated_at",
        table_name="conversations",
    )
    op.drop_table("conversations")
