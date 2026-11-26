"""Tablas base: workspace, project, clip, job y job_event.

Revision ID: 0001_initial_core_tables
Revises:
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_core_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_workspace_name"),
    )

    op.create_table(
        "project",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_clips", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("subtitle_preset", sa.String(length=64), nullable=False),
        sa.Column("reframe_mode", sa.String(length=16), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], name="fk_project_workspace"),
    )
    op.create_index("ix_project_workspace_id", "project", ["workspace_id"])

    op.create_table(
        "clip",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("candidate", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("hashtags", sa.JSON(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("thumb_path", sa.Text(), nullable=True),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("start_sec", sa.Float(), nullable=False),
        sa.Column("end_sec", sa.Float(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], name="fk_clip_project"),
    )
    op.create_index("ix_clip_project_id", "clip", ["project_id"])

    op.create_table(
        "job",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heavy_active", sa.Boolean(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], name="fk_job_project"),
    )
    op.create_index("ix_job_project_id", "job", ["project_id"])
    op.create_index(
        "ix_job_status_next_run_at_created_at",
        "job",
        ["status", "next_run_at", "created_at"],
    )

    op.create_table(
        "job_event",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_event_project_id", "job_event", ["project_id"])
    op.create_index("ix_job_event_project_id_id", "job_event", ["project_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_job_event_project_id_id", table_name="job_event")
    op.drop_index("ix_job_event_project_id", table_name="job_event")
    op.drop_table("job_event")

    op.drop_index("ix_job_status_next_run_at_created_at", table_name="job")
    op.drop_index("ix_job_project_id", table_name="job")
    op.drop_table("job")

    op.drop_index("ix_clip_project_id", table_name="clip")
    op.drop_table("clip")

    op.drop_index("ix_project_workspace_id", table_name="project")
    op.drop_table("project")

    op.drop_table("workspace")
