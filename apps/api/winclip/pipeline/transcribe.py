"""Transcripción local con marcas temporales por palabra.

El motor real (`mlx-whisper`) se importa de forma perezosa y queda detrás del
protocolo `TranscriberBackend`, para que la CLI, el futuro worker y los tests
compartan la misma interfaz sin depender de MLX.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from winclip.core.config import Settings, get_settings
from winclip.core.ids import validate_project_id
from winclip.core.storage import AUDIO_FILENAME, LocalStorage
from winclip.pipeline.schemas import (
    ProgressCallback,
    SourceMeta,
    Transcript,
    TranscriptSegment,
    WordTimestamp,
)

SUPPORTED_LANGUAGES = ("es", "en", "auto")
MODEL_ALIASES = {"tiny": "mlx-community/whisper-tiny"}
_AUDIO_SAMPLE_RATE = 16000
_LOAD_MODEL_PROGRESS = 5.0
_TRANSCRIBE_PROGRESS = 35.0
_SAVE_PROGRESS = 90.0


class TranscriptionError(RuntimeError):
    """Fallo de transcripción con un mensaje apto para mostrar al usuario."""


class AudioNotReadyError(TranscriptionError):
    """El proyecto no tiene `audio/audio16k.wav` (falta `winclip ingest`)."""


class TranscriberUnavailableError(TranscriptionError):
    """El motor de transcripción no está instalado en esta plataforma."""


@dataclass(frozen=True)
class RawWord:
    """Palabra tal como la devuelve el motor, sin normalizar."""

    w: str
    s: float
    e: float
    p: float | None = None


@dataclass(frozen=True)
class RawSegment:
    """Segmento tal como lo devuelve el motor, sin normalizar."""

    start: float
    end: float
    text: str
    words: list[RawWord] = field(default_factory=list)


@dataclass(frozen=True)
class RawTranscription:
    """Salida cruda de un backend de transcripción."""

    language: str | None
    duration: float | None
    segments: list[RawSegment] = field(default_factory=list)


class TranscriberBackend(Protocol):
    """Motor de transcripción inyectable."""

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        language: str | None,
    ) -> RawTranscription: ...


@dataclass(frozen=True)
class TranscriptionResult:
    """Transcripción disponible en disco."""

    project_id: str
    transcript: Transcript
    path: Path
    reused: bool


def _emit(progress: ProgressCallback | None, value: float, stage: str) -> None:
    if progress is not None:
        progress(max(0.0, min(100.0, value)), stage)


def resolve_model(model: str | None, settings: Settings) -> str:
    """Resuelve `--model`: atajo `tiny`, `WHISPER_MODEL` o repo HF explícito."""
    if not model or not model.strip():
        return settings.whisper_model
    value = model.strip()
    return MODEL_ALIASES.get(value.lower(), value)


def resolve_language(language: str | None) -> str | None:
    """`auto` (o vacío) → autodetección; `es`/`en` → idioma forzado."""
    if language is None:
        return None
    value = language.strip().lower()
    if value in {"", "auto"}:
        return None
    if value not in {"es", "en"}:
        raise TranscriptionError(
            f"idioma no soportado: {language!r}; valores válidos: es, en, auto"
        )
    return value


def _clean_text(text: str) -> str:
    return " ".join((text or "").split())


def _normalize_word(raw: RawWord) -> WordTimestamp | None:
    word = _clean_text(raw.w)
    if not word:
        return None
    start = max(0.0, float(raw.s))
    end = max(start, float(raw.e))
    probability = 1.0 if raw.p is None else min(1.0, max(0.0, float(raw.p)))
    return WordTimestamp(
        w=word,
        s=round(start, 3),
        e=round(end, 3),
        p=round(probability, 4),
    )


def normalize_transcription(
    raw: RawTranscription,
    *,
    model: str,
    language: str | None,
    duration: float | None = None,
) -> Transcript:
    """Normaliza la salida del motor al contrato `docs/architecture.md §6.1`."""
    segments: list[TranscriptSegment] = []
    ordered = sorted(raw.segments, key=lambda segment: (segment.start, segment.end))
    for index, segment in enumerate(ordered):
        start = max(0.0, float(segment.start))
        end = max(start, float(segment.end))
        words = [
            word
            for word in (_normalize_word(raw_word) for raw_word in segment.words)
            if word is not None
        ]
        segments.append(
            TranscriptSegment(
                id=index,
                start=round(start, 3),
                end=round(end, 3),
                text=_clean_text(segment.text),
                words=words,
            )
        )

    resolved_language = (raw.language or language or "").strip().lower() or "unknown"
    fallback_end = segments[-1].end if segments else 0.0
    total = duration if duration else (raw.duration or fallback_end)
    return Transcript(
        language=resolved_language,
        duration=round(max(0.0, float(total)), 3),
        model=model,
        segments=segments,
    )


def _raw_from_mlx(payload: dict[str, Any]) -> RawTranscription:
    segments: list[RawSegment] = []
    for segment in payload.get("segments") or []:
        words = [
            RawWord(
                w=str(word.get("word") or ""),
                s=float(word.get("start") or 0.0),
                e=float(word.get("end") or 0.0),
                p=word.get("probability"),
            )
            for word in segment.get("words") or []
        ]
        segments.append(
            RawSegment(
                start=float(segment.get("start") or 0.0),
                end=float(segment.get("end") or 0.0),
                text=str(segment.get("text") or ""),
                words=words,
            )
        )
    duration = payload.get("duration")
    return RawTranscription(
        language=payload.get("language"),
        duration=float(duration) if duration is not None else None,
        segments=segments,
    )


def _error_detail(text: str | None, limit: int = 400) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[-limit:] if cleaned else "sin detalle"


def _decode_audio(audio_path: Path, settings: Settings) -> Any:
    """Decodifica a float32 mono 16 kHz con `FFMPEG_BIN` (nunca el ffmpeg del PATH).

    `mlx_whisper.load_audio` invoca el `ffmpeg` del PATH, que puede ser el keg de
    Homebrew sin libass/dependencias rotas; por eso le pasamos muestras ya decodificadas.
    """
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - numpy llega con mlx-whisper
        raise TranscriberUnavailableError("numpy no está instalado en esta plataforma") from exc

    proc = subprocess.run(
        [
            str(settings.ffmpeg_bin),
            "-nostdin",
            "-i",
            str(audio_path),
            "-threads",
            "0",
            "-f",
            "s16le",
            "-ac",
            "1",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(_AUDIO_SAMPLE_RATE),
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise TranscriptionError(
            f"no se pudo decodificar {audio_path.name}: {_error_detail(proc.stderr.decode())}"
        )
    samples = np.frombuffer(proc.stdout, dtype=np.int16)
    if samples.size == 0:
        raise TranscriptionError(f"el audio {audio_path.name} está vacío")
    return samples.astype(np.float32) / 32768.0


class MlxWhisperBackend:
    """Backend de producción con `mlx-whisper` (importación perezosa)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def transcribe(
        self,
        audio_path: Path,
        *,
        model: str,
        language: str | None,
    ) -> RawTranscription:
        try:
            import mlx_whisper
        except ImportError as exc:  # pragma: no cover - depende de la plataforma
            raise TranscriberUnavailableError(
                "mlx-whisper no está instalado en esta plataforma (solo macOS arm64); "
                "instala las dependencias con uv sync"
            ) from exc

        audio = _decode_audio(audio_path, self.settings)
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=model,
            word_timestamps=True,
            language=language,
        )
        return _raw_from_mlx(result)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_meta(path: Path) -> SourceMeta | None:
    payload = _load_json(path)
    if payload is None:
        return None
    try:
        return SourceMeta.model_validate(payload)
    except ValidationError:
        return None


