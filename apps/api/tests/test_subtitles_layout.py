"""Tests de re-temporización y agrupación karaoke."""

from __future__ import annotations

from itertools import pairwise

import pytest

from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.subtitles.layout import (
    SubtitleCue,
    TimedWord,
    build_cues,
    cue_states,
    retime_words,
)
from winclip.pipeline.subtitles.presets import load_preset


def _word(text: str, start: float, end: float) -> WordTimestamp:
    return WordTimestamp(w=text, s=start, e=end, p=0.95)


def _transcript() -> Transcript:
    return Transcript(
        language="es",
        duration=120.0,
        model="test",
        segments=[
            TranscriptSegment(
                id=0,
                start=0.0,
                end=100.0,
                text="frase",
                words=[
                    _word("Antes", 9.0, 9.5),
                    _word("Hola", 10.5, 10.9),
                    _word("a", 10.9, 11.1),
                    _word("todos,", 11.1, 11.8),
                    _word("esto", 11.8, 12.4),
                    _word("es", 12.4, 12.6),
                    _word("WinClip.", 12.6, 13.4),
                    _word("Después", 25.0, 25.5),
                ],
            )
        ],
    )


def test_retime_filters_and_shifts_to_clip_zero() -> None:
    words = retime_words(_transcript(), 10.0, 20.0)

    assert [word.text for word in words] == [
        "Hola",
        "a",
        "todos,",
        "esto",
        "es",
        "WinClip.",
    ]
    assert words[0].start == pytest.approx(0.5)
    assert words[0].end == pytest.approx(0.9)
    assert words[-1].end == pytest.approx(3.4)


def test_retime_normalizes_overlaps_and_zero_durations() -> None:
    transcript = Transcript(
        language="es",
        duration=10.0,
        model="test",
        segments=[
            TranscriptSegment(
                id=0,
                start=0.0,
                end=5.0,
                text="x",
                words=[_word("uno", 1.0, 1.5), _word("dos", 1.2, 1.2), _word("tres", 1.3, 1.4)],
            )
        ],
    )

    words = retime_words(transcript, 1.0, 5.0)

    for previous, current in pairwise(words):
        assert current.start >= previous.end
    assert all(word.end > word.start for word in words)


def test_retime_uppercases_when_preset_asks() -> None:
    words = retime_words(_transcript(), 10.0, 14.0, uppercase=True)
    assert words[0].text == "HOLA"
    assert words[5].text == "WINCLIP."


def test_retime_without_words_returns_empty() -> None:
    assert retime_words(_transcript(), 40.0, 60.0) == []


def test_build_cues_respects_word_and_char_limits() -> None:
    preset = load_preset("bold-yellow")
    words = [
        TimedWord(text=word, start=index * 0.3, end=index * 0.3 + 0.28)
        for index, word in enumerate(
            [
                "esto",
                "es",
                "una",
                "frase",
                "larga",
                "con",
                "una",
                "coma,",
                "y",
                "después",
                "seguimos",
                "hablando",
                "del",
                "tema",
            ]
        )
    ]

    cues = build_cues(words, preset)

    assert len(cues) > 1
    for cue in cues:
        assert 1 <= len(cue.words) <= preset.max_words_per_cue
        assert 1 <= len(cue.lines) <= preset.max_lines
        assert all(
            len(" ".join(word.text for word in line)) <= preset.max_chars_per_line
            for line in cue.lines
        )
        assert " ".join(word.text for line in cue.lines for word in line) == cue.text


def test_build_cues_breaks_on_terminal_punctuation() -> None:
    preset = load_preset("bold-yellow")
    words = [
        TimedWord("primera", 0.0, 0.3),
        TimedWord("frase.", 0.3, 0.6),
        TimedWord("segunda", 0.6, 0.9),
        TimedWord("frase.", 0.9, 1.2),
    ]

    cues = build_cues(words, preset)

    assert [cue.text for cue in cues] == ["primera frase.", "segunda frase."]


def test_build_cues_breaks_on_long_pause() -> None:
    preset = load_preset("bold-yellow")
    words = [
        TimedWord("antes", 0.0, 0.3),
        TimedWord("pausa", 1.5, 1.8),
    ]

    cues = build_cues(words, preset)

    assert len(cues) == 2


def test_build_cues_without_words() -> None:
    assert build_cues([], load_preset("hormozi")) == []


def test_cue_states_cover_every_word() -> None:
    preset = load_preset("bold-yellow")
    cue = SubtitleCue(
        words=(
            TimedWord("una", 0.0, 0.3),
            TimedWord("dos", 0.3, 0.6),
            TimedWord("tres", 0.6, 1.0),
        ),
        lines=(
            (TimedWord("una", 0.0, 0.3), TimedWord("dos", 0.3, 0.6)),
            (TimedWord("tres", 0.6, 1.0),),
        ),
    )

    states = cue_states(cue)

    assert [state.word.text for state in states] == ["una", "dos", "tres"]
    assert states[0].end == pytest.approx(0.3)
    assert states[-1].end == pytest.approx(1.0)
    assert states[-1].line_index == 1
    assert preset.name == "bold-yellow"


def test_cue_keeps_emoji_extension_point() -> None:
    cue = SubtitleCue(
        words=(TimedWord("hola", 0.0, 0.4),),
        lines=((TimedWord("hola", 0.0, 0.4),),),
        emoji="🔥",
    )
    assert cue.emoji == "🔥"
