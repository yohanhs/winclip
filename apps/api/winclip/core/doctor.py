"""Diagnóstico de dependencias de WinClip.

Cada check es una función pura que recibe los `Settings` y devuelve un `CheckResult`.
La CLI (`winclip doctor`) y la API (`GET /api/health`) comparten el mismo registro.
Ningún check imprime ni devuelve el valor de una clave: solo "presente"/"ausente".
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import httpx

from winclip import __version__
from winclip.core.config import Settings, get_settings

Status = Literal["ok", "warn", "error"]

CHECK_TIMEOUT_SECONDS = 3.0
EXTERNAL_VOLUME = Path("/Volumes/yohan")
PLAYWRIGHT_CACHE = Path.home() / "Library" / "Caches" / "ms-playwright"


@dataclass(frozen=True)
class CheckResult:
    """Resultado de un check del doctor."""

    name: str
    status: Status
    detail: str
    hint: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _run(binary: Path | str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        timeout=CHECK_TIMEOUT_SECONDS,
        check=False,
    )


def check_ffmpeg(settings: Settings) -> CheckResult:
    """ffmpeg-full debe tener los filtros de libass: `ass` y `subtitles`."""
    binary = settings.ffmpeg_bin
    if not binary.exists():
        return CheckResult(
            name="ffmpeg",
            status="error",
            detail=f"no existe {binary}",
            hint="instala ffmpeg-full con libass: brew install ffmpeg-full",
        )
    try:
        proc = _run(binary, "-hide_banner", "-filters")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult(
            name="ffmpeg",
            status="error",
            detail=f"no se pudo ejecutar {binary} ({type(exc).__name__})",
            hint="revisa FFMPEG_BIN o reinstala ffmpeg-full",
        )
    if proc.returncode != 0:
        return CheckResult(
            name="ffmpeg",
            status="error",
            detail=f"ffmpeg terminó con código {proc.returncode}",
            hint="revisa FFMPEG_BIN o reinstala ffmpeg-full",
        )

    output = f"{proc.stdout}\n{proc.stderr}"
    missing = [name for name in ("ass", "subtitles") if not re.search(rf"\b{name}\b", output)]
    if missing:
        return CheckResult(
            name="ffmpeg",
            status="error",
            detail=f"ffmpeg sin libass: faltan los filtros {', '.join(missing)}",
            hint="instala ffmpeg-full (keg-only) y apunta FFMPEG_BIN a su binario",
        )
    return CheckResult(
        name="ffmpeg",
        status="ok",
        detail=f"ffmpeg-full con libass (ass, subtitles) en {binary}",
    )


def check_ffprobe(settings: Settings) -> CheckResult:
    binary = settings.ffprobe_bin
    if not binary.exists():
        return CheckResult(
            name="ffprobe",
            status="error",
            detail=f"no existe {binary}",
            hint="instala ffmpeg-full: brew install ffmpeg-full",
        )
    try:
        proc = _run(binary, "-version")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult(
            name="ffprobe",
            status="error",
            detail=f"no se pudo ejecutar {binary} ({type(exc).__name__})",
            hint="revisa FFPROBE_BIN o reinstala ffmpeg-full",
        )
    if proc.returncode != 0:
        return CheckResult(
            name="ffprobe",
            status="error",
            detail=f"ffprobe terminó con código {proc.returncode}",
            hint="revisa FFPROBE_BIN o reinstala ffmpeg-full",
        )
    version = (proc.stdout or proc.stderr).splitlines()[0] if proc.stdout else "disponible"
    return CheckResult(name="ffprobe", status="ok", detail=version)


def check_ytdlp(settings: Settings) -> CheckResult:
    binary = settings.ytdlp_bin
    resolved = shutil.which(binary) if not Path(binary).exists() else binary
    if not resolved:
        return CheckResult(
            name="yt-dlp",
            status="error",
            detail=f"no se encontró {binary}",
            hint="instala yt-dlp: brew install yt-dlp",
        )
    try:
        proc = _run(resolved, "--version")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult(
            name="yt-dlp",
            status="error",
            detail=f"no se pudo ejecutar {binary} ({type(exc).__name__})",
            hint="revisa YTDLP_BIN o reinstala yt-dlp",
        )
    if proc.returncode != 0:
        return CheckResult(
            name="yt-dlp",
            status="error",
            detail=f"yt-dlp terminó con código {proc.returncode}",
            hint="reinstala yt-dlp: brew install yt-dlp",
        )
    return CheckResult(
        name="yt-dlp",
        status="ok",
        detail=f"yt-dlp {proc.stdout.strip()} ({resolved})",
    )


def _hf_hub_cache() -> Path:
    explicit = os.environ.get("HUGGINGFACE_HUB_CACHE")
    if explicit:
        return Path(explicit).expanduser()
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def check_whisper_model(settings: Settings) -> CheckResult:
    """Comprueba la caché de Hugging Face sin importar mlx (se instala en el change 1)."""
    repo_dir = _hf_hub_cache() / f"models--{settings.whisper_model.replace('/', '--')}"
    if not repo_dir.is_dir():
        return CheckResult(
            name="whisper",
            status="error",
            detail=f"el modelo {settings.whisper_model} no está en la caché de Hugging Face",
            hint=(
                "descarga el modelo: uv run --project apps/api python -c "
                '"from huggingface_hub import snapshot_download; '
                f"snapshot_download('{settings.whisper_model}')\""
            ),
        )
    snapshots = repo_dir / "snapshots"
    if snapshots.is_dir() and any(snapshots.iterdir()):
        return CheckResult(
            name="whisper",
            status="ok",
            detail=f"{settings.whisper_model} en caché ({repo_dir})",
        )
    return CheckResult(
        name="whisper",
        status="warn",
        detail=f"{repo_dir} existe pero no tiene snapshots descargados",
        hint="vuelve a descargar el modelo con huggingface_hub",
    )


def check_ollama(settings: Settings) -> CheckResult:
    url = f"{settings.ollama_host.rstrip('/')}/api/tags"
    try:
        response = httpx.get(url, timeout=CHECK_TIMEOUT_SECONDS)
        response.raise_for_status()
        models = response.json().get("models", [])
    except (httpx.HTTPError, ValueError) as exc:
        return CheckResult(
            name="ollama",
            status="warn",
            detail=f"Ollama no responde en {settings.ollama_host} ({type(exc).__name__})",
            hint="arráncalo con: ollama serve (solo se usa como respaldo offline)",
        )
    names = ", ".join(model.get("name", "?") for model in models) or "sin modelos"
    return CheckResult(
        name="ollama",
        status="ok",
        detail=f"Ollama accesible con {len(models)} modelo(s): {names}",
    )


def check_playwright_chromium(_settings: Settings) -> CheckResult:
    browsers = sorted(PLAYWRIGHT_CACHE.glob("chromium-*")) if PLAYWRIGHT_CACHE.is_dir() else []
    if browsers:
        return CheckResult(
            name="playwright",
            status="ok",
            detail=f"Chromium disponible en {browsers[-1]}",
        )
    return CheckResult(
        name="playwright",
        status="warn",
        detail="Chromium de Playwright no encontrado",
        hint="instálalo cuando lo necesites: uv run --project apps/api playwright install chromium",
    )


def check_external_volume(_settings: Settings) -> CheckResult:
    if EXTERNAL_VOLUME.is_dir():
        return CheckResult(
            name="volumen externo",
            status="ok",
            detail=f"{EXTERNAL_VOLUME} montado",
        )
    return CheckResult(
        name="volumen externo",
        status="warn",
        detail=f"{EXTERNAL_VOLUME} no está montado",
        hint="conecta el disco externo o cambia STORAGE_DIR en .env",
    )


def _volume_root(path: Path) -> Path | None:
    """Devuelve `/Volumes/<volumen>` si la ruta vive en un volumen de macOS."""
    parts = path.parts
    if len(parts) >= 3 and parts[1] == "Volumes":
        return Path("/Volumes") / parts[2]
    return None


def check_storage(settings: Settings) -> CheckResult:
    target = settings.storage_dir
    volume = _volume_root(target)
    if volume is not None and not volume.is_dir():
        # No se crean carpetas falsas bajo /Volumes cuando el disco no está montado.
        return CheckResult(
            name="almacenamiento",
            status="error",
            detail=f"el volumen {volume} no está montado y STORAGE_DIR apunta a {target}",
            hint="conecta el disco externo o ajusta STORAGE_DIR en .env",
        )
    try:
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target, prefix=".winclip-write-", delete=True):
            pass
    except OSError as exc:
        return CheckResult(
            name="almacenamiento",
            status="error",
            detail=f"no se puede escribir en {target} ({exc.strerror or type(exc).__name__})",
            hint="revisa permisos o cambia STORAGE_DIR en .env",
        )
    return CheckResult(
        name="almacenamiento",
        status="ok",
        detail=f"{target} escribible (base de datos: {settings.database_url})",
    )


def _llm_key_check(name: str, present: bool) -> CheckResult:
    return CheckResult(
        name=name,
        status="ok" if present else "warn",
        detail="presente" if present else "ausente",
        hint=None if present else f"define {name} en .env si quieres usar ese proveedor",
    )


def check_llm_keys(settings: Settings) -> list[CheckResult]:
    presence = settings.api_key_presence
    return [
        _llm_key_check(name, presence[name])
        for name in ("GEMINI_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY")
    ]


def run_checks(settings: Settings | None = None) -> list[CheckResult]:
    """Ejecuta todos los checks en orden. Un fallo inesperado se convierte en `error`."""
    settings = settings or get_settings()
    results: list[CheckResult] = []
    checks: Sequence[tuple[str, Callable[[Settings], CheckResult]]] = (
        ("ffmpeg", check_ffmpeg),
        ("ffprobe", check_ffprobe),
        ("yt-dlp", check_ytdlp),
        ("whisper", check_whisper_model),
        ("ollama", check_ollama),
        ("playwright", check_playwright_chromium),
        ("volumen externo", check_external_volume),
        ("almacenamiento", check_storage),
    )
    for name, check in checks:
        try:
            results.append(check(settings))
        except Exception as exc:  # el doctor nunca debe romper por un check
            results.append(
                CheckResult(
                    name=name,
                    status="error",
                    detail=f"fallo inesperado ({type(exc).__name__})",
                    hint="revisa la configuración y vuelve a ejecutar el doctor",
                )
            )
    results.extend(check_llm_keys(settings))
    return results


def has_errors(results: Sequence[CheckResult]) -> bool:
    return any(result.status == "error" for result in results)


def health_payload(settings: Settings | None = None) -> dict[str, object]:
    """Payload de `GET /api/health` (mismo contrato que usa la web)."""
    settings = settings or get_settings()
    return {
        "app": settings.app_name,
        "version": __version__,
        "checks": [result.to_dict() for result in run_checks(settings)],
    }
