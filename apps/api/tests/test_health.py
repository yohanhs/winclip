"""Tests de `GET /api/health`."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from winclip.core import doctor
from winclip.core.config import Settings
from winclip.main import create_app


def _settings(tmp_path: Path) -> Settings:
    """Settings temporales: el lifespan migra esta base, no la del usuario."""
    storage = tmp_path / "storage"
    return Settings(
        _env_file=None,
        storage_dir=storage,
        database_url=f"sqlite:///{storage / 'winclip.db'}",
    )


def test_health_returns_checks(monkeypatch, tmp_path: Path) -> None:
    fake_results = [
        doctor.CheckResult(name="ffmpeg", status="ok", detail="ffmpeg-full con libass"),
        doctor.CheckResult(name="GEMINI_API_KEY", status="warn", detail="ausente", hint="define…"),
    ]
    monkeypatch.setattr(doctor, "run_checks", lambda settings=None: fake_results)

    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"app", "version", "checks"}
    assert body["app"] == "WinClip"
    assert [check["name"] for check in body["checks"]] == ["ffmpeg", "GEMINI_API_KEY"]
    assert body["checks"][0]["status"] == "ok"


def test_health_allows_web_origin(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(doctor, "run_checks", lambda settings=None: [])

    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
