"""Tests de `word_overrides` en `subtitles/layout.py`, `.ass` y huella `.render.sha256`."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from winclip.core.config import Settings
from winclip.pipeline.render import compute_fingerprint
from winclip.pipeline.render_models import RenderOptions
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.subtitles.ass_engine import write_ass
from winclip.pipeline.subtitles.fonts import resolve_font
from winclip.pipeline.subtitles.layout import build_cues, retime_words, word_override_key
from winclip.pipeline.subtitles.presets import load_preset


def _sample_transcript() -> Transcript:
    return Transcript(
        language="es",
        duration=30.0,
        model="fake-whisper",
        segments=[
            TranscriptSegment(
                id=0,
                start=0.0,
                end=5.0,
                text="Hola Juc viral",
                words=[
                    WordTimestamp(w="Hola", s=1.0, e=1.4, p=0.99),
                    WordTimestamp(w="Juc", s=1.5, e=1.9, p=0.88),
                    WordTimestamp(w="viral", s=2.0, e=2.5, p=0.97),
                ],
            )
        ],
    )


def test_retime_words_applies_word_overrides_and_preserves_timestamps() -> None:
    transcript = _sample_transcript()
    key = word_override_key(1.5, 1.9)
    assert key == "1500:1900"

    original_words = retime_words(transcript, 1.0, 4.0, uppercase=False)
    overridden_words = retime_words(
        transcript,
        1.0,
        4.0,
        uppercase=False,
        word_overrides={key: "Hook"},
    )

    assert [w.text for w in original_words] == ["Hola", "Juc", "viral"]
    assert [w.text for w in overridden_words] == ["Hola", "Hook", "viral"]
    # Timestamps idénticos
    assert [(w.start, w.end) for w in overridden_words] == [
        (w.start, w.end) for w in original_words
    ]
    # El objeto Transcript en memoria no se muta
    assert transcript.segments[0].words[1].w == "Juc"


def test_retime_words_respects_uppercase_with_overrides() -> None:
    transcript = _sample_transcript()
    words = retime_words(
        transcript,
        1.0,
        4.0,
        uppercase=True,
        word_overrides={"1500:1900": "Hook"},
    )
    assert [w.text for w in words] == ["HOLA", "HOOK", "VIRAL"]


def test_write_ass_reflects_word_override(tmp_path: Path) -> None:
    transcript = _sample_transcript()
    preset = load_preset("clean-white")
    words = retime_words(
        transcript,
        1.0,
        4.0,
        uppercase=preset.uppercase,
        word_overrides={"1500:1900": "Hook"},
    )
    cues = build_cues(words, preset)
    ass_path = tmp_path / "subs.ass"
    write_ass(ass_path, cues, preset, font_name="Inter")

    content = ass_path.read_text(encoding="utf-8")
    assert "Hook" in content
    assert "Juc" not in content


def test_compute_fingerprint_changes_with_word_overrides_and_crop(tmp_path: Path) -> None:
    source = tmp_path / "original.mp4"
    source.write_bytes(b"fake-video-bytes")
    candidate = SimpleNamespace(id="cand1", start=1.0, end=10.0, hook="Hook!")
    preset = load_preset("bold-yellow")
    font = resolve_font(preset.font, fallback=preset.fallback_font, settings=Settings())

    fp_base = compute_fingerprint(
        source,
        candidate,
        options=RenderOptions(),
        preset=preset,
        font=font,
        fps=30.0,
    )
    fp_word = compute_fingerprint(
        source,
        candidate,
        options=RenderOptions(word_overrides={"1500:1900": "Hook"}),
        preset=preset,
        font=font,
        fps=30.0,
    )
    fp_crop = compute_fingerprint(
        source,
        candidate,
        options=RenderOptions(reframe="center", crop_x_pct=35.0, crop_y_pct=25.0, zoom_pct=120.0),
        preset=preset,
        font=font,
        fps=30.0,
    )

    assert fp_base != fp_word
    assert fp_base != fp_crop
    assert fp_word != fp_crop
