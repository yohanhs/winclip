"""Fixtures compartidas de los tests de la API."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from winclip.core.config import (
    DEFAULT_FFMPEG_BIN,
    DEFAULT_FFPROBE_BIN,
    Settings,
    get_settings,
)

# Variables que podrían venir del entorno de la máquina y falsear los tests.
_WINCLIP_ENV_VARS = (
    "APP_NAME",
    "API_PORT",
    "WEB_PORT",
    "STORAGE_DIR",
    "DATABASE_URL",
    "FFMPEG_BIN",
    "FFPROBE_BIN",
    "YTDLP_BIN",
    "WHISPER_MODEL",
    "GEMINI_API_KEY",
    "NVIDIA_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "LLM_PROVIDER_ORDER",
    "OLLAMA_HOST",
    "GEMINI_MODEL",
    "NVIDIA_MODEL",
    "OPENROUTER_MODEL",
    "GROQ_MODEL",
    "OLLAMA_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES_PER_PROVIDER",
    "LLM_SCORE_THRESHOLD",
    "LLM_SINGLE_PASS_MAX_CHARS",
    "GOOGLE_CLIENT_SECRET_FILE",
    "TIKTOK_CLIENT_KEY",
    "TIKTOK_CLIENT_SECRET",
    "META_APP_ID",
    "META_APP_SECRET",
    "WINCLIP_SECRET_KEY",
    "USER_FONTS_DIR",
)


@pytest.fixture(autouse=True)
def clean_winclip_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla los tests de la configuración real de la máquina."""
    for name in _WINCLIP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def sample_settings(tmp_path: Path) -> Settings:
    """Settings con `STORAGE_DIR` temporal y el modelo ligero por defecto."""
    return Settings(
        storage_dir=tmp_path / "storage",
        whisper_model="mlx-community/whisper-tiny",
    )


@pytest.fixture
def ffmpeg_settings(sample_settings: Settings) -> Settings:
    """Settings que exigen que `FFMPEG_BIN` y `FFPROBE_BIN` existan (si no, se salta)."""
    missing = [
        str(binary)
        for binary in (sample_settings.ffmpeg_bin, sample_settings.ffprobe_bin)
        if not binary.exists()
    ]
    if missing:
        pytest.skip(f"ffmpeg-full no disponible: {', '.join(missing)}")
    return sample_settings


def _make_video(settings: Settings, path: Path, *, with_audio: bool) -> Path:
    command = [
        str(settings.ffmpeg_bin),
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=30:duration=2",
    ]
    if with_audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    command += ["-c:a", "aac", "-shortest"] if with_audio else ["-an"]
    command.append(str(path))
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        pytest.skip(f"no se pudo generar el video sintético: {proc.stderr[-300:]}")
    return path


@pytest.fixture
def synthetic_video(tmp_path: Path, ffmpeg_settings: Settings) -> Path:
    """Video corto con pista de audio generado con `FFMPEG_BIN`."""
    return _make_video(ffmpeg_settings, tmp_path / "sample.mp4", with_audio=True)


@pytest.fixture
def silent_video(tmp_path: Path, ffmpeg_settings: Settings) -> Path:
    """Video corto sin pista de audio."""
    return _make_video(ffmpeg_settings, tmp_path / "silent.mp4", with_audio=False)


@pytest.fixture
def cli_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """`STORAGE_DIR` temporal para invocar la CLI real y `get_settings` sin caché.

    No exige que ffmpeg exista: los tests que generan media piden su propia fixture.
    """
    storage_dir = tmp_path / "cli-storage"
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("FFMPEG_BIN", str(DEFAULT_FFMPEG_BIN))
    monkeypatch.setenv("FFPROBE_BIN", str(DEFAULT_FFPROBE_BIN))
    monkeypatch.setenv("WHISPER_MODEL", "mlx-community/whisper-tiny")
    get_settings.cache_clear()
    yield storage_dir
    get_settings.cache_clear()
