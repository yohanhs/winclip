"""Tests del motor `ass`: determinismo, golden files y zona segura."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from winclip.core.config import Settings
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.subtitles.ass_engine import (
    ass_color,
    ass_timestamp,
    build_ass,
    margin_v,
    write_ass,
)
from winclip.pipeline.subtitles.fonts import measure_font, resolve_font
from winclip.pipeline.subtitles.layout import build_cues, retime_words
from winclip.pipeline.subtitles.presets import load_preset

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"
CLIP_START = 812.4
CLIP_END = 828.0

SAMPLE_WORDS = [
    ("Hola", 812.9, 813.3),
    ("a", 813.3, 813.5),
    ("todos,", 813.5, 814.1),
    ("esto", 814.1, 814.6),
    ("es", 814.6, 814.8),
    ("WinClip.", 814.8, 815.6),
    ("Vamos", 816.0, 816.4),
    ("a", 816.4, 816.5),
    ("por", 816.5, 816.8),
    ("ello.", 816.8, 817.6),
]


def sample_transcript() -> Transcript:
    return Transcript(
        language="es",
        duration=900.0,
        model="test",
        segments=[
            TranscriptSegment(
                id=0,
                start=CLIP_START,
                end=CLIP_END,
                text=" ".join(word for word, _, _ in SAMPLE_WORDS),
                words=[
                    WordTimestamp(w=word, s=start, e=end, p=0.95)
                    for word, start, end in SAMPLE_WORDS
                ],
            )
        ],
    )


def _resolved_font(preset):
    settings = Settings(_env_file=None, user_fonts_dir=Path("/no-existe"))
    return resolve_font(preset.font, fallback=preset.fallback_font, settings=settings)


def sample_ass(preset_name: str) -> str:
    preset = load_preset(preset_name)
    font = _resolved_font(preset)
    words = retime_words(
        sample_transcript(),
        CLIP_START,
        CLIP_END,
        uppercase=preset.uppercase,
    )
    measure = measure_font(font.font.path, preset.font_size)
    cues = build_cues(words, preset, measure=measure)
    return build_ass(
        cues,
        preset,
        font_name=font.ass_name,
        measure=measure_font(font.font.path, preset.font_size),
    )


def test_ass_timestamp_format() -> None:
    assert ass_timestamp(0) == "0:00:00.00"
    assert ass_timestamp(61.234) == "0:01:01.23"
    assert ass_timestamp(3661.5) == "1:01:01.50"
    assert ass_timestamp(-3) == "0:00:00.00"


def test_ass_color_converts_to_bgr() -> None:
    assert ass_color("#FFFFFF") == "&H00FFFFFF"
    assert ass_color("#FFD600") == "&H0000D6FF"
    assert ass_color("#00000088") == "&H88000000"


@pytest.mark.parametrize("preset_name", ["bold-yellow", "hormozi"])
def test_ass_matches_golden_file(preset_name: str) -> None:
    golden_path = GOLDEN_DIR / f"subs-{preset_name}.ass"
    content = sample_ass(preset_name)

    if os.environ.get("WINCLIP_UPDATE_GOLDEN") == "1":
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(content, encoding="utf-8")

    assert golden_path.is_file(), f"falta el golden {golden_path}"
    assert content == golden_path.read_text(encoding="utf-8")


def test_ass_is_deterministic() -> None:
    assert sample_ass("bold-yellow") == sample_ass("bold-yellow")


def test_ass_header_and_style() -> None:
    content = sample_ass("bold-yellow")

    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "ScriptType: v4.00+" in content
    ass_name = _resolved_font(load_preset("bold-yellow")).ass_name
    assert f"Style: WinClip,{ass_name}," in content


def test_ass_highlights_one_word_per_event() -> None:
    content = sample_ass("bold-yellow")
    dialogues = [line for line in content.splitlines() if line.startswith("Dialogue:")]

    assert dialogues
    for line in dialogues:
        assert line.count("\\c&H0000D6FF&") == 1
    assert all("{\\c&H00FFFFFF&" in line for line in dialogues)


def test_ass_uppercases_for_hormozi() -> None:
    content = sample_ass("hormozi")
    dialogues = [line for line in content.splitlines() if line.startswith("Dialogue:")]

    assert "HOLA" in dialogues[0]
    assert "hola" not in content


def test_ass_safe_zone_margin() -> None:
    preset = load_preset("bold-yellow")
    bottom = (1920 - margin_v(preset)) / 1920

    assert 0.69 <= bottom <= 0.70


def test_ass_without_words_is_valid_but_empty() -> None:
    preset = load_preset("bold-yellow")
    content = build_ass([], preset, font_name="Anton")

    assert "[Events]" in content
    assert not any(line.startswith("Dialogue:") for line in content.splitlines())


def test_write_ass_creates_utf8_file(tmp_path: Path) -> None:
    preset = load_preset("clean-white")
    words = retime_words(sample_transcript(), CLIP_START, CLIP_END)
    cues = build_cues(words, preset)

    path = write_ass(tmp_path / "subs.ass", cues, preset, font_name="Poppins Bold")

    assert path.read_text(encoding="utf-8").startswith("[Script Info]")
    assert "BorderStyle" in path.read_text(encoding="utf-8")
