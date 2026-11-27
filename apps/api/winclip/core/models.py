"""Modelos SQLModel del dominio base (`docs/architecture.md §7`).

Tablas: `workspace`, `project`, `clip`, `job` y `job_event`. Las tablas de campañas,
cuentas sociales y publicaciones llegan en los changes 6-8 mediante nuevas revisiones
de Alembic, no aquí.

Todas las marcas temporales se guardan en UTC **naive** (SQLite no conserva zonas), para
poder compararlas directamente con `utcnow()`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel, UTCDateTime

DEFAULT_WORKSPACE_NAME = "Default"
PROJECT_STATUSES = ("queued", "processing", "ready", "failed", "cancelled")
CLIP_STATUSES = ("draft", "rendering", "rendered", "failed")
JOB_TYPES = ("ingest", "transcribe", "select", "render", "pipeline", "publish")
JOB_STATUSES = ("queued", "running", "done", "failed", "cancelled")
HEAVY_JOB_TYPES = frozenset({"transcribe", "render"})
TERMINAL_JOB_STATUSES = frozenset({"done", "failed", "cancelled"})
JOB_EVENT_TYPES = ("job.progress", "job.done", "job.failed", "clip.ready")
ACCOUNT_PLATFORMS = ("youtube", "tiktok", "instagram")
ACCOUNT_AUTH_METHODS = ("api", "playwright")
ACCOUNT_STATUSES = ("pending", "connected", "expired", "error")


def utcnow() -> datetime:
    """Ahora en UTC con zona; `UTCDateTime` la normaliza en SQLite."""
    return datetime.now(UTC)


class Workspace(SQLModel, table=True):
    """Espacio de trabajo (hoy uno por defecto, preparado para SaaS)."""

    __tablename__ = "workspace"
    __table_args__ = (UniqueConstraint("name", name="uq_workspace_name"),)

    id: str = Field(primary_key=True)
    name: str = Field(default=DEFAULT_WORKSPACE_NAME, max_length=120)
    created_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)


class Campaign(SQLModel, table=True):
    """Campaña de clipping con reglas editoriales y visuales (`docs/architecture.md §7`)."""

    __tablename__ = "campaign"

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    name: str = Field(max_length=120)
    rules_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    source_text: str | None = None
    created_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)
    updated_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)


class Project(SQLModel, table=True):
    """Proyecto de clipping: un video fuente y sus clips."""

    __tablename__ = "project"

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    campaign_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(64),
            ForeignKey("campaign.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    source_type: str = Field(default="file", max_length=16)
    source_url: str | None = None
    title: str = Field(default="", max_length=500)
    status: str = Field(default="queued", max_length=16)
    # `None` representa `"max"`.
    requested_clips: int | None = None
    language: str = Field(default="auto", max_length=8)
    duration: float | None = None
    subtitle_preset: str = Field(default="bold-yellow", max_length=64)
    reframe_mode: str = Field(default="face", max_length=16)
    # Ruta relativa bajo STORAGE_DIR (`projects/<id>/source/original.mp4`).
    source_path: str | None = None
    created_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)
    updated_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)


class Clip(SQLModel, table=True):
    """Clip candidato o renderizado de un proyecto."""

    __tablename__ = "clip"

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    candidate: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="draft", max_length=16)
    title: str = Field(default="", max_length=500)
    description: str = ""
    hashtags: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    score: int = Field(default=0)
    path: str | None = None
    thumb_path: str | None = None
    hook: str = ""
    start_sec: float = Field(default=0.0)
    end_sec: float = Field(default=0.0)
    duration: float = Field(default=0.0)
    created_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)
    updated_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)


class Job(SQLModel, table=True):
    """Trabajo de la cola persistente."""

    __tablename__ = "job"

    id: str = Field(primary_key=True)
    project_id: str | None = Field(default=None, foreign_key="project.id", index=True)
    type: str = Field(max_length=16)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="queued", max_length=16)
    progress: float = Field(default=0.0)
    stage: str = Field(default="queued", max_length=64)
    error: str | None = None
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=3)
    next_run_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    worker_id: str | None = Field(default=None, max_length=64)
    heartbeat_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    heavy_active: bool = Field(default=False)
    cancel_requested: bool = Field(default=False)
    created_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)
    started_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    finished_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    updated_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)


class JobEvent(SQLModel, table=True):
    """Outbox de eventos para SSE entre el worker y la API (design, decisión 4)."""

    __tablename__ = "job_event"

    id: int | None = Field(default=None, primary_key=True)
    project_id: str | None = Field(default=None, index=True)
    job_id: str | None = Field(default=None, max_length=64)
    event_type: str = Field(max_length=32)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)


class SocialAccount(SQLModel, table=True):
    """Cuenta social conectada por API oficial (OAuth) o perfil persistente Playwright."""

    __tablename__ = "social_account"

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    platform: str = Field(max_length=16, index=True)
    display_name: str = Field(default="", max_length=200)
    handle: str = Field(default="", max_length=200)
    alias: str | None = Field(default=None, max_length=120)
    avatar_url: str | None = None
    auth_method: str = Field(default="api", max_length=16)
    credentials_ref: str = Field(default="", max_length=255)
    status: str = Field(default="pending", max_length=16)
    is_default: bool = Field(default=False)
    capabilities_json: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    external_account_id: str | None = Field(default=None, max_length=128)
    token_expires_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    last_check_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    last_error: str | None = None
    created_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)
    updated_at: datetime = Field(sa_type=UTCDateTime, default_factory=utcnow)
