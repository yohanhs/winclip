"""Esquemas Pydantic de entrada y salida de la API (`/api`)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from winclip.pipeline.render_models import ReframeMode
from winclip.pipeline.subtitles.presets import SubtitlePreset

Language = Literal["auto", "es", "en"]
RequestedClips = int | Literal["max"]

# --------------------------------------------------------------------------- trabajos


class JobOut(BaseModel):
    """Estado completo de un trabajo (`GET /api/jobs/{id}`)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    type: str
    status: str
    progress: float
    stage: str
    error: str | None = None
    attempts: int
    max_attempts: int
    payload: dict = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class JobSummary(BaseModel):
    """Resumen de trabajo embebido en un proyecto."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    status: str
    progress: float
    stage: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- proyectos


class ProjectCreate(BaseModel):
    """Cuerpo JSON de `POST /api/projects` (URL)."""

    source_type: Literal["url", "file"] = "url"
    source_url: str | None = None
    title: str | None = Field(default=None, max_length=500)
    requested_clips: RequestedClips = 10
    language: Language = "auto"
    campaign_id: str | None = Field(default=None, max_length=64)
    subtitle_preset: str = "bold-yellow"
    reframe_mode: ReframeMode = "face"

    @field_validator("requested_clips")
    @classmethod
    def _positive_requested(cls, value: RequestedClips) -> RequestedClips:
        if isinstance(value, int) and value < 1:
            raise ValueError("requested_clips debe ser un entero >= 1 o 'max'")
        return value

    @field_validator("subtitle_preset")
    @classmethod
    def _preset_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("subtitle_preset no puede estar vacío")
        return value

    @model_validator(mode="after")
    def _url_required(self) -> ProjectCreate:
        if self.source_type == "url" and not (self.source_url or "").strip():
            raise ValueError("source_url es obligatoria cuando source_type es 'url'")
        return self


class ProjectOut(BaseModel):
    """Proyecto con resumen de clips y trabajos."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    campaign_id: str | None = None
    source_type: str
    source_url: str | None = None
    title: str
    status: str
    requested_clips: int | None = None
    language: str
    duration: float | None = None
    subtitle_preset: str
    reframe_mode: str
    clips_count: int = 0
    thumb_url: str | None = None
    active_job: JobSummary | None = None
    latest_job: JobSummary | None = None
    created_at: datetime
    updated_at: datetime
    jobs: list[JobOut] = Field(default_factory=list)


class ProjectCreated(BaseModel):
    """Respuesta `201` de `POST /api/projects`."""

    project: ProjectOut
    job: JobOut


# --------------------------------------------------------------------------- clips


class ClipOut(BaseModel):
    """Clip con URLs de video y miniatura."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    status: str
    title: str
    description: str
    hashtags: list[str]
    score: int
    hook: str
    start_sec: float
    end_sec: float
    duration: float
    video_url: str | None = None
    thumb_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ClipUpdate(BaseModel):
    """Campos editables de `PATCH /api/clips/{id}`."""

    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    hashtags: list[str] | None = None
    start_sec: Annotated[float | None, Field(ge=0)] = None
    end_sec: Annotated[float | None, Field(ge=0)] = None


# --------------------------------------------------------------------------- presets


class SubtitlePresetOut(BaseModel):
    """Preset de subtítulos con su identificador de catálogo."""

    id: str
    name: str
    description: str
    font: str
    fallback_font: str
    font_size: int
    uppercase: bool
    primary_color: str
    highlight_color: str
    outline_color: str
    outline_width: int
    shadow_color: str
    shadow_depth: int
    highlight_scale_pct: int
    y_pct: float
    margin_x: int
    max_lines: int
    max_chars_per_line: int
    max_words_per_cue: int
    max_pause_sec: float
    box_bg_color: str | None = None

    @classmethod
    def from_preset(cls, preset_id: str, preset: SubtitlePreset) -> SubtitlePresetOut:
        return cls(id=preset_id, **preset.model_dump())
