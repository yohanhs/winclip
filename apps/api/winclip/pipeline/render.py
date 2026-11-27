"""Renderizado completo de un candidato a clip vertical (`docs/architecture.md §6.3`).

Una sola pasada de `FFMPEG_BIN`: reencuadre 9:16 → hook → marca de agua → subtítulos
(`ass` o `pil`) → `loudnorm` + AAC, con codificación `h264_videotoolbox` en macOS y
respaldo `libx264` en Linux/CI. Los artefactos se escriben en un directorio temporal y
se publican con `os.replace` para que un fallo no deje clips corruptos.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from winclip.core.config import Settings, get_settings
from winclip.core.ids import new_ulid, validate_project_id
from winclip.core.storage import LocalStorage, StoragePathError
from winclip.pipeline.ingest import probe_media
from winclip.pipeline.reframe import (
    ReframeError,
    YuNetFaceDetector,
    build_reframe_filter,
    compute_reframe,
    ensure_yunet_model,
    sample_video_frames,
    sha256_file,
)
from winclip.pipeline.render_models import (
    DEFAULT_FPS,
    FINGERPRINT_FILENAME,
    MANIFEST_FILENAME,
    OUTPUT_FILENAME,
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    SUBTITLES_FILENAME,
    THUMBNAIL_FILENAME,
    RenderManifest,
    RenderOptions,
    RenderProgress,
    SubtitleSummary,
)
from winclip.pipeline.schemas import Transcript
from winclip.pipeline.select import CandidatesDocument
from winclip.pipeline.subtitles.ass_engine import write_ass
from winclip.pipeline.subtitles.fonts import (
    ResolvedFont,
    fonts_directory,
    measure_font,
    resolve_font,
)
from winclip.pipeline.subtitles.layout import build_cues, retime_words
from winclip.pipeline.subtitles.pil_engine import SubtitleFrameRenderer
from winclip.pipeline.subtitles.presets import SubtitlePreset, load_preset
from winclip.rules.schema import CampaignRules, validate_watermark_path

HOOK_CARD_FILENAME = "hook.png"
HOOK_CARD_TOP = 0.14
HOOK_CARD_HEIGHT = 0.08
HOOK_FADE_SECONDS = 0.3
CTA_CARD_FILENAME = "cta.png"
CTA_CARD_TOP = 0.54
CTA_CARD_HEIGHT = 0.06
CTA_FADE_SECONDS = 0.3
WATERMARK_MAX_WIDTH = 152
WATERMARK_MARGIN = 48
WATERMARK_TOP = 120
WATERMARK_OPACITY = 0.85
THUMB_SAMPLES = 5
THUMB_MIN_LUMINANCE = 15.0
PROGRESS_REFRAME_END = 20.0
PROGRESS_SUBTITLES_END = 30.0
PROGRESS_ENCODE_END = 95.0
LOW_LEVEL = "error"

_VIDEOTOOLBOX_CACHE: dict[str, bool] = {}
_FILTER_SCRIPT_CACHE: dict[str, bool] = {}


EMOJI_RANGES = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0xFE0F, 0xFE0F))


def contains_emoji(text: str) -> bool:
    """`True` si el texto incluye emojis (para incluir la fuente de color en fontsdir)."""
    return any(start <= ord(character) <= end for character in text for start, end in EMOJI_RANGES)


class RenderError(RuntimeError):
    """Error de renderizado con un mensaje apto para la CLI."""


class MissingRenderInputError(RenderError):
    """Falta la fuente, la transcripción o los candidatos del proyecto."""


class CandidateNotFoundError(RenderError):
    """El `candidate_id` no existe en `selection/candidates.json`."""


# --------------------------------------------------------------------------- entradas


def load_transcript(storage: LocalStorage, project_id: str) -> Transcript:
    """Lee `transcript/transcript.json` (§6.1)."""
    path = storage.transcript_path(project_id)
    if not path.is_file():
        raise MissingRenderInputError(
            f"no existe {path}; ejecuta primero `winclip transcribe {project_id}`"
        )
    try:
        return Transcript.model_validate(storage.read_json(path))
    except ValueError as exc:
        raise RenderError(f"transcript inválido en {path}: {exc}") from exc


def load_candidates(storage: LocalStorage, project_id: str) -> CandidatesDocument:
    """Lee `selection/candidates.json` (§6.2)."""
    path = storage.selection_path(project_id)
    if not path.is_file():
        raise MissingRenderInputError(
            f"no existe {path}; ejecuta primero `winclip select {project_id}`"
        )
    try:
        return CandidatesDocument.model_validate(storage.read_json(path))
    except ValueError as exc:
        raise RenderError(f"candidatos inválidos en {path}: {exc}") from exc


def find_source_video(storage: LocalStorage, project_id: str) -> Path:
    """Localiza `source/original.<ext>` del proyecto."""
    source_dir = storage.source_dir(project_id)
    candidates = sorted(
        path
        for path in source_dir.glob("original.*")
        if path.is_file() and path.suffix.lower() != ".json"
    )
    if not candidates:
        raise MissingRenderInputError(
            f"no hay video original en {source_dir}; ejecuta primero `winclip ingest`"
        )
    return candidates[0]


def output_fps(source_fps: float | None) -> float:
    """`30` si la fuente va por encima; si no, la tasa original redondeada."""
    if not source_fps or source_fps <= 0:
        return float(DEFAULT_FPS)
    if source_fps > DEFAULT_FPS:
        return float(DEFAULT_FPS)
    return float(max(1, min(DEFAULT_FPS, round(source_fps))))


# --------------------------------------------------------------------------- codificación


def detect_video_encoder(settings: Settings) -> str:
    """`h264_videotoolbox` si ffmpeg lo anuncia, si no `libx264` (CI/Linux)."""
    binary = str(settings.ffmpeg_bin)
    if binary in _VIDEOTOOLBOX_CACHE:
        return "h264_videotoolbox" if _VIDEOTOOLBOX_CACHE[binary] else "libx264"
    available = False
    try:
        result = subprocess.run(
            [binary, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        available = result.returncode == 0 and "h264_videotoolbox" in result.stdout
    except (OSError, subprocess.TimeoutExpired):
        available = False
    _VIDEOTOOLBOX_CACHE[binary] = available
    return "h264_videotoolbox" if available else "libx264"


def supports_filter_script(ffmpeg_bin: Path) -> bool:
    """`-filter_complex_script` existe en ffmpeg 6-8 y se eliminó en ffmpeg 9."""
    binary = str(ffmpeg_bin)
    if binary not in _FILTER_SCRIPT_CACHE:
        try:
            result = subprocess.run(
                [binary, "-hide_banner", "-h", "full"],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            _FILTER_SCRIPT_CACHE[binary] = "filter_complex_script" in result.stdout
        except (OSError, subprocess.TimeoutExpired):
            _FILTER_SCRIPT_CACHE[binary] = False
    return _FILTER_SCRIPT_CACHE[binary]


def filter_graph_arguments(ffmpeg_bin: Path, script: Path, graph: str) -> list[str]:
    """Pasa el grafo por archivo si el binario lo soporta; si no, como argumento."""
    if supports_filter_script(ffmpeg_bin):
        return ["-filter_complex_script", str(script)]
    return ["-filter_complex", graph]


def encoder_arguments(encoder: str) -> list[str]:
    """Argumentos de video por encoder, siempre en H.264 4:2:0 reproducible."""
    if encoder == "h264_videotoolbox":
        return [
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            "10M",
            "-maxrate",
            "14M",
            "-bufsize",
            "20M",
            "-profile:v",
            "high",
        ]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


# --------------------------------------------------------------------------- filtros


def build_hook_card(
    hook: str,
    path: Path,
    *,
    font_path: Path,
    font_size: int,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> Path:
    """Tarjeta RGBA con el texto del hook en la zona superior segura."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), font_size)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    max_text_width = width - 2 * 90
    lines: list[str] = []
    current = ""
    for word in hook.split():
        trial = f"{current} {word}".strip()
        if current and measure.textlength(trial, font=font) > max_text_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    lines = lines[:3]

    top = round(HOOK_CARD_TOP * height)
    line_height = round(font_size * 1.2)
    card_height = max(round(HOOK_CARD_HEIGHT * height), line_height * len(lines) + 40)
    draw.rounded_rectangle(
        (60, top, width - 60, top + card_height),
        radius=32,
        fill=(0, 0, 0, 165),
    )
    y = top + (card_height - line_height * len(lines)) / 2
    for line in lines:
        line_width = measure.textlength(line, font=font)
        draw.text(
            ((width - line_width) / 2, y),
            line,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 200),
        )
        y += line_height

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def build_cta_card(
    cta_text: str,
    path: Path,
    *,
    font_path: Path,
    font_size: int,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> Path:
    """Banner discreto de CTA sobre la zona segura de subtítulos para los últimos segundos."""
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cta_font_size = max(32, min(46, font_size - 12))
    font = ImageFont.truetype(str(font_path), cta_font_size)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    max_text_width = width - 2 * 110
    lines: list[str] = []
    current = ""
    for word in cta_text.split():
        trial = f"{current} {word}".strip()
        if current and measure.textlength(trial, font=font) > max_text_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    lines = lines[:2]

    top = round(CTA_CARD_TOP * height)
    line_height = round(cta_font_size * 1.25)
    card_height = max(round(CTA_CARD_HEIGHT * height), line_height * len(lines) + 28)
    max_line_width = max((measure.textlength(line, font=font) for line in lines), default=0.0)
    pill_width = min(width - 120, int(max_line_width + 76))
    left = (width - pill_width) // 2
    draw.rounded_rectangle(
        (left, top, left + pill_width, top + card_height),
        radius=24,
        fill=(17, 17, 20, 210),
        outline=(245, 158, 11, 220),
        width=3,
    )
    y = top + (card_height - line_height * len(lines)) / 2
    for line in lines:
        line_width = measure.textlength(line, font=font)
        draw.text(
            ((width - line_width) / 2, y),
            line,
            font=font,
            fill=(250, 250, 250, 255),
        )
        y += line_height

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def apply_campaign_to_render_options(
    options: RenderOptions,
    rules: CampaignRules | None,
    *,
    storage: LocalStorage,
    preset_overridden: bool = False,
) -> RenderOptions:
    """Aplica preset, `hook_max_seconds`, `watermark_path` seguro y `cta_text` de campaña."""
    if rules is None:
        return options
    updates: dict[str, Any] = {}
    if rules.subtitle_preset and not preset_overridden:
        updates["preset"] = rules.subtitle_preset
    updates["hook_seconds"] = min(options.hook_seconds, float(rules.hook_max_seconds))
    if rules.cta_text and not options.cta_text:
        updates["cta_text"] = rules.cta_text
    if rules.watermark_path and options.watermark_path is None:
        try:
            validated = validate_watermark_path(rules.watermark_path)
            resolved = None if validated is None else storage.resolve_safe(validated)
        except (ValueError, StoragePathError) as exc:
            raise RenderError(f"watermark_path inválido en campaña: {exc}") from exc
        if resolved is not None and resolved.is_file():
            updates["watermark_path"] = resolved
    return options.model_copy(update=updates)


def build_filter_graph(
    reframe_filter: str,
    *,
    fps: float,
    engine: str,
    subtitles_path: Path,
    fonts_dir: Path,
    hook_input: int | None,
    hook_seconds: float,
    watermark_input: int | None,
    overlay_input: int | None,
    has_audio: bool,
    cta_input: int | None = None,
    cta_start: float = 0.0,
) -> str:
    """Encadena reencuadre, overlays, subtítulos y audio en un solo `filter_complex`."""
    parts = [reframe_filter]
    current = "[vref]"

    if hook_input is not None:
        fade_start = max(0.0, hook_seconds - HOOK_FADE_SECONDS)
        parts.append(
            f"[{hook_input}:v]format=rgba,"
            f"fade=t=out:st={fade_start:.3f}:d={HOOK_FADE_SECONDS:.3f}:alpha=1[hookcard]"
        )
        parts.append(f"{current}[hookcard]overlay=0:0:enable='lt(t,{hook_seconds:.3f})'[vhook]")
        current = "[vhook]"

    if watermark_input is not None:
        parts.append(
            f"[{watermark_input}:v]scale={WATERMARK_MAX_WIDTH}:-2,format=rgba,"
            f"colorchannelmixer=aa={WATERMARK_OPACITY:g}[watermark]"
        )
        parts.append(f"{current}[watermark]overlay=W-w-{WATERMARK_MARGIN}:{WATERMARK_TOP}[vwm]")
        current = "[vwm]"

    if cta_input is not None:
        parts.append(
            f"[{cta_input}:v]format=rgba,"
            f"fade=t=in:st={cta_start:.3f}:d={CTA_FADE_SECONDS:.3f}:alpha=1[ctacard]"
        )
        parts.append(f"{current}[ctacard]overlay=0:0:enable='gte(t,{cta_start:.3f})'[vcta]")
        current = "[vcta]"

    if engine == "ass":
        parts.append(f"{current}ass=filename='{subtitles_path}':fontsdir='{fonts_dir}'[vsub]")
    else:
        parts.append(f"[{overlay_input}:v]format=rgba[subs]")
        parts.append(f"{current}[subs]overlay=0:0:format=auto[vsub]")
    current = "[vsub]"

    parts.append(f"{current}fps={fps:g},format=yuv420p[vout]")
    if has_audio:
        parts.append("[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    return ";\n".join(parts)


def parse_progress_line(line: str) -> float | None:
    """`out_time_us=123000` → segundos; `None` para otras claves de `-progress`."""
    key, _, value = line.strip().partition("=")
    if key != "out_time_us":
        return None
    try:
        return int(value) / 1_000_000
    except ValueError:
        return None


class _ProgressReporter:
    """Callback de progreso monotónico con fases ponderadas."""

    def __init__(
        self,
        clip_id: str,
        candidate_id: str,
        callback: Callable[[RenderProgress], None] | None,
    ) -> None:
        self.clip_id = clip_id
        self.candidate_id = candidate_id
        self.callback = callback
        self.last = -1.0

    def emit(self, stage: str, percent: float, message: str) -> None:
        value = max(self.last, min(100.0, percent))
        self.last = value
        if self.callback is not None:
            self.callback(
                RenderProgress(
                    clip_id=self.clip_id,
                    candidate_id=self.candidate_id,
                    stage=stage,  # type: ignore[arg-type]
                    percent=round(value, 2),
                    message=message,
                )
            )


# --------------------------------------------------------------------------- miniatura


def thumbnail_candidates(
    clip_path: Path,
    duration: float,
    *,
    settings: Settings,
) -> list[tuple[float, float]]:
    """Puntúa muestras del clip por rostro y nitidez (descarta fotogramas negros)."""
    import cv2

    moments: list[tuple[float, float]] = []
    if duration <= 0:
        return moments
    fps = max(0.5, THUMB_SAMPLES / duration)
    detector = None
    try:
        detector = YuNetFaceDetector(ensure_yunet_model(settings, download=False))
    except (ReframeError, OSError, RuntimeError):
        detector = None

    for moment, frame in sample_video_frames(
        clip_path,
        duration * 0.1,
        max(duration * 0.1 + 0.1, duration * 0.9),
        fps=fps,
        settings=settings,
        width=480,
    ):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if float(gray.mean()) < THUMB_MIN_LUMINANCE:
            continue
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        confidence = 0.0
        if detector is not None:
            faces = detector.detect(frame)
            confidence = max((face.confidence for face in faces), default=0.0)
        score = (
            (confidence + 0.25) * math.log1p(sharpness)
            if confidence
            else 0.25 * math.log1p(sharpness)
        )
        moments.append((score, moment))
    return moments


def extract_frame(video_path: Path, moment: float, target: Path, settings: Settings) -> Path:
    """Extrae un fotograma exacto como JPEG con `FFMPEG_BIN`."""
    result = subprocess.run(
        [
            str(settings.ffmpeg_bin),
            "-y",
            "-hide_banner",
            "-loglevel",
            LOW_LEVEL,
            "-ss",
            f"{max(0.0, moment):.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RenderError(
            "no se pudo generar la miniatura: " + (" ".join(result.stderr.split())[-400:] or "?")
        )
    return target


def choose_thumbnail(
    clip_path: Path,
    duration: float,
    target: Path,
    *,
    settings: Settings,
) -> Path:
    """Elige el mejor instante y escribe `thumb.jpg` (con respaldo al primer fotograma)."""
    moments = thumbnail_candidates(clip_path, duration, settings=settings)
    if moments:
        _, best = max(moments, key=lambda item: (item[0], -item[1]))
    else:
        best = min(duration * 0.1, max(0.0, duration - 0.1))
    return extract_frame(clip_path, best, target, settings)


# --------------------------------------------------------------------------- idempotencia


def compute_fingerprint(
    source: Path,
    candidate: Any,
    *,
    options: RenderOptions,
    preset: SubtitlePreset,
    font: ResolvedFont,
    fps: float,
) -> str:
    """Huella de idempotencia (nunca se escribe dentro de `render.json`)."""
    stat = source.stat()
    watermark = (
        sha256_file(options.watermark_path)
        if options.watermark_path is not None and Path(options.watermark_path).is_file()
        else None
    )
    payload = {
        "source": {
            "name": source.name,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        },
        "candidate": {
            "id": candidate.id,
            "start": candidate.start,
            "end": candidate.end,
            "hook": candidate.hook,
        },
        "options": {
            "preset": options.preset,
            "reframe": options.reframe,
            "engine": options.engine,
            "font": font.name,
            "font_file": font.font.path.name,
            "crop_x_pct": options.crop_x_pct,
            "crop_y_pct": options.crop_y_pct,
            "zoom_pct": options.zoom_pct,
            "word_overrides": dict(sorted(options.word_overrides.items())),
            "hook_overlay": options.hook_overlay,
            "hook_seconds": options.hook_seconds,
            "sample_fps": options.sample_fps,
            "watermark": watermark,
            "cta_text": options.cta_text,
            "cta_seconds": options.cta_seconds,
        },
        "preset": preset.model_dump(mode="json"),
        "fps": fps,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    import hashlib

    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _files_complete(directory: Path) -> bool:
    return all(
        (directory / name).is_file() and (directory / name).stat().st_size > 0
        for name in (OUTPUT_FILENAME, THUMBNAIL_FILENAME, SUBTITLES_FILENAME, MANIFEST_FILENAME)
    )


def find_existing_clip(clips_dir: Path, candidate_id: str) -> Path | None:
    """Directorio de un clip ya renderizado para el mismo candidato."""
    if not clips_dir.is_dir():
        return None
    for directory in sorted(clips_dir.iterdir()):
        manifest_path = directory / MANIFEST_FILENAME
        if not directory.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = RenderManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if manifest.candidate_id == candidate_id:
            return directory
    return None


def _is_fresh(directory: Path, fingerprint: str) -> bool:
    marker = directory / FINGERPRINT_FILENAME
    if not marker.is_file() or not _files_complete(directory):
        return False
    return marker.read_text(encoding="utf-8").strip() == fingerprint


def _publish(tmp: Path, target: Path, clips_dir: Path) -> None:
    """Sustituye el directorio final de forma atómica (con vuelta atrás)."""
    if not target.exists():
        os.replace(tmp, target)
        return
    trash = clips_dir / f".old-{new_ulid()}"
    os.replace(target, trash)
    try:
        os.replace(tmp, target)
    except BaseException:
        os.replace(trash, target)
        raise
    shutil.rmtree(trash, ignore_errors=True)


# --------------------------------------------------------------------------- ffmpeg


def _run_ffmpeg(
    command: list[str],
    *,
    duration: float,
    reporter: _ProgressReporter,
    frames: Iterable[np.ndarray] | None = None,
    fps: float = 30.0,
    frame_size: tuple[int, int] = (OUTPUT_WIDTH, OUTPUT_HEIGHT),
) -> None:
    """Ejecuta ffmpeg, alimenta frames RGBA si los hay y reporta progreso."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if frames is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    writer_error: list[BaseException] = []

    def write_frames() -> None:
        assert process.stdin is not None
        try:
            for frame in frames or []:
                process.stdin.write(frame.astype(np.uint8, copy=False).tobytes())
        except (BrokenPipeError, OSError) as exc:
            writer_error.append(exc)
        finally:
            with contextlib.suppress(OSError):
                process.stdin.close()

    thread = None
    if frames is not None:
        thread = threading.Thread(target=write_frames, daemon=True)
        thread.start()

    assert process.stdout is not None
    try:
        for raw_line in process.stdout:
            seconds = parse_progress_line(raw_line.decode("utf-8", "replace"))
            if seconds is None:
                continue
            ratio = min(1.0, seconds / duration) if duration > 0 else 1.0
            span = PROGRESS_ENCODE_END - PROGRESS_SUBTITLES_END
            percent = PROGRESS_SUBTITLES_END + ratio * span
            reporter.emit("encode", percent, f"codificando {seconds:.1f}/{duration:.1f} s")
    finally:
        process.stdout.close()

    if thread is not None:
        thread.join(timeout=30)
    stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr is not None else ""
    if process.stderr is not None:
        process.stderr.close()
    code = process.wait()
    if code != 0:
        detail = " ".join(stderr.split())[-500:] or "sin detalle"
        raise RenderError(f"ffmpeg falló (código {code}): {detail}")
    if writer_error:
        raise RenderError(f"no se pudieron enviar los subtítulos a ffmpeg: {writer_error[0]}")


def build_ffmpeg_command(
    ffmpeg_bin: Path,
    source: Path,
    *,
    start: float,
    duration: float,
    fps: float,
    filter_script: Path,
    graph: str,
    target: Path,
    encoder: str,
    hook_card: Path | None,
    watermark: Path | None,
    overlay: bool,
    has_audio: bool,
    cta_card: Path | None = None,
) -> tuple[list[str], int | None, int | None, int | None]:
    """Comando ffmpeg y los índices de entrada de hook, marca de agua y overlay."""
    command: list[str] = [str(ffmpeg_bin)]
    command.extend(
        [
            "-y",
            "-hide_banner",
            "-nostats",
            "-loglevel",
            LOW_LEVEL,
            "-progress",
            "pipe:1",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(source),
        ]
    )
    index = 1
    hook_input: int | None = None
    watermark_input: int | None = None
    overlay_input: int | None = None
    if hook_card is not None:
        command.extend(["-loop", "1", "-framerate", f"{fps:g}", "-i", str(hook_card)])
        hook_input = index
        index += 1
    if watermark is not None:
        command.extend(["-loop", "1", "-i", str(watermark)])
        watermark_input = index
        index += 1
    if cta_card is not None:
        command.extend(["-loop", "1", "-framerate", f"{fps:g}", "-i", str(cta_card)])
        index += 1
    if overlay:
        command.extend(
            [
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgba",
                "-s",
                f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
                "-r",
                f"{fps:g}",
                "-i",
                "pipe:0",
            ]
        )
        overlay_input = index
        index += 1

    command.extend(filter_graph_arguments(ffmpeg_bin, filter_script, graph))
    command.extend(["-map", "[vout]"])
    if has_audio:
        command.extend(["-map", "[aout]"])
    command.extend(encoder_arguments(encoder))
    if has_audio:
        command.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"])
    else:
        command.append("-an")
    command.extend(
        [
            "-t",
            f"{duration:.3f}",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )
    return command, hook_input, watermark_input, overlay_input


def _read_manifest(directory: Path) -> RenderManifest:
    return RenderManifest.model_validate_json(
        (directory / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )


def render_clip(
    project_id: str,
    candidate_id: str,
    options: RenderOptions,
    *,
    settings: Settings | None = None,
    on_progress: Callable[[RenderProgress], None] | None = None,
    clip_id: str | None = None,
    campaign_rules: CampaignRules | None = None,
) -> RenderManifest:
    """Renderiza un candidato a `clips/<clip_id>/` y devuelve su manifiesto.

    `clip_id` permite que el worker use el identificador de la fila `clip`, de modo que
    el directorio publicado coincida con `docs/architecture.md §5`; por CLI se genera un
    ULID nuevo cuando el candidato aún no tiene carpeta.
    """
    settings = settings or get_settings()
    storage = LocalStorage(settings.storage_dir)
    validate_project_id(project_id)
    if campaign_rules is not None:
        options = apply_campaign_to_render_options(options, campaign_rules, storage=storage)

    transcript = load_transcript(storage, project_id)
    document = load_candidates(storage, project_id)
    candidate = next((item for item in document.candidates if item.id == candidate_id), None)
    if candidate is None:
        available = ", ".join(item.id for item in document.candidates) or "(ninguno)"
        raise CandidateNotFoundError(
            f"no existe el candidato {candidate_id!r} en {storage.selection_path(project_id)}; "
            f"disponibles: {available}"
        )

    source = find_source_video(storage, project_id)
    probe = probe_media(source, settings)
    fps = output_fps(probe.fps)
    preset = load_preset(options.preset)
    font = resolve_font(
        options.font or preset.font,
        fallback=preset.fallback_font,
        settings=settings,
    )

    clips_dir = storage.project_dir(project_id) / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = compute_fingerprint(
        source,
        candidate,
        options=options,
        preset=preset,
        font=font,
        fps=fps,
    )

    existing = find_existing_clip(clips_dir, candidate.id)
    if existing is not None and not options.force and _is_fresh(existing, fingerprint):
        manifest = _read_manifest(existing)
        if on_progress is not None:
            on_progress(
                RenderProgress(
                    clip_id=manifest.clip_id,
                    candidate_id=candidate.id,
                    stage="thumbnail",
                    percent=100.0,
                    message="clip ya renderizado (sin cambios)",
                )
            )
        return manifest

    desired_clip_id = validate_project_id(clip_id) if clip_id else None
    clip_id = existing.name if existing is not None else desired_clip_id or new_ulid()
    tmp_dir = clips_dir / f".tmp-{new_ulid()}"
    tmp_dir.mkdir(parents=True, exist_ok=False)
    reporter = _ProgressReporter(clip_id, candidate.id, on_progress)
    duration = round(candidate.end - candidate.start, 3)

    try:
        reporter.emit("reframe", 1.0, f"analizando reencuadre ({options.reframe})")
        reframe_result = compute_reframe(
            source,
            candidate.start,
            candidate.end,
            mode=options.reframe,
            options_fps=options.sample_fps,
            settings=settings,
            crop_x_pct=options.crop_x_pct,
            crop_y_pct=options.crop_y_pct,
            zoom_pct=options.zoom_pct,
        )
        reporter.emit("reframe", PROGRESS_REFRAME_END, f"modo {reframe_result.mode}")

        reporter.emit("subtitles", PROGRESS_REFRAME_END + 1, "generando subtítulos")
        words = retime_words(
            transcript,
            candidate.start,
            candidate.end,
            uppercase=preset.uppercase,
            word_overrides=options.word_overrides or None,
        )
        measure = measure_font(font.font.path, preset.font_size)
        cues = build_cues(words, preset, measure=measure)
        write_ass(
            tmp_dir / SUBTITLES_FILENAME,
            cues,
            preset,
            font_name=font.ass_name,
            measure=measure,
        )
        font_files = [font.font]
        if any(contains_emoji(word.text) for word in words):
            emoji = resolve_font(
                "Noto Color Emoji",
                fallback=preset.fallback_font,
                settings=settings,
            )
            if not emoji.fallback_used:
                font_files.append(emoji.font)
        overlay_frames: Iterable[np.ndarray] | None = None
        if options.engine == "pil":
            overlay_frames = SubtitleFrameRenderer(cues, preset, font.font.path).iter_frames(
                duration, fps
            )
        reporter.emit("subtitles", PROGRESS_SUBTITLES_END, f"{len(cues)} bloques")

        hook_active = options.hook_overlay and bool(candidate.hook.strip())
        cta_active = bool((options.cta_text or "").strip())
        cta_start = max(0.0, round(duration - options.cta_seconds, 3))
        encoder = detect_video_encoder(settings)
        subtitles_path = tmp_dir / SUBTITLES_FILENAME
        with tempfile.TemporaryDirectory(prefix="winclip-render-") as work_raw:
            work = Path(work_raw)
            hook_card: Path | None = None
            if hook_active:
                hook_card = build_hook_card(
                    candidate.hook,
                    work / HOOK_CARD_FILENAME,
                    font_path=font.font.path,
                    font_size=max(40, preset.font_size - 6),
                )
            cta_card: Path | None = None
            if cta_active and options.cta_text:
                cta_card = build_cta_card(
                    options.cta_text,
                    work / CTA_CARD_FILENAME,
                    font_path=font.font.path,
                    font_size=max(40, preset.font_size - 6),
                )
            with fonts_directory(font_files) as fonts_dir:
                filter_script = work / "filter_complex.txt"
                overlay = options.engine == "pil"
                next_index = 1
                hook_index: int | None = None
                watermark_index: int | None = None
                cta_index: int | None = None
                overlay_index: int | None = None
                if hook_card is not None:
                    hook_index = next_index
                    next_index += 1
                if options.watermark_path is not None:
                    watermark_index = next_index
                    next_index += 1
                if cta_card is not None:
                    cta_index = next_index
                    next_index += 1
                if overlay:
                    overlay_index = next_index
                    next_index += 1
                graph = build_filter_graph(
                    build_reframe_filter(
                        reframe_result,
                        crop_x_pct=options.crop_x_pct,
                        crop_y_pct=options.crop_y_pct,
                    ),
                    fps=fps,
                    engine=options.engine,
                    subtitles_path=subtitles_path,
                    fonts_dir=fonts_dir,
                    hook_input=hook_index,
                    hook_seconds=options.hook_seconds,
                    watermark_input=watermark_index,
                    overlay_input=overlay_index,
                    has_audio=probe.has_audio,
                    cta_input=cta_index,
                    cta_start=cta_start,
                )
                filter_script.write_text(graph + "\n", encoding="utf-8")
                command, _, _, _ = build_ffmpeg_command(
                    settings.ffmpeg_bin,
                    source,
                    start=candidate.start,
                    duration=duration,
                    fps=fps,
                    filter_script=filter_script,
                    graph=graph,
                    target=tmp_dir / OUTPUT_FILENAME,
                    encoder=encoder,
                    hook_card=hook_card,
                    watermark=options.watermark_path,
                    overlay=overlay,
                    has_audio=probe.has_audio,
                    cta_card=cta_card,
                )

                reporter.emit("encode", PROGRESS_SUBTITLES_END, f"codificando con {encoder}")
                _run_ffmpeg(
                    command,
                    duration=duration,
                    reporter=reporter,
                    frames=overlay_frames,
                    fps=fps,
                )

        reporter.emit("thumbnail", PROGRESS_ENCODE_END, "eligiendo miniatura")
        choose_thumbnail(
            tmp_dir / OUTPUT_FILENAME,
            duration,
            tmp_dir / THUMBNAIL_FILENAME,
            settings=settings,
        )

        manifest = RenderManifest(
            clip_id=clip_id,
            candidate_id=candidate.id,
            width=OUTPUT_WIDTH,
            height=OUTPUT_HEIGHT,
            fps=fps,
            reframe=reframe_result.manifest_spec(),
            subtitles=SubtitleSummary(
                engine=options.engine,
                preset=preset.name,
                font=font.name,
            ),
            hook_overlay=hook_active,
            duration=duration,
            output=OUTPUT_FILENAME,
            thumbnail=THUMBNAIL_FILENAME,
        )
        (tmp_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (tmp_dir / FINGERPRINT_FILENAME).write_text(fingerprint + "\n", encoding="utf-8")

        destination = clips_dir / clip_id
        _publish(tmp_dir, destination, clips_dir)
        reporter.emit("thumbnail", 100.0, f"clip listo en {destination}")
        return manifest
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def render_project_clips(
    project_id: str,
    *,
    options: RenderOptions,
    all_clips: bool = False,
    candidate_ids: list[str] | None = None,
    settings: Settings | None = None,
    on_progress: Callable[[RenderProgress], None] | None = None,
) -> list[RenderManifest]:
    """Renderiza un candidato, una lista o todos los candidatos del proyecto."""
    settings = settings or get_settings()
    storage = LocalStorage(settings.storage_dir)
    validate_project_id(project_id)
    if all_clips and candidate_ids:
        raise RenderError("usa `--all` o `--clip`, no ambos")
    if not all_clips and not candidate_ids:
        raise RenderError("indica `--clip <candidate_id>` o `--all`")

    document = load_candidates(storage, project_id)
    if all_clips:
        selected = [candidate.id for candidate in document.candidates]
    else:
        selected = list(candidate_ids or [])
    if not selected:
        raise RenderError("el proyecto no tiene candidatos que renderizar")

    manifests: list[RenderManifest] = []
    for candidate_id in selected:
        manifests.append(
            render_clip(
                project_id,
                candidate_id,
                options,
                settings=settings,
                on_progress=on_progress,
            )
        )
    return manifests
