"""Add Auth.js v5 PostgreSQL adapter tables (users, accounts, sessions, verification_token).

Revision ID: 0003_authjs_tables
Revises: 09d577e3aed4

Owned by Alembic so Auth.js session tables share the same PostgreSQL instance
and migration path as PCC application tables (ADR 0003). Schema matches the
official @auth/pg-adapter SQL, with uniqueness and ON DELETE CASCADE foreign
keys for safer session revocation and account cleanup.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_authjs_tables"
down_revision: Union[str, None] = "09d577e3aed4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("emailVerified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("image", sa.Text(), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("userId", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("providerAccountId", sa.String(length=255), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.BigInteger(), nullable=True),
        sa.Column("id_token", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("session_state", sa.Text(), nullable=True),
        sa.Column("token_type", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["userId"],
            ["users.id"],
            name="fk_accounts_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "provider",
            "providerAccountId",
            name="uq_accounts_provider_provider_account_id",
        ),
    )
    op.create_index("ix_accounts_userId", "accounts", ["userId"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("userId", sa.Integer(), nullable=False),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sessionToken", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["userId"],
            ["users.id"],
            name="fk_sessions_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("sessionToken", name="uq_sessions_session_token"),
    )
    op.create_index("ix_sessions_userId", "sessions", ["userId"])

    op.create_table(
        "verification_token",
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("identifier", "token", name="pk_verification_token"),
    )


def downgrade() -> None:
    op.drop_table("verification_token")
    op.drop_index("ix_sessions_userId", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_accounts_userId", table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("users")
