"""Esquemas Pydantic de entrada y salida de la API (`/api`)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from winclip.pipeline.render_models import ReframeMode
from winclip.pipeline.subtitles.presets import (
    SubtitlePreset,
    available_presets,
    is_valid_preset_name,
)
from winclip.publishers.base import DeliveryMode, PublishMeta
from winclip.rules.schema import CampaignRules, RuleViolation, TemplateLanguage

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
    campaign_name: str | None = None
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


class ClipWordOut(BaseModel):
    """Palabra del tramo del clip con su clave estable y texto efectivo."""

    key: str
    index: int
    original: str
    text: str
    start: float
    end: float
    edited: bool = False


class ClipWordsOut(BaseModel):
    """Lista ordenada de palabras de un clip (`GET /api/clips/{id}/words`)."""

    clip_id: str
    words: list[ClipWordOut] = Field(default_factory=list)


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
    rule_violations: list[RuleViolation] = Field(default_factory=list)
    subtitle_preset: str | None = None
    reframe_mode: ReframeMode | None = None
    crop_x_pct: float | None = None
    crop_y_pct: float | None = None
    zoom_pct: float | None = None
    subtitle_overrides: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ClipUpdate(BaseModel):
    """Campos editables de `PATCH /api/clips/{id}`."""

    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    hashtags: list[str] | None = None
    start_sec: Annotated[float | None, Field(ge=0)] = None
    end_sec: Annotated[float | None, Field(ge=0)] = None
    subtitle_preset: str | None = None
    reframe_mode: ReframeMode | None = None
    crop_x_pct: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    crop_y_pct: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    zoom_pct: Annotated[float | None, Field(ge=50.0, le=200.0)] = None
    subtitle_overrides: dict[str, str] | None = None

    @field_validator("subtitle_preset")
    @classmethod
    def _valid_subtitle_preset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("subtitle_preset no puede estar vacío")
        if not is_valid_preset_name(cleaned):
            raise ValueError(
                f"subtitle_preset desconocido: {cleaned!r}; disponibles: {available_presets()}"
            )
        return cleaned

    @field_validator("subtitle_overrides")
    @classmethod
    def _valid_subtitle_overrides(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        cleaned: dict[str, str] = {}
        for raw_key, raw_word in value.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("las claves de subtitle_overrides no pueden estar vacías")
            word = str(raw_word).strip()
            if len(word) > 64:
                raise ValueError(
                    f"la palabra corregida para {key!r} supera el máximo de 64 caracteres"
                )
            if word:
                cleaned[key] = word
        return cleaned


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


# --------------------------------------------------------------------------- campañas


class CampaignCreate(BaseModel):
    """Cuerpo de `POST /api/campaigns`."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    rules: CampaignRules
    source_text: str | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("name no puede estar vacío")
        return cleaned


class CampaignUpdate(BaseModel):
    """Actualización parcial de `PATCH /api/campaigns/{id}`."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    rules: CampaignRules | None = None
    source_text: str | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("name no puede estar vacío")
        return cleaned


class CampaignOut(BaseModel):
    """Campaña persistida con sus reglas estructuradas."""

    id: str
    workspace_id: str
    name: str
    rules: CampaignRules
    source_text: str | None = None
    projects_count: int = 0
    created_at: datetime
    updated_at: datetime


class CampaignTemplateOut(BaseModel):
    """Plantilla predefinida de campaña ES/EN."""

    id: str
    title: str
    description: str
    language: TemplateLanguage
    rules: CampaignRules


class CampaignParseRequest(BaseModel):
    """Cuerpo de `POST /api/campaigns/parse`."""

    model_config = ConfigDict(extra="forbid")

    source_text: str = Field(min_length=1, max_length=20000)


class CampaignParseOut(BaseModel):
    """Propuesta generada desde un brief en texto libre (sin persistir)."""

    rules: CampaignRules
    inferred_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: str


class WatermarkUploadOut(BaseModel):
    """Respuesta de `POST /api/campaigns/watermarks`."""

    watermark_path: str


# --------------------------------------------------------------------------- cuentas sociales


AccountPlatform = Literal["youtube", "tiktok", "instagram"]
AccountAuthMethod = Literal["api", "playwright"]
AccountStatus = Literal["pending", "connected", "expired", "error"]
BrowserLoginSessionStatus = Literal["waiting", "connected", "timeout", "cancelled", "error"]


class SocialAccountOut(BaseModel):
    """Cuenta social sin exponer jamás tokens, secretos ni rutas absolutas."""

    id: str
    workspace_id: str
    platform: AccountPlatform
    display_name: str
    handle: str
    alias: str | None = None
    avatar_url: str | None = None
    auth_method: AccountAuthMethod
    status: AccountStatus
    is_default: bool
    capabilities: dict[str, object] = Field(default_factory=dict)
    external_account_id: str | None = None
    token_expires_at: datetime | None = None
    last_check_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class SocialAccountUpdate(BaseModel):
    """Actualización parcial de alias y/o cuenta por defecto (`PATCH /api/accounts/{id}`)."""

    model_config = ConfigDict(extra="forbid")

    alias: str | None = Field(default=None, max_length=120)
    is_default: bool | None = None

    @field_validator("alias")
    @classmethod
    def _clean_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class OAuthStartRequest(BaseModel):
    """Cuerpo opcional de `POST /api/accounts/oauth/{platform}/start`."""

    model_config = ConfigDict(extra="forbid")

    account_id: str | None = None
    direct_post: bool = False
    alias: str | None = Field(default=None, max_length=120)


class OAuthStartOut(BaseModel):
    """URL de autorización y estado anti-CSRF devueltos al iniciar OAuth."""

    auth_url: str
    state: str
    platform: AccountPlatform


class PlatformOAuthConfigOut(BaseModel):
    """Disponibilidad de configuración OAuth por plataforma (sin secretos)."""

    platform: AccountPlatform
    configured: bool
    missing: list[str] = Field(default_factory=list)


class AccountsOAuthConfigOut(BaseModel):
    """Estado de configuración OAuth para todas las plataformas."""

    platforms: list[PlatformOAuthConfigOut]


class InstagramCandidateOut(BaseModel):
    """Cuenta Business/Creator de Instagram elegible tras autorizar Meta."""

    external_account_id: str
    username: str
    display_name: str
    avatar_url: str | None = None
    page_name: str


class InstagramSelectionOut(BaseModel):
    """Lista temporal de cuentas elegibles de Instagram (`GET .../pending/{token}`)."""

    selection_token: str
    candidates: list[InstagramCandidateOut]


class InstagramSelectRequest(BaseModel):
    """Confirmación de cuentas Business/Creator de Instagram a registrar."""

    model_config = ConfigDict(extra="forbid")

    selection_token: str = Field(min_length=1)
    external_account_ids: list[str] = Field(min_length=1)


class BrowserLoginStartRequest(BaseModel):
    """Inicio o reconexión de login interactivo con navegador persistente."""

    model_config = ConfigDict(extra="forbid")

    platform: Literal["tiktok", "instagram"]
    account_id: str | None = None
    alias: str | None = Field(default=None, max_length=120)


class BrowserLoginOut(BaseModel):
    """Estado en vivo de una sesión de login con navegador."""

    account_id: str
    platform: AccountPlatform
    session_status: BrowserLoginSessionStatus
    error: str | None = None


class TokenImportRequest(BaseModel):
    """Importación de uno o varios tokens locales existentes en modo solo lectura."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=1000)
    platform: AccountPlatform | None = None
    alias: str | None = Field(default=None, max_length=120)


