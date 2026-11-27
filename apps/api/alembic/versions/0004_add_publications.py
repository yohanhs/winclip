"""Tabla `publication` y columna diferida `job.run_at`.

Revision ID: 0004_add_publications
Revises: 0003_add_social_accounts
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_publications"
down_revision: str | None = "0003_add_social_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("job") as batch_op:
        batch_op.add_column(sa.Column("run_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_job_run_at", ["run_at"])

    op.create_table(
        "publication",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("clip_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="scheduled"),
        sa.Column("delivery_mode", sa.String(length=16), nullable=False, server_default="direct"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("screenshot_path", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspace.id"], name="fk_publication_workspace"
        ),
        sa.ForeignKeyConstraint(["clip_id"], ["clip.id"], name="fk_publication_clip"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["social_account.id"], name="fk_publication_account"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name="fk_publication_job", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_publication_workspace_id", "publication", ["workspace_id"])
    op.create_index("ix_publication_clip_id", "publication", ["clip_id"])
    op.create_index("ix_publication_account_id", "publication", ["account_id"])
    op.create_index("ix_publication_job_id", "publication", ["job_id"])
    op.create_index("ix_publication_status", "publication", ["status"])


def downgrade() -> None:
    op.drop_index("ix_publication_status", table_name="publication")
    op.drop_index("ix_publication_job_id", table_name="publication")
    op.drop_index("ix_publication_account_id", table_name="publication")
    op.drop_index("ix_publication_clip_id", table_name="publication")
    op.drop_index("ix_publication_workspace_id", table_name="publication")
    op.drop_table("publication")

    with op.batch_alter_table("job") as batch_op:
        batch_op.drop_index("ix_job_run_at")
        batch_op.drop_column("run_at")
