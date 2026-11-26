"""Ingesta de medios: URL remota (yt-dlp) o archivo local.

Flujo: obtener `source/original.<ext>` → inspeccionar con `FFPROBE_BIN` →
extraer `audio/audio16k.wav` con `FFMPEG_BIN` → escribir `source/meta.json`
(último paso, para que el archivo solo exista cuando el proyecto está listo).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

import yt_dlp

from winclip.core.config import Settings
from winclip.core.ids import new_project_id, validate_project_id
from winclip.core.storage import LocalStorage
from winclip.pipeline.schemas import ProgressCallback, SourceMeta

SUPPORTED_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})
DOWNLOAD_FORMAT = (
    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
    "best[height<=1080][ext=mp4]/best[height<=1080]"
)
COPY_FILENAME = "original"
DOWNLOAD_PROGRESS_END = 65.0
PROBE_PROGRESS_END = 75.0
_AUDIO_SAMPLE_RATE = 16000


class IngestError(RuntimeError):
    """Fallo de ingesta con un mensaje apto para mostrar al usuario."""


class InvalidUrlError(IngestError):
    """La URL no es válida o no está soportada por yt-dlp."""


class PrivateVideoError(IngestError):
    """El video es privado o exige autenticación."""


class LiveStreamNotSupportedError(IngestError):
    """La URL apunta a una transmisión en directo en curso."""


class MissingAudioError(IngestError):
    """El video no tiene pista de audio que transcribir."""


class ProjectExistsError(IngestError):
    """El proyecto ya tiene `source/meta.json` y no se pidió `--force`."""


@dataclass(frozen=True)
class DownloadedMedia:
    """Resultado de una descarga remota."""

    path: Path
    title: str | None = None
    channel: str | None = None
    uploader_id: str | None = None
    duration: float | None = None


class MediaDownloader(Protocol):
    """Adaptador inyectable de descarga (yt-dlp en producción, fakes en tests)."""

    def download(
        self,
        url: str,
        destination: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> DownloadedMedia: ...


@dataclass(frozen=True)
class ProbeResult:
    """Metadatos técnicos obtenidos con `FFPROBE_BIN`."""

    duration: float
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    audio_sample_rate: int | None
    has_audio: bool


@dataclass(frozen=True)
class IngestResult:
    """Proyecto ingestado y rutas generadas."""

    project_id: str
    meta: SourceMeta
    video_path: Path
    audio_path: Path


def _emit(progress: ProgressCallback | None, value: float, stage: str) -> None:
    if progress is not None:
        progress(max(0.0, min(100.0, value)), stage)


def _stderr_tail(text: str | None, limit: int = 400) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[-limit:] if cleaned else "sin detalle"


def _is_url(source: str) -> bool:
    return urlparse(source).scheme in {"http", "https"}


def _classify_download_error(message: str) -> IngestError:
    """Traduce el mensaje de yt-dlp a una excepción de dominio."""
    text = message.lower()
    if any(
        key in text
        for key in (
            "private video",
            "private",
            "sign in",
            "login",
            "members-only",
            "requires authentication",
            "confirm your age",
            "cookies",
        )
    ):
        return PrivateVideoError(
            f"el video es privado o no está disponible sin autenticación: {message}"
        )
    if any(
        key in text
        for key in (
            "unsupported url",
            "is not a valid url",
            "invalid url",
            "no video formats",
            "not a valid",
        )
    ):
        return InvalidUrlError(f"URL inválida o no soportada: {message}")
    return IngestError(f"no se pudo descargar el video: {message}")


class YtDlpDownloader:
    """Descarga con el paquete Python `yt-dlp` (sin subproceso)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _options(
        self,
        destination: Path,
        on_progress: Callable[[float], None] | None,
    ) -> dict[str, Any]:
        def progress_hook(status: dict[str, Any]) -> None:
            if on_progress is None or status.get("status") != "downloading":
                return
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            downloaded = status.get("downloaded_bytes") or 0
            if total:
                on_progress(min(100.0, float(downloaded) / float(total) * 100.0))

        return {
            "format": DOWNLOAD_FORMAT,
            "merge_output_format": "mp4",
            "ffmpeg_location": str(self.settings.ffmpeg_bin),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": str(destination / f"{COPY_FILENAME}.%(ext)s"),
            "progress_hooks": [progress_hook],
        }

    def _ensure_supported_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise InvalidUrlError(f"URL inválida o no soportada: {url}")

    def download(
        self,
        url: str,
        destination: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> DownloadedMedia:
        self._ensure_supported_url(url)
        destination.mkdir(parents=True, exist_ok=True)
        with yt_dlp.YoutubeDL(self._options(destination, on_progress)) as ydl:
            try:
                # Comprobación previa: rechazar directos antes de transferir datos.
                info = ydl.extract_info(url, download=False) or {}
            except yt_dlp.utils.DownloadError as exc:
                raise _classify_download_error(str(exc)) from exc
            if info.get("is_live"):
                raise LiveStreamNotSupportedError(
                    "las transmisiones en directo en curso no están soportadas; "
                    "espera a que el video esté disponible"
                )
            try:
                ydl.download([url])
            except yt_dlp.utils.DownloadError as exc:
                raise _classify_download_error(str(exc)) from exc

        path = self._locate_download(destination)
        return DownloadedMedia(
            path=path,
            title=info.get("title"),
            channel=info.get("channel") or info.get("uploader"),
            uploader_id=info.get("uploader_id") or info.get("channel_id"),
            duration=info.get("duration"),
        )

    def _locate_download(self, destination: Path) -> Path:
        candidates = sorted(
            path
            for path in destination.glob(f"{COPY_FILENAME}.*")
            if path.is_file() and path.suffix != ".part"
        )
        if not candidates:
            raise IngestError("la descarga terminó pero no generó ningún archivo de video")
        downloaded = candidates[0]
        if downloaded.suffix.lower() == ".mp4":
            return downloaded
        return self._remux_to_mp4(downloaded, destination / f"{COPY_FILENAME}.mp4")

    def _remux_to_mp4(self, source: Path, target: Path) -> Path:
        proc = subprocess.run(
            [
                str(self.settings.ffmpeg_bin),
                "-y",
                "-i",
                str(source),
                "-c",
                "copy",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise IngestError(
                f"no se pudo convertir la descarga a MP4: {_stderr_tail(proc.stderr)}"
            )
        source.unlink(missing_ok=True)
        return target


def _parse_fps(value: str | None) -> float | None:
    if not value:
        return None
    numerator, _, denominator = value.partition("/")
    try:
        fps = float(numerator) / float(denominator or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return round(fps, 3) if fps > 0 else None


def probe_media(video_path: Path, settings: Settings) -> ProbeResult:
    """Inspecciona un video con `FFPROBE_BIN` y devuelve sus metadatos técnicos."""
    video_path = Path(video_path)
    if not video_path.is_file():
        raise IngestError(f"no existe el archivo de video: {video_path}")
    proc = subprocess.run(
        [
            str(settings.ffprobe_bin),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise IngestError(f"ffprobe no pudo leer {video_path.name}: {_stderr_tail(proc.stderr)}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise IngestError(f"ffprobe devolvió un JSON inválido para {video_path.name}") from exc

    streams = payload.get("streams") or []
    video = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == "video"
            and not (stream.get("disposition") or {}).get("attached_pic")
        ),
        None,
    )
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    fmt = payload.get("format") or {}

    duration = fmt.get("duration") or (video or {}).get("duration") or 0.0
    try:
        duration = max(0.0, float(duration))
    except (TypeError, ValueError):
        duration = 0.0

    sample_rate = (audio or {}).get("sample_rate")
    try:
        sample_rate = int(sample_rate) if sample_rate is not None else None
    except (TypeError, ValueError):
        sample_rate = None

    return ProbeResult(
        duration=duration,
        width=(video or {}).get("width"),
        height=(video or {}).get("height"),
        fps=_parse_fps((video or {}).get("avg_frame_rate") or (video or {}).get("r_frame_rate")),
        video_codec=(video or {}).get("codec_name"),
        audio_codec=(audio or {}).get("codec_name"),
        audio_sample_rate=sample_rate,
        has_audio=audio is not None,
    )


def extract_audio(video_path: Path, audio_path: Path, settings: Settings) -> Path:
    """Genera un WAV PCM mono 16 kHz con `FFMPEG_BIN`."""
    audio_path = Path(audio_path)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            str(settings.ffmpeg_bin),
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(_AUDIO_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise IngestError(f"no se pudo extraer el audio: {_stderr_tail(proc.stderr)}")
    return audio_path


def _copy_file_with_progress(
    source: Path,
    destination: Path,
    on_progress: Callable[[float], None] | None,
) -> None:
    total = source.stat().st_size
    copied = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("wb") as dst:
        while chunk := src.read(1024 * 1024):
            dst.write(chunk)
            copied += len(chunk)
            if total and on_progress is not None:
                on_progress(min(100.0, copied / total * 100.0))
    if on_progress is not None:
        on_progress(100.0)


def _copy_local(
    source: str,
    source_dir: Path,
    on_progress: Callable[[float], None] | None,
) -> Path:
    path = Path(source).expanduser()
    if not path.exists():
        raise IngestError(f"no existe el archivo: {path}")
    if not path.is_file():
        raise IngestError(f"la ruta no es un archivo: {path}")
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise IngestError(f"extensión no soportada ({extension or 'sin extensión'}); usa {allowed}")
    destination = source_dir / f"{COPY_FILENAME}{extension}"
    _copy_file_with_progress(path, destination, on_progress)
    return destination


def ingest(
    source: str,
    *,
    settings: Settings,
    storage: LocalStorage | None = None,
    project_id: str | None = None,
    force: bool = False,
    downloader: MediaDownloader | None = None,
    progress: ProgressCallback | None = None,
) -> IngestResult:
    """Ingesta un video desde una URL o un archivo local en `STORAGE_DIR/projects/`."""
    storage = storage or LocalStorage(settings.storage_dir)
    project_id = validate_project_id(project_id) if project_id else new_project_id()
    project_dir = storage.project_dir(project_id)
    meta_path = storage.source_meta_path(project_id)

    if meta_path.exists() and not force:
        raise ProjectExistsError(
            f"el proyecto {project_id} ya está ingestado; usa --force para reemplazarlo"
        )
    if project_dir.exists() and force:
        shutil.rmtree(project_dir)
    storage.ensure_project_dirs(project_id)

    from_url = _is_url(source)
    first_stage = "download" if from_url else "copy"
    _emit(progress, 0.0, first_stage)

    source_type: Literal["url", "file"]
    if from_url:
        downloader = downloader or YtDlpDownloader(settings)
        media = downloader.download(
            source,
            storage.source_dir(project_id),
            on_progress=lambda value: _emit(
                progress, value * DOWNLOAD_PROGRESS_END / 100.0, "download"
            ),
        )
        video_path = media.path
        source_type = "url"
        source_url: str | None = source
        title = (media.title or source).strip()
        channel = media.channel
        uploader_id = media.uploader_id
    else:
        video_path = _copy_local(
            source,
            storage.source_dir(project_id),
            on_progress=lambda value: _emit(
                progress, value * DOWNLOAD_PROGRESS_END / 100.0, "copy"
            ),
        )
        source_type = "file"
        source_url = None
        title = Path(source).expanduser().stem or video_path.name
        channel = None
        uploader_id = None

    _emit(progress, DOWNLOAD_PROGRESS_END, first_stage)
    probe = probe_media(video_path, settings)
    _emit(progress, PROBE_PROGRESS_END, "probe")

    if not probe.has_audio:
        raise MissingAudioError(f"el video {video_path.name} no contiene audio para transcribir")

    audio_path = extract_audio(video_path, storage.audio_path(project_id), settings)
    _emit(progress, 100.0, "extract_audio")

    meta = SourceMeta(
        project_id=project_id,
        source_type=source_type,
        source_url=source_url,
        original_filename=video_path.name,
        title=title,
        channel=channel,
        uploader_id=uploader_id,
        duration=probe.duration,
        width=probe.width,
        height=probe.height,
        fps=probe.fps,
        video_codec=probe.video_codec,
        audio_codec=probe.audio_codec,
        audio_sample_rate=probe.audio_sample_rate,
        has_audio=probe.has_audio,
        file_size_bytes=video_path.stat().st_size,
    )
    storage.write_json_atomic(meta_path, meta)

    return IngestResult(
        project_id=project_id,
        meta=meta,
        video_path=video_path,
        audio_path=audio_path,
    )