# --------------------------------------------------------------------------- publicaciones


PublicationStatus = Literal["scheduled", "publishing", "published", "failed", "cancelled"]


class AccountQuotaOut(BaseModel):
    """Resumen de uso diario y límite por cuenta."""

    account_id: str
    platform: AccountPlatform
    auth_method: AccountAuthMethod
    display_name: str
    handle: str
    alias: str | None = None
    used_today: int
    daily_limit: int
    remaining_today: int


class QuotaSummaryOut(BaseModel):
    """Resumen global de cuota YouTube y límites diarios por cuenta."""

    youtube_units_used: int
    youtube_units_limit: int
    youtube_upload_cost: int
    youtube_uploads_today: int
    accounts: list[AccountQuotaOut] = Field(default_factory=list)


class PreviewMetaRequest(BaseModel):
    """Cuerpo de `POST /api/publications/preview-meta`."""

    model_config = ConfigDict(extra="forbid")

    clip_ids: list[str] = Field(min_length=1)
    account_ids: list[str] = Field(min_length=1)


class PreviewMetaItemOut(BaseModel):
    """Metadatos propuestos para un par `(clip_id, account_id)`."""

    clip_id: str
    account_id: str
    platform: AccountPlatform
    auth_method: AccountAuthMethod
    delivery_mode: DeliveryMode
    meta: PublishMeta
    warnings: list[str] = Field(default_factory=list)


class PreviewMetaOut(BaseModel):
    """Respuesta de `POST /api/publications/preview-meta`."""

    items: list[PreviewMetaItemOut]
    warnings: list[str] = Field(default_factory=list)
    quota: QuotaSummaryOut


class PublicationCreateItem(BaseModel):
    """Un par `(clip, cuenta)` a encolar para publicación o programación."""

    model_config = ConfigDict(extra="forbid")

    clip_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    meta: PublishMeta
    scheduled_at: datetime | None = None


class PublicationsCreateRequest(BaseModel):
    """Cuerpo de `POST /api/publications`."""

    model_config = ConfigDict(extra="forbid")

    items: list[PublicationCreateItem] = Field(min_length=1)
    force: bool = False


class PublicationCancelRequest(BaseModel):
    """Cuerpo opcional de `POST /api/publications/{id}/cancel`."""

    model_config = ConfigDict(extra="forbid")

    delete_remote: bool = False


class PublicationOut(BaseModel):
    """Registro de publicación enriquecido para el historial `/publications`."""

    id: str
    workspace_id: str
    clip_id: str
    project_id: str | None = None
    project_title: str | None = None
    clip_title: str = ""
    clip_thumb_url: str | None = None
    account_id: str
    account_platform: AccountPlatform
    account_auth_method: AccountAuthMethod
    account_display_name: str = ""
    account_handle: str = ""
    account_alias: str | None = None
    job_id: str | None = None
    job_progress: float = 0.0
    job_stage: str | None = None
    status: PublicationStatus
    delivery_mode: DeliveryMode
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    meta: PublishMeta
    external_id: str | None = None
    external_url: str | None = None
    error: str | None = None
    error_code: str | None = None
    warnings: list[str] = Field(default_factory=list)
    has_screenshot: bool = False
    screenshot_url: str | None = None
    attempts: int = 0
    created_at: datetime
    updated_at: datetime


class PublicationDetailOut(PublicationOut):
    """Detalle completo de publicación incluyendo capturas por paso."""

    step_screenshots: list[str] = Field(default_factory=list)
