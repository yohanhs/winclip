"""Tests de `winclip.pipeline.segment`."""

from __future__ import annotations

import pytest

from winclip.llm.prompts import PromptError, load_prompt
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.segment import (
    build_utterances,
    chunk_utterances,
    flatten_words,
    format_timestamp,
    nearest_word_range,
    serialize_utterances,
    snap_to_words,
    span_text,
)


def _transcript(sentences: list[list[tuple[str, float]]], *, language: str = "es") -> Transcript:
    """Construye un transcript con palabras `(texto, inicio)` de 1.0 s de duración."""
    segments = []
    for index, sentence in enumerate(sentences):
        words = [WordTimestamp(w=text, s=start, e=start + 1.0, p=0.9) for text, start in sentence]
        segments.append(
            TranscriptSegment(
                id=index,
                start=words[0].s,
                end=words[-1].e,
                text=" ".join(word.w for word in words),
                words=words,
            )
        )
    return Transcript(
        language=language,
        duration=max((segment.end for segment in segments), default=0.0),
        model="fake",
        segments=segments,
    )


def test_flatten_words_skips_empty_and_indexes_globally() -> None:
    transcript = _transcript([[("Hola", 0.0), (" ", 1.0)], [("mundo", 2.0)]])

    words = flatten_words(transcript)

    assert [word.text for word in words] == ["Hola", "mundo"]
    assert [word.index for word in words] == [0, 1]


def test_utterances_split_by_terminal_punctuation() -> None:
    transcript = _transcript(
        [
            [("Hola", 0.0), ("mundo.", 1.0), ("¿Qué", 2.0), ("tal?", 3.0), ("Bien", 4.0)],
        ]
    )
    words = flatten_words(transcript)

    utterances = build_utterances(words)

    assert [utterance.text for utterance in utterances] == ["Hola mundo.", "¿Qué tal?", "Bien"]
    assert [utterance.id for utterance in utterances] == ["U0001", "U0002", "U0003"]
    assert utterances[0].start == 0.0
    assert utterances[1].end == 4.0


def test_utterances_split_by_pause() -> None:
    transcript = _transcript([[("Hola", 0.0), ("mundo", 1.0), ("Otra", 3.0)]])

    utterances = build_utterances(flatten_words(transcript), pause_seconds=0.7)

    assert len(utterances) == 2
    assert utterances[1].text == "Otra"


def test_utterances_cap_max_words_without_punctuation() -> None:
    transcript = _transcript([[("palabra", float(index)) for index in range(6)]])

    utterances = build_utterances(flatten_words(transcript), max_words=3)

    assert len(utterances) == 2
    assert (utterances[0].first_word, utterances[0].last_word) == (0, 2)
    assert (utterances[1].first_word, utterances[1].last_word) == (3, 5)


def test_format_timestamp_and_serialization() -> None:
    transcript = _transcript([[("Hola", 252.3), ("mundo.", 253.0)]])

    line = serialize_utterances(build_utterances(flatten_words(transcript)))

    assert format_timestamp(252.3) == "04:12.3"
    assert format_timestamp(3723.4) == "1:02:03.4"
    assert line == "[U0001 04:12.3-04:14.0] Hola mundo."


def test_chunks_overlap_and_respect_budget() -> None:
    sentences = [[(f"palabra{index}.", float(index))] for index in range(12)]
    transcript = _transcript(sentences)
    utterances = build_utterances(flatten_words(transcript), pause_seconds=0.1)
    line_length = len(serialize_utterances(utterances[:1]))

    chunks = chunk_utterances(utterances, max_chars=line_length * 3 + 3, overlap_ratio=0.5)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(serialize_utterances(chunk)) <= line_length * 3 + 3
    # La segunda ventana empieza antes de donde terminó la primera.
    first_ids = [utterance.id for utterance in chunks[0]]
    assert chunks[1][0].id in first_ids


def test_chunking_returns_single_chunk_when_it_fits() -> None:
    utterances = build_utterances(flatten_words(_transcript([[("Hola", 0.0)]])))

    assert chunk_utterances(utterances, max_chars=10_000) == [utterances]


def test_nearest_word_range_snaps_to_word_boundaries() -> None:
    transcript = _transcript([[("uno", 0.0), ("dos", 1.5), ("tres", 3.0)]])
    words = flatten_words(transcript)

    first, last = nearest_word_range(words, 1.4, 3.6)

    assert (first, last) == (1, 2)


def test_snap_never_cuts_words_and_fits_duration() -> None:
    transcript = _transcript([[("uno", 0.0), ("dos", 1.5), ("tres", 3.0), ("cuatro", 4.5)]])
    words = flatten_words(transcript)

    span = snap_to_words(words, 1.4, 3.6, min_duration=1.0, max_duration=4.0)

    assert span is not None
    first, last = span
    assert words[first].start >= 1.5
    assert words[last].end <= 4.5
    assert span_text(words, first, last) == "dos tres"


def test_snap_expands_short_span_within_tolerance() -> None:
    transcript = _transcript([[("uno", 0.0), ("dos", 1.5), ("tres", 3.0), ("cuatro", 4.5)]])
    words = flatten_words(transcript)

    span = snap_to_words(words, 1.5, 3.6, min_duration=4.0, max_duration=10.0, tolerance=3.0)

    assert span is not None
    first, last = span
    assert words[last].end - words[first].start >= 4.0


def test_snap_discards_span_far_outside_duration() -> None:
    transcript = _transcript([[("uno", 0.0), ("dos", 1.5)]])
    words = flatten_words(transcript)

    assert snap_to_words(words, 0.0, 1.0, min_duration=20, max_duration=60) is None


def test_prompts_are_versioned_and_renderable() -> None:
    single = load_prompt("select_single_v1")
    chunk = load_prompt("select_chunk_v1")
    rank = load_prompt("select_rank_v1")

    assert single.version == "1"
    assert single.logical_model == "clip-selection:single:v1"
    assert chunk.logical_model == "clip-selection:chunk:v1"
    assert rank.logical_model == "clip-selection:rank:v1"
    rendered = single.render(
        language="es",
        min_duration=20,
        max_duration=60,
        requested=5,
        rules_block="- sin reglas",
    )
    assert "20" in rendered and "60" in rendered
    assert "{language}" not in rendered

    with pytest.raises(PromptError, match="falta el valor"):
        single.render(language="es")
