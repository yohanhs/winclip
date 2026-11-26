"""Esquema de reglas de campaña (`docs/architecture.md §6.4`).

El CRUD de campañas y el parser de texto libre llegan en `add-campaign-rules`; este
change solo necesita cargar un `rules.json` opcional desde disco.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

RuleLanguage = Literal["es", "en", "auto"]
RuleTargetPlatform = Literal["youtube", "tiktok", "instagram"]
RuleSeverity = Literal["warning", "error"]


class RuleViolation(BaseModel):
    """Infracción estructurada de una regla, embebida en `candidates.json §6.2`."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    field: str = Field(min_length=1)
    severity: RuleSeverity
    message: str = Field(min_length=1)


class CampaignRules(BaseModel):
    """Reglas de una campaña con defaults seguros (todos los campos son opcionales)."""

    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    language: RuleLanguage = "auto"
    min_duration: float = 20
    max_duration: float = 60
    max_clips: int | None = None
    priority_topics: list[str] = Field(default_factory=list)
    banned_topics: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    tone: str | None = None
    hook_max_seconds: float = 3
    cta_text: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    subtitle_preset: str | None = None
    watermark_path: str | None = None
    target_platforms: list[RuleTargetPlatform] = Field(default_factory=list)
    extra_instructions: str | None = None

    @model_validator(mode="after")
    def _validate_durations(self) -> CampaignRules:
        if self.min_duration < 5:
            raise ValueError("min_duration debe ser >= 5 segundos")
        if self.max_duration <= self.min_duration:
            raise ValueError("max_duration debe ser mayor que min_duration")
        if self.max_clips is not None and self.max_clips < 1:
            raise ValueError("max_clips debe ser None o >= 1")
        if self.hook_max_seconds <= 0:
            raise ValueError("hook_max_seconds debe ser > 0")
        return self


class RulesFileError(ValueError):
    """El archivo de reglas no existe, no es JSON o no cumple el esquema §6.4."""


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
