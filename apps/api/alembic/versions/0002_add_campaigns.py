"""Tabla `campaign` y FK `ON DELETE SET NULL` en `project.campaign_id`.

Revision ID: 0002_add_campaigns
Revises: 0001_initial_core_tables
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_add_campaigns"
down_revision: str | None = "0001_initial_core_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], name="fk_campaign_workspace"),
    )
    op.create_index("ix_campaign_workspace_id", "campaign", ["workspace_id"])

    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_project_campaign",
            "campaign",
            ["campaign_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_project_campaign_id", ["campaign_id"])


def downgrade() -> None:
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_index("ix_project_campaign_id")
        batch_op.drop_constraint("fk_project_campaign", type_="foreignkey")

    op.drop_index("ix_campaign_workspace_id", table_name="campaign")
    op.drop_table("campaign")