def _read_existing(path: Path) -> Transcript | None:
    payload = _load_json(path)
    if payload is None:
        return None
    try:
        return Transcript.model_validate(payload)
    except ValidationError:
        return None


def transcribe(
    project_id: str,
    *,
    settings: Settings,
    storage: LocalStorage | None = None,
    model: str | None = None,
    language: str = "auto",
    force: bool = False,
    backend: TranscriberBackend | None = None,
    progress: ProgressCallback | None = None,
) -> TranscriptionResult:
    """Transcribe `audio/audio16k.wav` y escribe `transcript/transcript.json`."""
    storage = storage or LocalStorage(settings.storage_dir)
    project_id = validate_project_id(project_id)
    audio_path = storage.audio_path(project_id)
    transcript_path = storage.transcript_path(project_id)

    if not audio_path.is_file():
        raise AudioNotReadyError(
            f"el proyecto {project_id} no tiene {AUDIO_FILENAME}; ejecuta winclip ingest primero"
        )

    if not force:
        existing = _read_existing(transcript_path)
        if existing is not None:
            _emit(progress, 100.0, "save")
            return TranscriptionResult(
                project_id=project_id,
                transcript=existing,
                path=transcript_path,
                reused=True,
            )

    requested_language = resolve_language(language)
    model_id = resolve_model(model, settings)
    engine = backend or MlxWhisperBackend(settings)

    _emit(progress, _LOAD_MODEL_PROGRESS, "load_model")
    _emit(progress, _TRANSCRIBE_PROGRESS, "transcribe")
    raw = engine.transcribe(audio_path, model=model_id, language=requested_language)

    meta = _read_meta(storage.source_meta_path(project_id))
    transcript = normalize_transcription(
        raw,
        model=model_id,
        language=requested_language,
        duration=meta.duration if meta is not None else None,
    )

    _emit(progress, _SAVE_PROGRESS, "save")
    storage.write_json_atomic(transcript_path, transcript)
    _emit(progress, 100.0, "save")

    return TranscriptionResult(
        project_id=project_id,
        transcript=transcript,
        path=transcript_path,
        reused=False,
    )
