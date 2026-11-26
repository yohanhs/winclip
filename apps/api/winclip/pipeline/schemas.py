"""Modelos Pydantic de los contratos en disco del pipeline.

`SourceMeta` describe `source/meta.json` (design del change `add-ingest-transcription`)
y `Transcript` implementa exactamente `docs/architecture.md §6.1`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# (progress: 0.0..100.0, stage: str), compatible con `job.progress` y `job.stage`.
ProgressCallback = Callable[[float, str], None]

SourceType = Literal["url", "file"]


class SourceMeta(BaseModel):
    """Metadatos técnicos y de origen del video ingestado (`source/meta.json`)."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    source_type: SourceType
    source_url: str | None = None
    original_filename: str = Field(min_length=1)
    title: str = Field(min_length=1)
    channel: str | None = None
    uploader_id: str | None = None
    duration: float = Field(ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    fps: float | None = Field(default=None, gt=0)
    video_codec: str | None = None
    audio_codec: str | None = None
    audio_sample_rate: int | None = Field(default=None, gt=0)
    has_audio: bool
    file_size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WordTimestamp(BaseModel):
    """Palabra con marcas temporales en segundos y probabilidad (`w`, `s`, `e`, `p`)."""

    model_config = ConfigDict(extra="forbid")

    w: str
    s: float = Field(ge=0)
    e: float = Field(ge=0)
    p: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _end_not_before_start(self) -> WordTimestamp:
        if self.e < self.s:
            raise ValueError("el fin de la palabra (e) no puede ser anterior al inicio (s)")
        return self


class TranscriptSegment(BaseModel):
    """Segmento de transcripción con su texto y sus palabras."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    words: list[WordTimestamp] = Field(default_factory=list)

    @model_validator(mode="after")
    def _end_not_before_start(self) -> TranscriptSegment:
        if self.end < self.start:
            raise ValueError("el fin del segmento (end) no puede ser anterior al inicio (start)")
        return self


class Transcript(BaseModel):
    """Contrato `transcript.json` (`docs/architecture.md §6.1`)."""

    model_config = ConfigDict(extra="forbid")

    language: str = Field(min_length=1)
    duration: float = Field(ge=0)
    model: str = Field(min_length=1)
    segments: list[TranscriptSegment] = Field(default_factory=list)
