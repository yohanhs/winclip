"""Tests de los modelos de `render.json`, opciones y progreso."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from winclip.pipeline.render_models import (
    ReframeResult,
    ReframeSpec,
    RenderManifest,
    RenderOptions,
    RenderProgress,
)


def _manifest(**overrides) -> dict:
    payload = {
        "clip_id": "01jclip",
        "candidate_id": "01jcand",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "reframe": {"mode": "face", "track": [[0.0, 0.42], [1.0, 0.45]]},
        "subtitles": {"engine": "ass", "preset": "bold-yellow", "font": "Montserrat ExtraBold"},
        "hook_overlay": True,
        "duration": 48.6,
        "output": "clip.mp4",
        "thumbnail": "thumb.jpg",
    }
    payload.update(overrides)
    return payload


def test_manifest_matches_contract_exactly() -> None:
    manifest = RenderManifest.model_validate(_manifest())

    assert manifest.width == 1080
    assert manifest.reframe.mode == "face"
    assert manifest.subtitles.engine == "ass"
    # El contrato §6.3 tiene exactamente 11 campos.
    assert set(manifest.model_dump()) == {
        "clip_id",
        "candidate_id",
        "width",
        "height",
        "fps",
        "reframe",
        "subtitles",
        "hook_overlay",
        "duration",
        "output",
        "thumbnail",
    }


def test_manifest_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RenderManifest.model_validate(_manifest(fingerprint="abc"))


@pytest.mark.parametrize("mode", ["face", "center", "blur", "passthrough"])
def test_manifest_accepts_all_reframe_modes(mode: str) -> None:
    manifest = RenderManifest.model_validate(
        _manifest(reframe={"mode": mode, "track": [] if mode != "center" else [[0.0, 0.5]]})
    )
    assert manifest.reframe.mode == mode


def test_reframe_spec_validates_track() -> None:
    with pytest.raises(ValidationError):
        ReframeSpec(mode="face", track=[(1.0, 0.5), (0.5, 0.6)])
    with pytest.raises(ValidationError):
        ReframeSpec(mode="face", track=[(0.0, 1.4)])
    # Un corte de plano puede repetir el instante (salto instantáneo).
    spec = ReframeSpec(mode="face", track=[(1.0, 0.2), (1.0, 0.8)])
    assert spec.track == [(1.0, 0.2), (1.0, 0.8)]


def test_reframe_result_manifest_spec() -> None:
    result = ReframeResult(
        mode="face",
        track=[(0.0, 0.4), (1.0, 0.6)],
        source_width=1920,
        source_height=1080,
        crop_width=608,
        crop_height=1080,
        faces_detected=12,
        shots=2,
    )
    assert result.manifest_spec() == ReframeSpec(mode="face", track=[(0.0, 0.4), (1.0, 0.6)])


def test_render_options_defaults() -> None:
    options = RenderOptions()

    assert options.preset == "bold-yellow"
    assert options.reframe == "face"
    assert options.engine == "ass"
    assert options.crop_x_pct == 50.0
    assert options.crop_y_pct == 50.0
    assert options.zoom_pct == 100.0
    assert options.hook_overlay is True
    assert options.hook_seconds == 3.0
    assert options.force is False
    assert options.sample_fps == 3.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("crop_x_pct", 120.0),
        ("crop_x_pct", -1.0),
        ("crop_y_pct", 101.0),
        ("zoom_pct", 90.0),
        ("zoom_pct", 320.0),
        ("hook_seconds", 0.1),
        ("sample_fps", 8.0),
        ("reframe", "passthrough"),
        ("engine", "srt"),
    ],
)
def test_render_options_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        RenderOptions(**{field: value})


def test_render_options_reject_missing_watermark(tmp_path) -> None:
    with pytest.raises(ValidationError, match="marca de agua"):
        RenderOptions(watermark_path=tmp_path / "no-existe.png")

    watermark = tmp_path / "marca.png"
    watermark.write_bytes(b"png")
    assert RenderOptions(watermark_path=watermark).watermark_path == watermark


def test_render_progress_is_frozen() -> None:
    progress = RenderProgress(
        clip_id="a", candidate_id="b", stage="encode", percent=42.5, message="hola"
    )
    assert progress.percent == 42.5
    with pytest.raises(AttributeError):
        progress.percent = 10  # type: ignore[misc]
