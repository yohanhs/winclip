"""Tests del subcomando `winclip render`."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from winclip import cli
from winclip.core.config import Settings
from winclip.pipeline.render import RenderError
from winclip.pipeline.render_models import RenderManifest

runner = CliRunner()


def _manifest(clip_id: str = "01jclip", mode: str = "face") -> RenderManifest:
    return RenderManifest(
        clip_id=clip_id,
        candidate_id="01jcand",
        width=1080,
        height=1920,
        fps=30,
        reframe={"mode": mode, "track": [[0.0, 0.5]]},
        subtitles={"engine": "ass", "preset": "bold-yellow", "font": "Montserrat ExtraBold"},
        hook_overlay=True,
        duration=4.0,
        output="clip.mp4",
        thumbnail="thumb.jpg",
    )


def test_render_help_lists_all_flags() -> None:
    result = runner.invoke(cli.app, ["render", "--help"])

    assert result.exit_code == 0
    for flag in (
        "--clip",
        "--all",
        "--preset",
        "--reframe",
        "--engine",
        "--font",
        "--crop-x-pct",
        "--crop-y-pct",
        "--zoom-pct",
        "--hook-overlay",
        "--no-hook-overlay",
        "--hook-seconds",
        "--watermark",
        "--force",
    ):
        assert flag in result.stdout


def test_render_single_clip_uses_flags(monkeypatch, sample_settings: Settings) -> None:
    captured: dict[str, object] = {}

    def fake_render(project_id, **kwargs):
        captured["project_id"] = project_id
        captured.update(kwargs)
        return [_manifest()]

    monkeypatch.setattr(cli, "get_settings", lambda: sample_settings)
    monkeypatch.setattr(cli, "render_project_clips", fake_render)

    result = runner.invoke(
        cli.app,
        [
            "render",
            "proyecto",
            "--clip",
            "01jcand",
            "--preset",
            "hormozi",
            "--reframe",
            "center",
            "--engine",
            "pil",
            "--font",
            "GothamBlack",
            "--crop-x-pct",
            "30",
            "--crop-y-pct",
            "40",
            "--zoom-pct",
            "125",
            "--no-hook-overlay",
            "--hook-seconds",
            "5",
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert captured["project_id"] == "proyecto"
    assert captured["candidate_ids"] == ["01jcand"]
    assert captured["all_clips"] is False
    options = captured["options"]
    assert options.preset == "hormozi"
    assert options.reframe == "center"
    assert options.engine == "pil"
    assert options.font == "GothamBlack"
    assert options.crop_x_pct == 30
    assert options.crop_y_pct == 40
    assert options.zoom_pct == 125
    assert options.hook_overlay is False
    assert options.hook_seconds == 5
    assert options.force is True
    assert "Clips renderizados" in result.stdout
    assert "01jclip" in result.stdout


def test_render_all_passes_all_flag(monkeypatch, sample_settings: Settings) -> None:
    captured: dict[str, object] = {}

    def fake_render(project_id, **kwargs):
        captured.update(kwargs)
        return [_manifest("01ja"), _manifest("01jb")]

    monkeypatch.setattr(cli, "get_settings", lambda: sample_settings)
    monkeypatch.setattr(cli, "render_project_clips", fake_render)

    result = runner.invoke(cli.app, ["render", "proyecto", "--all"])

    assert result.exit_code == 0
    assert captured["all_clips"] is True
    assert captured["candidate_ids"] is None
    assert "01ja" in result.stdout


def test_render_requires_clip_or_all(monkeypatch, sample_settings: Settings) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: sample_settings)

    result = runner.invoke(cli.app, ["render", "proyecto"])

    assert result.exit_code == 1
    assert "indica" in result.stdout


def test_render_rejects_invalid_options(monkeypatch, sample_settings: Settings) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: sample_settings)

    result = runner.invoke(cli.app, ["render", "proyecto", "--all", "--crop-x-pct", "200"])

    assert result.exit_code == 1
    assert "error" in result.stdout


def test_render_reports_render_errors(monkeypatch, sample_settings: Settings) -> None:
    def failing(project_id, **kwargs):
        raise RenderError("ffmpeg falló")

    monkeypatch.setattr(cli, "get_settings", lambda: sample_settings)
    monkeypatch.setattr(cli, "render_project_clips", failing)

    result = runner.invoke(cli.app, ["render", "proyecto", "--all"])

    assert result.exit_code == 1
    assert "ffmpeg falló" in result.stdout


def test_render_rejects_missing_watermark(
    monkeypatch, sample_settings: Settings, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: sample_settings)

    result = runner.invoke(
        cli.app,
        ["render", "proyecto", "--all", "--watermark", str(tmp_path / "no.png")],
    )

    assert result.exit_code == 1
    assert "marca de agua" in result.stdout


def test_render_exit_code_propagates_unexpected_failure(
    monkeypatch, sample_settings: Settings
) -> None:
    def failing(project_id, **kwargs):
        raise pytest.fail("no debería ejecutarse")

    monkeypatch.setattr(cli, "get_settings", lambda: sample_settings)
    monkeypatch.setattr(cli, "render_project_clips", failing)

    with pytest.raises(pytest.fail.Exception):
        runner.invoke(cli.app, ["render", "proyecto", "--all"], catch_exceptions=False)
