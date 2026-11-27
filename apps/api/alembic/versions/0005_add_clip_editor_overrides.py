"""Columnas JSON `render_overrides` y `subtitle_overrides` en `clip`.

Revision ID: 0005_add_clip_editor_overrides
Revises: 0004_add_publications
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_add_clip_editor_overrides"
down_revision: str | None = "0004_add_publications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clip") as batch_op:
        batch_op.add_column(sa.Column("render_overrides", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("subtitle_overrides", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("clip") as batch_op:
        batch_op.drop_column("subtitle_overrides")
        batch_op.drop_column("render_overrides")
