"""Modelos del renderizado de clips (`docs/architecture.md §6.3`).

`RenderManifest` reproduce exactamente los 11 campos del contrato; la huella de
idempotencia se guarda aparte en `.render.sha256` para no añadir claves al JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReframeMode = Literal["face", "center", "blur", "passthrough"]
ReframeRequestMode = Literal["face", "center", "blur"]
SubtitleEngine = Literal["ass", "pil"]
RenderStage = Literal["reframe", "subtitles", "encode", "thumbnail"]

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
DEFAULT_FPS = 30
OUTPUT_FILENAME = "clip.mp4"
THUMBNAIL_FILENAME = "thumb.jpg"
SUBTITLES_FILENAME = "subs.ass"
MANIFEST_FILENAME = "render.json"
FINGERPRINT_FILENAME = ".render.sha256"
CLIPS_DIR = "clips"


class SubtitleSummary(BaseModel):
    """Motor, preset y fuente efectiva registrados en `render.json`."""

    model_config = ConfigDict(extra="forbid")

    engine: SubtitleEngine
    preset: str = Field(min_length=1)
    font: str = Field(min_length=1)


class ReframeSpec(BaseModel):
    """Modo de reencuadre y trayectoria horizontal normalizada (`[t, x_norm]`)."""

    model_config = ConfigDict(extra="forbid")

    mode: ReframeMode
    track: list[tuple[float, float]] = Field(default_factory=list)

    @field_validator("track")
    @classmethod
    def _valid_track(cls, track: list[tuple[float, float]]) -> list[tuple[float, float]]:
        previous = -1.0
        for moment, position in track:
            if moment < 0:
                raise ValueError("el instante de la trayectoria no puede ser negativo")
            if not 0.0 <= position <= 1.0:
                raise ValueError("la posición de la trayectoria debe estar en [0, 1]")
            if moment < previous:
                raise ValueError("la trayectoria no puede retroceder en el tiempo")
            previous = moment
        return track


class RenderManifest(BaseModel):
    """Contrato `clips/<clip_id>/render.json` (`docs/architecture.md §6.3`)."""

    model_config = ConfigDict(extra="forbid")

    clip_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    reframe: ReframeSpec
    subtitles: SubtitleSummary
    hook_overlay: bool
    duration: float = Field(gt=0)
    output: str = Field(min_length=1)
    thumbnail: str = Field(min_length=1)


class ReframeResult(BaseModel):
    """Resultado del análisis de reencuadre y parámetros del recorte."""

    model_config = ConfigDict(extra="forbid")

    mode: ReframeMode
    track: list[tuple[float, float]] = Field(default_factory=list)
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    crop_width: int = Field(gt=0)
    crop_height: int = Field(gt=0)
    faces_detected: int = Field(default=0, ge=0)
    shots: int = Field(default=1, ge=1)

    def manifest_spec(self) -> ReframeSpec:
        """Vista `reframe` para `render.json`."""
        return ReframeSpec(mode=self.mode, track=list(self.track))


class RenderOptions(BaseModel):
    """Opciones de `render_clip`: preset, reencuadre, subtítulos y overlays."""

    model_config = ConfigDict(extra="forbid")

    preset: str = "bold-yellow"
    reframe: ReframeRequestMode = "face"
    engine: SubtitleEngine = "ass"
    font: str | None = None
    crop_x_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    crop_y_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    zoom_pct: float = Field(default=100.0, ge=100.0, le=300.0)
    hook_overlay: bool = True
    hook_seconds: float = Field(default=3.0, ge=0.5, le=10.0)
    watermark_path: Path | None = None
    force: bool = False
    sample_fps: float = Field(default=3.0, ge=2.0, le=4.0)

    @model_validator(mode="after")
    def _watermark_must_exist(self) -> RenderOptions:
        if self.watermark_path is not None and not self.watermark_path.is_file():
            raise ValueError(f"no existe el archivo de marca de agua: {self.watermark_path}")
        return self


@dataclass(frozen=True)
class RenderProgress:
    """Progreso reportable por la CLI y, más adelante, por el worker."""

    clip_id: str
    candidate_id: str
    stage: RenderStage
    percent: float
    message: str
