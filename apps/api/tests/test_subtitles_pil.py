"""Tests del motor `pil`: frames RGBA, color activo y zona segura."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from winclip.core.config import Settings
from winclip.pipeline.subtitles.fonts import resolve_font
from winclip.pipeline.subtitles.layout import SubtitleCue, TimedWord, build_cues
from winclip.pipeline.subtitles.pil_engine import SubtitleFrameRenderer
from winclip.pipeline.subtitles.presets import load_preset

WIDTH = 1080
HEIGHT = 1920


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, storage_dir=tmp_path / "storage", user_fonts_dir=tmp_path)


def _cues() -> list[SubtitleCue]:
    words = [
        TimedWord("Hola", 0.0, 0.4),
        TimedWord("a", 0.4, 0.6),
        TimedWord("todos", 0.6, 1.0),
        TimedWord("esto", 1.2, 1.5),
        TimedWord("es", 1.5, 1.7),
        TimedWord("WinClip.", 1.7, 2.2),
    ]
    return build_cues(words, load_preset("bold-yellow"))


def _renderer(tmp_path: Path, preset_name: str = "bold-yellow") -> SubtitleFrameRenderer:
    preset = load_preset(preset_name)
    font = resolve_font(preset.font, fallback=preset.fallback_font, settings=_settings(tmp_path))
    return SubtitleFrameRenderer(_cues(), preset, font.font.path, width=WIDTH, height=HEIGHT)


def _active_region(alpha: np.ndarray) -> tuple[int, int]:
    rows = np.where(alpha.max(axis=1) > 0)[0]
    return int(rows.min()), int(rows.max())


def test_frame_has_expected_shape_and_transparency(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)

    frame = renderer.frame_at(0.1)

    assert frame.shape == (HEIGHT, WIDTH, 4)
    assert frame.dtype == np.uint8
    assert frame[..., 3].max() > 0


def test_frame_before_first_word_is_transparent(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)

    frame = renderer.frame_at(5.0)

    assert frame[..., 3].max() == 0


def test_text_stays_in_safe_zone(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)
    preset = renderer.preset

    frame = renderer.frame_at(0.2)
    top, bottom = _active_region(frame[..., 3])

    assert top / HEIGHT >= 0.55
    assert bottom / HEIGHT <= 0.72
    assert abs(bottom / HEIGHT - (preset.y_pct + 0.04)) < 0.02


def test_active_word_is_highlighted_in_yellow(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)

    frame = renderer.frame_at(0.1)
    rgb = frame[..., :3].astype(np.int16)
    yellow = (rgb[..., 0] > 200) & (rgb[..., 1] > 160) & (rgb[..., 2] < 90) & (frame[..., 3] > 200)

    assert yellow.sum() > 200


def test_highlight_moves_with_the_active_word(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)

    first = renderer.frame_at(0.1)
    third = renderer.frame_at(0.7)

    def yellow_pixels(frame: np.ndarray) -> int:
        rgb = frame[..., :3].astype(np.int16)
        return int(
            (
                (rgb[..., 0] > 200)
                & (rgb[..., 1] > 160)
                & (rgb[..., 2] < 90)
                & (frame[..., 3] > 200)
            ).sum()
        )

    assert yellow_pixels(first) > 0
    assert yellow_pixels(third) > 0
    assert not np.array_equal(first[..., 3], third[..., 3])


def test_iter_frames_matches_fps_and_reuses_buffer(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)

    frames = list(renderer.iter_frames(1.0, 10.0))

    assert len(frames) == 10
    assert len(frames[0]) == HEIGHT
    # Dentro del mismo estado de palabra se reutiliza el mismo buffer.
    assert frames[0] is frames[1]


def test_boxed_preset_draws_background(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path, "clean-white")

    frame = renderer.frame_at(0.2)

    assert frame[..., 3].max() > 0
    mid_row = frame[(int(HEIGHT * 0.68)), :, 3]
    assert (mid_row > 0).sum() > WIDTH // 3


def test_missing_coverage_renders_empty(tmp_path: Path) -> None:
    preset = load_preset("bold-yellow")
    font = resolve_font(preset.font, fallback=preset.fallback_font, settings=_settings(tmp_path))
    renderer = SubtitleFrameRenderer([], preset, font.font.path)

    assert renderer.frame_at(0.0).shape == (HEIGHT, WIDTH, 4)
    with pytest.raises(KeyError):
        renderer.render_state(0, 0)
