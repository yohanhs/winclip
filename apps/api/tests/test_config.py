"""Tests de `winclip.core.config.Settings`."""

from __future__ import annotations

from pathlib import Path

from winclip.core.config import DEFAULT_FFMPEG_BIN, ROOT_DIR, Settings


def _settings(**overrides: object) -> Settings:
    """Settings sin `.env`, para probar solo defaults y entorno."""
    return Settings(_env_file=None, **overrides)


def test_defaults_load_without_env_file() -> None:
    settings = _settings()

    assert settings.app_name == "WinClip"
    assert settings.api_port == 8000
    assert settings.web_port == 3000
    assert settings.ffmpeg_bin == DEFAULT_FFMPEG_BIN
    assert settings.ffprobe_bin == Path("/opt/homebrew/opt/ffmpeg-full/bin/ffprobe")
    assert settings.whisper_model == "mlx-community/whisper-large-v3-turbo"
    assert settings.llm_providers == ["gemini", "nvidia", "openrouter", "groq", "ollama"]
    # STORAGE_DIR relativo se ancla a la raíz del repo
    assert settings.storage_dir == (ROOT_DIR / "storage").resolve()
    assert settings.database_url == f"sqlite:///{settings.storage_dir / 'winclip.db'}"
    # Sin claves: nada es obligatorio
    assert all(present is False for present in settings.api_key_presence.values())


def test_database_url_follows_storage_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "datos"))

    settings = _settings()

    assert settings.storage_dir == tmp_path / "datos"
    assert settings.database_url == f"sqlite:///{tmp_path / 'datos' / 'winclip.db'}"


def test_explicit_database_url_wins(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/otra.db")

    settings = _settings()

    assert settings.database_url == "sqlite:////tmp/otra.db"


def test_ffmpeg_bin_can_be_overridden(monkeypatch, tmp_path: Path) -> None:
    fake_ffmpeg = tmp_path / "ffmpeg-full"
    monkeypatch.setenv("FFMPEG_BIN", str(fake_ffmpeg))

    settings = _settings()

    assert settings.ffmpeg_bin == fake_ffmpeg
    assert settings.ffmpeg_bin != DEFAULT_FFMPEG_BIN


def test_api_keys_report_presence_but_never_the_value(monkeypatch) -> None:
    secret = "clave-de-prueba-que-no-debe-aparecer"
    monkeypatch.setenv("GEMINI_API_KEY", secret)

    settings = _settings()

    assert settings.api_key_presence["GEMINI_API_KEY"] is True
    assert settings.api_key_presence["NVIDIA_API_KEY"] is False
    assert secret not in repr(settings)
    assert secret not in settings.model_dump_json()
    assert secret not in str(settings.gemini_api_key)


def test_relative_storage_dir_is_anchored_to_repo_root(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_DIR", "datos-locales")

    settings = _settings()

    assert settings.storage_dir == ROOT_DIR / "datos-locales"
