"""Tabla `social_account` para gestión multi-cuenta por plataforma.

Revision ID: 0003_add_social_accounts
Revises: 0002_add_campaigns
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_social_accounts"
down_revision: str | None = "0002_add_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "social_account",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("handle", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("alias", sa.String(length=120), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("auth_method", sa.String(length=16), nullable=False, server_default="api"),
        sa.Column("credentials_ref", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("external_account_id", sa.String(length=128), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspace.id"], name="fk_social_account_workspace"
        ),
    )
    op.create_index("ix_social_account_workspace_id", "social_account", ["workspace_id"])
    op.create_index("ix_social_account_platform", "social_account", ["platform"])
    op.create_index(
        "uq_social_account_default_per_platform",
        "social_account",
        ["workspace_id", "platform"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_social_account_default_per_platform", table_name="social_account")
    op.drop_index("ix_social_account_platform", table_name="social_account")
    op.drop_index("ix_social_account_workspace_id", table_name="social_account")
    op.drop_table("social_account")
