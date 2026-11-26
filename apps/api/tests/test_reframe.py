"""Tests del reencuadre: muestreo, cortes, suavizado, bordes y filtros."""

from __future__ import annotations

import subprocess
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from winclip.core.config import Settings
from winclip.pipeline.reframe import (
    FaceDetection,
    SampleFrame,
    apply_deadband,
    bidirectional_ema,
    build_crop_expression,
    build_face_track,
    build_reframe_filter,
    clamp_speed,
    compute_reframe,
    crop_dimensions,
    crop_x_pixels,
    detect_shot_ranges,
    even,
    fill_short_gaps,
    frame_histogram,
    is_vertical,
    sample_video_frames,
    select_primary_face,
    simplify_rdp,
)
from winclip.pipeline.render_models import ReframeResult


def _face(cx: float, *, area: float = 0.05, confidence: float = 0.9) -> FaceDetection:
    side = area**0.5
    return FaceDetection(cx=cx, cy=0.4, width=side, height=side, confidence=confidence)


def _frame(color: tuple[int, int, int], size: int = 64) -> np.ndarray:
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    frame[:, :] = color
    return frame


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, storage_dir=tmp_path / "storage")


def test_even_rounds_to_even_and_minimum() -> None:
    assert even(607.4) == 606
    assert even(608.0) == 608
    assert even(1) == 2
    assert even(0) == 2


def test_crop_dimensions_keep_nine_by_sixteen() -> None:
    assert crop_dimensions(1920, 1080) == (608, 1080)
    assert crop_dimensions(1280, 720) == (404, 720)
    # Fuente más estrecha que 9:16: se usa el ancho completo y se recorta en alto.
    width, height = crop_dimensions(600, 1200)
    assert width == 600
    assert height == 1066


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (1080, 1920, True),
        (720, 1280, True),
        (1920, 1080, False),
        (1080, 1080, False),
        (900, 1920, False),
    ],
)
def test_is_vertical(width: int, height: int, expected: bool) -> None:
    assert is_vertical(width, height) is expected


def test_select_primary_face_prefers_larger_and_central() -> None:
    small = _face(0.5, area=0.02)
    large = _face(0.55, area=0.20)
    chosen = select_primary_face([small, large])
    assert chosen is not None and chosen.cx == large.cx


def test_select_primary_face_prefers_continuity() -> None:
    left = _face(0.2, area=0.10)
    right = _face(0.8, area=0.10)
    assert select_primary_face([left, right], previous_cx=0.21) is not None
    assert select_primary_face([left, right], previous_cx=0.21).cx == 0.2  # type: ignore[union-attr]


def test_select_primary_face_ignores_low_confidence() -> None:
    assert select_primary_face([_face(0.5, confidence=0.3)]) is None


def test_detect_shot_ranges_splits_on_color_change() -> None:
    red = frame_histogram(_frame((0, 0, 220)))
    blue = frame_histogram(_frame((220, 60, 0)))
    same = [red, frame_histogram(_frame((0, 0, 218)))]
    assert detect_shot_ranges(same) == [(0, 1)]

    cut = [red, red, blue, blue]
    assert detect_shot_ranges(cut) == [(0, 1), (2, 3)]
    assert detect_shot_ranges([]) == []


def test_fill_short_gaps_interpolates() -> None:
    filled = fill_short_gaps([0.2, None, None, 0.8], fps=3.0)
    assert filled[0] == 0.2
    assert filled[-1] == 0.8
    assert 0.2 < filled[1] < filled[2] < 0.8  # type: ignore[operator]


def test_fill_short_gaps_keeps_long_gaps() -> None:
    values = [0.2, None, None, None, None, 0.8]
    assert fill_short_gaps(values, fps=3.0)[2] is None


def test_deadband_absorbs_tremor() -> None:
    values = [0.5, 0.505, 0.495, 0.51, 0.49, 0.515]
    assert apply_deadband(values, deadband=0.02) == [0.5] * len(values)


def test_bidirectional_ema_has_no_lag() -> None:
    values = [0.0, 0.0, 1.0, 1.0, 1.0]
    smoothed = bidirectional_ema(values, alpha=0.5)
    assert smoothed[0] < 0.2
    assert smoothed[-1] > 0.85
    assert smoothed[1] < smoothed[2] < smoothed[3]


def test_clamp_speed_limits_pan() -> None:
    clamped = clamp_speed([0.1, 0.9, 0.1], fps=3.0, max_speed=0.22)
    limit = 0.22 / 3.0
    assert clamped[1] - clamped[0] <= limit + 1e-9
    assert clamped[0] - clamped[2] <= limit + 1e-9


def test_simplify_rdp_keeps_extremes_and_corners() -> None:
    points = [(0.0, 0.2), (0.5, 0.2), (1.0, 0.8), (1.5, 0.8)]
    simplified = simplify_rdp(points, epsilon=0.005)
    assert simplified[0] == (0.0, 0.2)
    assert simplified[-1] == (1.5, 0.8)
    assert (1.0, 0.8) in simplified


