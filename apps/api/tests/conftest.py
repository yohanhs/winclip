"""Fixtures compartidas de los tests de la API."""

from __future__ import annotations

import pytest

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
