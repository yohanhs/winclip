"""Carga y validación de los presets de subtítulos (`assets/subtitle-presets/*.json`)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from winclip.core.config import ROOT_DIR

PRESETS_DIRNAME = "assets/subtitle-presets"
NO_SUBTITLES_PRESET = "none"
SAFE_ZONE_MIN = 0.62
SAFE_ZONE_MAX = 0.70
_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


class SubtitlePresetError(ValueError):
    """Preset inexistente, ilegible o inválido."""


class SubtitlePreset(BaseModel):
    """Esquema de preset de subtítulos (contrato B del design)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    font: str = Field(min_length=1)
    fallback_font: str = Field(min_length=1)
    font_size: int = Field(ge=12, le=240)
    uppercase: bool = False
    primary_color: str
    highlight_color: str
    outline_color: str
    outline_width: int = Field(default=0, ge=0, le=40)
    shadow_color: str = "#000000"
    shadow_depth: int = Field(default=0, ge=0, le=40)
    highlight_scale_pct: int = Field(default=110, ge=100, le=200)
    y_pct: float = Field(ge=SAFE_ZONE_MIN, le=SAFE_ZONE_MAX)
    margin_x: int = Field(default=80, ge=0, le=400)
    max_lines: int = Field(default=2, ge=1, le=2)
    max_chars_per_line: int = Field(ge=8, le=120)
    max_words_per_cue: int = Field(ge=1, le=20)
    max_pause_sec: float = Field(default=0.65, gt=0, le=5)
    box_bg_color: str | None = None

    @field_validator(
        "primary_color",
        "highlight_color",
        "outline_color",
        "shadow_color",
        "box_bg_color",
    )
    @classmethod
    def _valid_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _COLOR_PATTERN.fullmatch(value):
            raise ValueError(f"color inválido: {value!r}; usa #RRGGBB o #RRGGBBAA")
        return value.upper()


def presets_dir() -> Path:
    """Directorio de presets del repositorio."""
    return ROOT_DIR / PRESETS_DIRNAME


def list_presets(directory: Path | None = None) -> list[str]:
    """Nombres de los presets disponibles, ordenados alfabéticamente."""
    base = directory or presets_dir()
    if not base.is_dir():
        return []
    return sorted(path.stem for path in base.glob("*.json") if path.is_file())


def available_presets(directory: Path | None = None) -> str:
    """Lista legible para los mensajes de error de la CLI."""
    names = list_presets(directory)
    return ", ".join([*names, NO_SUBTITLES_PRESET]) if names else NO_SUBTITLES_PRESET


def is_valid_preset_name(name: str, *, directory: Path | None = None) -> bool:
    """True si `name` es `none` (sin subtítulos) o un preset JSON existente."""
    return name == NO_SUBTITLES_PRESET or name in list_presets(directory)


def load_preset(name: str, *, directory: Path | None = None) -> SubtitlePreset:
    """Carga `assets/subtitle-presets/<name>.json` validándolo con Pydantic."""
    base = directory or presets_dir()
    if not name or Path(name).name != name:
        raise SubtitlePresetError(f"nombre de preset inválido: {name!r}")
    path = base / f"{name}.json"
    if not path.is_file():
        raise SubtitlePresetError(
            f"no existe el preset {name!r}; disponibles: {available_presets(base)}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SubtitlePresetError(f"no se pudo leer el preset {path}: {exc}") from exc
    try:
        return SubtitlePreset.model_validate(payload)
    except ValueError as exc:
        raise SubtitlePresetError(f"preset inválido {path}: {exc}") from exc
