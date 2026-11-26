"""Tests del doctor: casos ok, warn y error con binarios falsos."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from winclip.core import doctor
from winclip.core.config import Settings


def _fake_bin(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {"storage_dir": tmp_path / "storage"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


@pytest.fixture
def ok_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Settings, dict[str, Path]]:
    """Entorno completamente falso pero funcional: todos los checks deben dar ok."""
    bins = {
        "ffmpeg": _fake_bin(
            tmp_path,
            "ffmpeg",
            'echo " .. ass               V->V       Render ASS subtitles"\n'
            'echo " .. subtitles         V->V       Render text subtitles"',
        ),
        "ffprobe": _fake_bin(tmp_path, "ffprobe", 'echo "ffprobe version 8.0"'),
        "yt-dlp": _fake_bin(tmp_path, "yt-dlp", 'echo "2026.08.19"'),
    }

    hf_home = tmp_path / "hf"
    snapshot = hf_home / "hub" / "models--org--model" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "weights.safetensors").write_text("x", encoding="utf-8")
    monkeypatch.setenv("HF_HOME", str(hf_home))

    playwright = tmp_path / "ms-playwright"
    (playwright / "chromium-1248").mkdir(parents=True)
    monkeypatch.setattr(doctor, "PLAYWRIGHT_CACHE", playwright)
    monkeypatch.setattr(doctor, "EXTERNAL_VOLUME", tmp_path)

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        assert url.endswith("/api/tags")
        return _FakeResponse({"models": [{"name": "llama3.2:3b"}]})

    monkeypatch.setattr(doctor.httpx, "get", fake_get)

    settings = _settings(
        tmp_path,
        ffmpeg_bin=bins["ffmpeg"],
        ffprobe_bin=bins["ffprobe"],
        ytdlp_bin=str(bins["yt-dlp"]),
        whisper_model="org/model",
    )
    return settings, bins


def test_all_checks_ok(ok_env: tuple[Settings, dict[str, Path]]) -> None:
    settings, _ = ok_env

    results = doctor.run_checks(settings)
    by_name = {result.name: result for result in results}

    assert doctor.has_errors(results) is False
    for name in (
        "ffmpeg",
        "ffprobe",
        "yt-dlp",
        "whisper",
        "ollama",
        "playwright",
        "almacenamiento",
    ):
        assert by_name[name].status == "ok", by_name[name]


def test_ffmpeg_without_libass_is_error(tmp_path: Path) -> None:
    ffmpeg = _fake_bin(tmp_path, "ffmpeg", 'echo " .. subtitles V->V Render text subtitles"')

    result = doctor.check_ffmpeg(_settings(tmp_path, ffmpeg_bin=ffmpeg))

    assert result.status == "error"
    assert "ass" in result.detail
    assert result.hint is not None and "ffmpeg-full" in result.hint


def test_ffmpeg_missing_binary_is_error(tmp_path: Path) -> None:
    result = doctor.check_ffmpeg(_settings(tmp_path, ffmpeg_bin=tmp_path / "no-existe"))

    assert result.status == "error"
    assert "no existe" in result.detail


def test_ffprobe_ok_and_missing(tmp_path: Path) -> None:
    ffprobe = _fake_bin(tmp_path, "ffprobe", 'echo "ffprobe version 8.0"')

    assert doctor.check_ffprobe(_settings(tmp_path, ffprobe_bin=ffprobe)).status == "ok"
    missing = doctor.check_ffprobe(_settings(tmp_path, ffprobe_bin=tmp_path / "no-existe"))
    assert missing.status == "error"


def test_ytdlp_ok_and_missing(tmp_path: Path) -> None:
    ytdlp = _fake_bin(tmp_path, "yt-dlp", 'echo "2026.08.19"')

    assert doctor.check_ytdlp(_settings(tmp_path, ytdlp_bin=str(ytdlp))).status == "ok"
    missing = doctor.check_ytdlp(_settings(tmp_path, ytdlp_bin=str(tmp_path / "no-existe")))
    assert missing.status == "error"


def test_whisper_cache_ok_error_and_warn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hf_home = tmp_path / "hf"
    monkeypatch.setenv("HF_HOME", str(hf_home))
    settings = _settings(tmp_path, whisper_model="org/model")

    assert doctor.check_whisper_model(settings).status == "error"

    empty_repo = hf_home / "hub" / "models--org--model"
    empty_repo.mkdir(parents=True)
    assert doctor.check_whisper_model(settings).status == "warn"

    snapshot = empty_repo / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "weights.safetensors").write_text("x", encoding="utf-8")
    assert doctor.check_whisper_model(settings).status == "ok"


def test_ollama_down_is_warn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_get(url: str, timeout: float) -> None:
        raise httpx.ConnectError("sin conexión")

    monkeypatch.setattr(doctor.httpx, "get", failing_get)

    result = doctor.check_ollama(_settings(tmp_path))

    assert result.status == "warn"
    assert result.hint is not None


def test_playwright_missing_is_warn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "PLAYWRIGHT_CACHE", tmp_path / "vacio")

    result = doctor.check_playwright_chromium(_settings(tmp_path))

    assert result.status == "warn"
    assert "playwright install chromium" in (result.hint or "")


def test_external_volume_missing_is_warn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "EXTERNAL_VOLUME", tmp_path / "no-montado")

    result = doctor.check_external_volume(_settings(tmp_path))

    assert result.status == "warn"


def test_storage_writable(tmp_path: Path) -> None:
    result = doctor.check_storage(_settings(tmp_path))

    assert result.status == "ok"
    assert (tmp_path / "storage").is_dir()


def test_storage_on_unmounted_volume_fails_without_creating_dirs(tmp_path: Path) -> None:
    missing_volume = Path("/Volumes/winclip-volumen-de-prueba-inexistente")
    settings = _settings(tmp_path, storage_dir=missing_volume / "storage")

    result = doctor.check_storage(settings)

    assert result.status == "error"
    assert "no está montado" in result.detail
    assert not missing_volume.exists()


def test_llm_keys_report_presence_without_leaking_values(
    ok_env: tuple[Settings, dict[str, Path]], monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "clave-ultra-secreta-1234567890"  # gitleaks:allow - valor ficticio de test
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    settings, _ = ok_env
    settings = settings.model_copy(update={"gemini_api_key": SecretStr(secret)})

    payload = doctor.health_payload(settings)
    serialized = json.dumps(payload)

    checks = {check["name"]: check for check in payload["checks"]}  # type: ignore[index]
    assert checks["GEMINI_API_KEY"]["detail"] == "presente"
    assert checks["NVIDIA_API_KEY"]["detail"] == "ausente"
    assert secret not in serialized


def test_unexpected_failure_becomes_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_settings: Settings) -> doctor.CheckResult:
        raise RuntimeError("no debería propagarse")

    monkeypatch.setattr(doctor, "check_ffmpeg", boom)

    results = doctor.run_checks(_settings(tmp_path))
    by_name = {result.name: result for result in results}

    assert by_name["ffmpeg"].status == "error"
    assert "RuntimeError" in by_name["ffmpeg"].detail