def _samples(positions: list[float | None], *, cut_at: int | None = None) -> list[SampleFrame]:
    red = frame_histogram(_frame((0, 0, 220)))
    blue = frame_histogram(_frame((220, 60, 0)))
    samples = []
    for index, position in enumerate(positions):
        faces = () if position is None else (_face(position),)
        histogram = blue if cut_at is not None and index >= cut_at else red
        samples.append(SampleFrame(time=index / 3.0, faces=faces, histogram=histogram))
    return samples


def test_build_face_track_smooths_a_steady_face() -> None:
    samples = _samples([0.40, 0.405, 0.395, 0.40, 0.402, 0.398])
    track, detected = build_face_track(samples, fps=3.0)
    assert detected == 6
    assert track
    values = [value for _, value in track]
    assert max(values) - min(values) < 0.01


def test_build_face_track_jumps_at_shot_cut() -> None:
    samples = _samples([0.20] * 6 + [0.80] * 6, cut_at=6)
    track, _ = build_face_track(samples, fps=3.0)
    thresholds = [value for _, value in track]
    assert thresholds[-1] > 0.7
    assert thresholds[0] < 0.3
    jumps = [abs(second[1] - first[1]) for first, second in pairwise(track)]
    assert max(jumps) > 0.3


def test_build_face_track_without_faces_centers() -> None:
    samples = _samples([None] * 5)
    track, detected = build_face_track(samples, fps=3.0)
    assert detected == 0
    assert all(value == 0.5 for _, value in track)


def test_face_near_border_is_clamped_inside_frame() -> None:
    result = ReframeResult(
        mode="face",
        track=[(0.0, 0.02)],
        source_width=1920,
        source_height=1080,
        crop_width=606,
        crop_height=1080,
    )
    assert crop_x_pixels(result, 0.02) == 0.0
    assert crop_x_pixels(result, 0.98) == 1920 - 606


def test_crop_expression_interpolates_and_jumps() -> None:
    result = ReframeResult(
        mode="face",
        track=[(0.0, 0.2), (1.0, 0.2), (1.0, 0.8), (2.0, 0.8)],
        source_width=1920,
        source_height=1080,
        crop_width=606,
        crop_height=1080,
    )
    expression = build_crop_expression(result)
    assert expression.startswith("if(lt(t,1.000)")
    assert "(t-0.000)" in expression


def test_build_reframe_filter_modes() -> None:
    face = ReframeResult(
        mode="face",
        track=[(0.0, 0.5)],
        source_width=1920,
        source_height=1080,
        crop_width=606,
        crop_height=1080,
    )
    assert "crop=w=606:h=1080" in build_reframe_filter(face)
    assert "scale=1080:1920" in build_reframe_filter(face)

    blur = face.model_copy(update={"mode": "blur", "track": []})
    assert "gblur" in build_reframe_filter(blur)

    passthrough = face.model_copy(update={"mode": "passthrough", "track": []})
    assert "pad=1080:1920" in build_reframe_filter(passthrough)

    center = face.model_copy(update={"mode": "center"})
    assert "crop=w=606" in build_reframe_filter(center, crop_x_pct=30, crop_y_pct=40)


def _make_video(
    path: Path, settings: Settings, *, width: int, height: int, seconds: int = 2
) -> Path:
    result = subprocess.run(
        [
            str(settings.ffmpeg_bin),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={width}x{height}:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"ffmpeg no pudo generar el video sintético: {result.stderr[-200:]}")
    return path


def test_sample_video_frames_reads_bgr_frames(ffmpeg_settings: Settings, tmp_path: Path) -> None:
    video = _make_video(tmp_path / "horizontal.mp4", ffmpeg_settings, width=320, height=180)

    frames = list(
        sample_video_frames(video, 0.0, 1.0, fps=3.0, settings=ffmpeg_settings, width=160)
    )

    assert 2 <= len(frames) <= 4
    moment, frame = frames[0]
    assert moment == 0.0
    assert frame.shape[1] == 160
    assert frame.shape[2] == 3


def test_compute_reframe_passthrough_for_vertical_source(
    ffmpeg_settings: Settings, tmp_path: Path
) -> None:
    video = _make_video(tmp_path / "vertical.mp4", ffmpeg_settings, width=180, height=320)

    result = compute_reframe(video, 0.0, 1.0, settings=ffmpeg_settings)

    assert result.mode == "passthrough"
    assert result.track == []
    assert (result.crop_width, result.crop_height) == (180, 320)


def test_compute_reframe_center_uses_zoom(ffmpeg_settings: Settings, tmp_path: Path) -> None:
    video = _make_video(tmp_path / "horizontal.mp4", ffmpeg_settings, width=320, height=180)

    result = compute_reframe(
        video,
        0.0,
        1.0,
        mode="center",
        settings=ffmpeg_settings,
        crop_x_pct=30,
        zoom_pct=125,
    )

    assert result.mode == "center"
    assert result.crop_width < crop_dimensions(320, 180)[0]
    assert result.track == [(0.0, 0.3)]
