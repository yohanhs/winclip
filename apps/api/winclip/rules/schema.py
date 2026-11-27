"""Esquema de reglas de campaña (`docs/architecture.md §6.4`) y cargador de plantillas."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from winclip.core.config import ROOT_DIR
from winclip.pipeline.subtitles.presets import available_presets, is_valid_preset_name

RuleLanguage = Literal["es", "en", "auto"]
RuleTargetPlatform = Literal["youtube", "tiktok", "instagram"]
RuleSeverity = Literal["warning", "error"]
TemplateLanguage = Literal["es", "en"]

CAMPAIGN_TEMPLATES_DIRNAME = "assets/campaign-templates"
ALLOWED_WATERMARK_SUFFIXES = frozenset({".png", ".webp"})


def normalize_hashtags(values: list[str]) -> list[str]:
    """Normaliza hashtags con prefijo `#`, sin espacios y sin duplicados."""
    tags: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = " ".join(str(raw).split())
        if not cleaned:
            continue
        if not cleaned.startswith("#"):
            cleaned = f"#{cleaned}"
        cleaned = "#" + cleaned[1:].replace("#", "").replace(" ", "")
        if cleaned == "#":
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(cleaned)
    return tags


def _normalize_string_list(values: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in values:
        cleaned = " ".join(str(raw).split())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(cleaned)
    return items


def validate_watermark_path(value: str | None) -> str | None:
    """Valida que `watermark_path` sea relativa bajo `campaigns/` y `.png`/`.webp`."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "\\" in cleaned or cleaned.startswith("/"):
        raise ValueError("watermark_path debe ser una ruta relativa bajo 'campaigns/'")
    posix = PurePosixPath(cleaned)
    parts = posix.parts
    if not parts or any(part in {"..", "."} for part in parts):
        raise ValueError("watermark_path no puede contener segmentos '..' ni '.'")
    if parts[0] != "campaigns" or len(parts) < 2:
        raise ValueError("watermark_path debe ubicarse dentro de 'campaigns/'")
    if posix.suffix.lower() not in ALLOWED_WATERMARK_SUFFIXES:
        raise ValueError("watermark_path debe ser una imagen .png o .webp")
    return posix.as_posix()


class RuleViolation(BaseModel):
    """Infracción estructurada de una regla, embebida en `candidates.json §6.2`."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    field: str = Field(min_length=1)
    severity: RuleSeverity
    message: str = Field(min_length=1)


class CampaignRules(BaseModel):
    """Reglas de una campaña (`docs/architecture.md §6.4`) con validación estricta."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="default", min_length=1, max_length=120)
    language: RuleLanguage = "auto"
    min_duration: float = Field(default=20, ge=5, le=179)
    max_duration: float = Field(default=60, ge=6, le=180)
    max_clips: int | None = Field(default=None, ge=1, le=50)
    priority_topics: list[str] = Field(default_factory=list)
    banned_topics: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    tone: str | None = Field(default=None, max_length=120)
    hook_max_seconds: float = Field(default=3, ge=1, le=15)
    cta_text: str | None = Field(default=None, max_length=200)
    hashtags: list[str] = Field(default_factory=list)
    subtitle_preset: str | None = None
    watermark_path: str | None = None
    target_platforms: list[RuleTargetPlatform] = Field(default_factory=list)
    extra_instructions: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("name no puede estar vacío")
        if len(cleaned) > 120:
            raise ValueError("name no puede superar 120 caracteres")
        return cleaned

    @field_validator("priority_topics", "banned_topics", "banned_words", "required_keywords")
    @classmethod
    def _clean_lists(cls, value: list[str]) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("hashtags")
    @classmethod
    def _clean_hashtags(cls, value: list[str]) -> list[str]:
        return normalize_hashtags(value)

    @field_validator("tone", "cta_text", "extra_instructions")
    @classmethod
    def _clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("target_platforms")
    @classmethod
    def _dedupe_platforms(cls, value: list[RuleTargetPlatform]) -> list[RuleTargetPlatform]:
        deduped: list[RuleTargetPlatform] = []
        for platform in value:
            if platform not in deduped:
                deduped.append(platform)
        return deduped

    @field_validator("subtitle_preset")
    @classmethod
    def _valid_subtitle_preset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if not is_valid_preset_name(cleaned):
            raise ValueError(
                f"subtitle_preset desconocido: {cleaned!r}; disponibles: {available_presets()}"
            )
        return cleaned

    @field_validator("watermark_path")
    @classmethod
    def _valid_watermark_path(cls, value: str | None) -> str | None:
        return validate_watermark_path(value)

    @model_validator(mode="after")
    def _validate_durations(self) -> CampaignRules:
        if self.min_duration < 5:
            raise ValueError("min_duration debe ser >= 5 segundos")
        if self.max_duration > 180:
            raise ValueError("max_duration debe ser <= 180 segundos")
        if self.max_duration <= self.min_duration:
            raise ValueError("max_duration debe ser mayor que min_duration")
        if self.max_clips is not None and not (1 <= self.max_clips <= 50):
            raise ValueError("max_clips debe ser None o estar entre 1 y 50")
        if self.hook_max_seconds < 1 or self.hook_max_seconds > 15:
            raise ValueError("hook_max_seconds debe estar entre 1 y 15 segundos")
        if self.hook_max_seconds > self.min_duration:
            raise ValueError("hook_max_seconds no puede superar min_duration")
        return self


class CampaignTemplate(BaseModel):
    """Plantilla predefinida de campaña en español o inglés."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=400)
    language: TemplateLanguage
    rules: CampaignRules


class RulesFileError(ValueError):
    """El archivo de reglas no existe, no es JSON o no cumple el esquema §6.4."""


def templates_dir() -> Path:
    """Directorio de plantillas de campaña del repositorio."""
    return ROOT_DIR / CAMPAIGN_TEMPLATES_DIRNAME


def load_campaign_templates(directory: Path | None = None) -> list[CampaignTemplate]:
    """Carga y valida todas las plantillas de `assets/campaign-templates/*.json`."""
    base = directory or templates_dir()
    if not base.is_dir():
        return []
    templates: list[CampaignTemplate] = []
    for path in sorted(base.glob("*.json")):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RulesFileError(f"no se pudo leer la plantilla {path}: {exc}") from exc
        try:
            templates.append(CampaignTemplate.model_validate(payload))
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or 'raíz'}: {error['msg']}"
                for error in exc.errors()
            )
            raise RulesFileError(f"plantilla inválida en {path}: {details}") from exc
    return templates


def load_rules(path: Path | str) -> CampaignRules:
    """Carga y valida `rules.json`, con mensajes aptos para la CLI."""
    rules_path = Path(path).expanduser()
    try:
        raw = rules_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RulesFileError(f"no existe el archivo de reglas: {rules_path}") from exc
    except OSError as exc:
        raise RulesFileError(f"no se pudo leer el archivo de reglas {rules_path}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RulesFileError(
            f"el archivo de reglas no es JSON válido ({rules_path}): {exc.msg} "
            f"línea {exc.lineno}, columna {exc.colno}"
        ) from exc

    try:
        return CampaignRules.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'raíz'}: {error['msg']}"
            for error in exc.errors()
        )
        raise RulesFileError(f"reglas inválidas en {rules_path}: {details}") from exc
