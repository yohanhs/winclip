"""Tests de `winclip.pipeline.select` con `FakeSelectionProvider`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fakes import FakeSelectionProvider

from winclip.core.config import Settings
from winclip.core.storage import LocalStorage
from winclip.llm.router import LLMRouter
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.select import (
    CandidatesDocument,
    MissingTranscriptError,
    SelectionError,
    parse_requested,
    select_clips,
)

PROJECT_ID = "clipuno"


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        **overrides,
    )


def _router(settings: Settings, provider: FakeSelectionProvider) -> LLMRouter:
    return LLMRouter(
        settings,
        {provider.name: provider},
        sleep_fn=lambda _seconds: None,
        jitter_fn=lambda: 0.0,
    )


def _write_rules(tmp_path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "name": "test",
        "min_duration": 5,
        "max_duration": 30,
        **overrides,
    }
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_transcript(
    settings: Settings,
    *,
    sentences: int = 4,
    language: str = "es",
    long_text: bool = False,
    special: dict[int, str] | None = None,
) -> None:
    """Escribe un transcript con frases de 5 s separadas por 1 s de pausa."""
    special = special or {}
    segments = []
    base = 0.0
    for index in range(sentences):
        padding = ("palabra " * 40) if long_text else ""
        texts = [
            f"{padding}tema{index}a",
            f"{padding}tema{index}b",
            f"{padding}{special.get(index, 'cierre')}{index}.",
        ]
        words = [
            WordTimestamp(w=text, s=base + offset * 2.0, e=base + offset * 2.0 + 2.0, p=0.9)
            for offset, text in enumerate(texts)
        ]
        segments.append(
            TranscriptSegment(
                id=index,
                start=words[0].s,
                end=words[-1].e,
                text=" ".join(word.w for word in words),
                words=words,
            )
        )
        base += 7.0

    transcript = Transcript(
        language=language,
        duration=segments[-1].end,
        model="fake",
        segments=segments,
    )
    storage = LocalStorage(settings.storage_dir)
    storage.write_json_atomic(storage.transcript_path(PROJECT_ID), transcript)


def test_parse_requested_accepts_positive_int_and_max() -> None:
    assert parse_requested(5) == 5
    assert parse_requested("5") == 5
    assert parse_requested("max") == "max"
    assert parse_requested("MAX") == "max"
    for value in ("0", "-1", "muchos"):
        with pytest.raises(SelectionError, match="--count"):
            parse_requested(value)


def test_select_short_video_single_pass(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_transcript(settings, sentences=4)
    provider = FakeSelectionProvider("fake", "fake-1", candidates_per_request=3)
    rules = _write_rules(tmp_path)

    result = select_clips(
        PROJECT_ID,
        settings=settings,
        count=2,
        rules_path=rules,
        router=_router(settings, provider),
    )

    document = result.document
    assert result.chunks == 1
    assert document.requested == 2
    assert document.provider == "fake:fake-1"
    assert len(document.candidates) == 2
    assert [candidate.score for candidate in document.candidates] == sorted(
        (candidate.score for candidate in document.candidates), reverse=True
    )
    for candidate in document.candidates:
        assert candidate.language == "es"
        assert 5 <= candidate.end - candidate.start <= 30
        assert candidate.end > candidate.start
        assert candidate.title and candidate.hook
    assert len(provider.calls) == 1

    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert set(payload) == {"project_id", "campaign_id", "requested", "provider", "candidates"}
    assert payload["requested"] == 2
    assert CandidatesDocument.model_validate(payload).project_id == PROJECT_ID


def test_select_count_max_uses_threshold_and_writes_all_valid(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_transcript(settings, sentences=6)
    provider = FakeSelectionProvider("fake", "fake-1", candidates_per_request=6, score=85)

    result = select_clips(
        PROJECT_ID,
        settings=settings,
        count="max",
        rules_path=_write_rules(tmp_path),
        router=_router(settings, provider),
    )

    assert result.document.requested == "max"
    assert len(result.document.candidates) == 6
    assert all(
        candidate.score >= settings.llm_score_threshold for candidate in result.document.candidates
    )
    assert all(candidate.rule_violations == [] for candidate in result.document.candidates)


def test_select_applies_banned_words_and_required_keywords(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_transcript(settings, sentences=4, special={1: "prohibido"})
    provider = FakeSelectionProvider(
        "fake",
        "fake-1",
        candidates_per_request=4,
        skip_lines_containing=("prohibido",),
    )
    rules = _write_rules(tmp_path, banned_words=["prohibido"], required_keywords=["inexistente"])

    result = select_clips(
        PROJECT_ID,
        settings=settings,
        count=4,
        rules_path=rules,
        router=_router(settings, provider),
    )

    starts = {candidate.start for candidate in result.document.candidates}
    assert 7.0 not in starts
    assert result.document.candidates
    for candidate in result.document.candidates:
        assert len(candidate.rule_violations) == 1
        violation = candidate.rule_violations[0]
        assert violation.code == "missing_required_keyword"
        assert violation.severity == "warning"

    max_result = select_clips(
        PROJECT_ID,
        settings=settings,
        count="max",
        rules_path=rules,
        router=_router(settings, provider),
    )
    assert max_result.document.candidates == []


def test_select_language_follows_rules_or_transcript(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_transcript(settings, sentences=3, language="en")
    provider = FakeSelectionProvider("fake", candidates_per_request=2)

    forced = select_clips(
        PROJECT_ID,
        settings=settings,
        count=2,
        rules_path=_write_rules(tmp_path, language="es"),
        router=_router(settings, provider),
    )
    assert all(candidate.language == "es" for candidate in forced.document.candidates)
    assert "es" in provider.calls[0][0]

    inherited = select_clips(
        PROJECT_ID,
        settings=settings,
        count=2,
        rules_path=_write_rules(tmp_path, language="auto"),
        router=_router(settings, provider),
        use_cache=False,
    )
    assert all(candidate.language == "en" for candidate in inherited.document.candidates)


def test_select_long_video_chunks_and_ranks(tmp_path: Path) -> None:
    settings = _settings(tmp_path, llm_single_pass_max_chars=1200)
    _write_transcript(settings, sentences=8, long_text=True)
    provider = FakeSelectionProvider("fake", "fake-1", candidates_per_request=2)

    result = select_clips(
        PROJECT_ID,
        settings=settings,
        count=3,
        rules_path=_write_rules(tmp_path),
        router=_router(settings, provider),
    )

    assert result.chunks > 1
    assert len(result.document.candidates) <= 3
    assert result.document.candidates
    # La última llamada es el ranking global.
    assert provider.calls[-1][2].__name__ == "RankingProposal"
    assert (
        sum(1 for _, _, schema in provider.calls if schema.__name__ == "SelectionProposal")
        == result.chunks
    )


def test_select_cache_reuses_results_and_is_keyed_by_prompt_version(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_transcript(settings, sentences=4)
    rules = _write_rules(tmp_path)
    provider = FakeSelectionProvider("fake", "fake-1", candidates_per_request=2)
    first = select_clips(
        PROJECT_ID,
        settings=settings,
        count=2,
        rules_path=rules,
        router=_router(settings, provider),
    )

    never_called = FakeSelectionProvider("fake", "fake-1")
    second = select_clips(
        PROJECT_ID,
        settings=settings,
        count=2,
        rules_path=rules,
        router=_router(settings, never_called),
    )
    assert never_called.calls == []
    assert second.cached is True
    assert [(c.start, c.end, c.score) for c in second.document.candidates] == [
        (c.start, c.end, c.score) for c in first.document.candidates
    ]

    cache_dir = settings.storage_dir / "cache" / "llm"
    entries = [json.loads(path.read_text(encoding="utf-8")) for path in cache_dir.glob("*.json")]
    assert entries
    assert {entry["logical_model"] for entry in entries} == {"clip-selection:single:v1"}


def test_select_without_cache_calls_provider_again(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_transcript(settings, sentences=3)
    provider = FakeSelectionProvider("fake", candidates_per_request=2)
    rules = _write_rules(tmp_path)
    select_clips(
        PROJECT_ID,
        settings=settings,
        count=1,
        rules_path=rules,
        router=_router(settings, provider),
    )
    select_clips(
        PROJECT_ID,
        settings=settings,
        count=1,
        rules_path=rules,
        router=_router(settings, provider),
        use_cache=False,
    )

    assert len(provider.calls) == 2


def test_select_requires_transcript(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    provider = FakeSelectionProvider("fake")

    with pytest.raises(MissingTranscriptError, match="winclip transcribe"):
        select_clips(
            PROJECT_ID,
            settings=settings,
            count=1,
            router=_router(settings, provider),
        )


def test_select_rejects_transcript_without_words(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    storage = LocalStorage(settings.storage_dir)
    storage.write_json_atomic(
        storage.transcript_path(PROJECT_ID),
        Transcript(language="es", duration=10, model="fake", segments=[]),
    )
    provider = FakeSelectionProvider("fake")

    with pytest.raises(SelectionError, match="no contiene palabras"):
        select_clips(
            PROJECT_ID,
            settings=settings,
            count=1,
            router=_router(settings, provider),
        )


def test_select_drops_proposals_outside_duration(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_transcript(settings, sentences=2)
    provider = FakeSelectionProvider("fake", candidates_per_request=2)

    result = select_clips(
        PROJECT_ID,
        settings=settings,
        count=2,
        rules_path=_write_rules(tmp_path, min_duration=25, max_duration=30),
        router=_router(settings, provider),
    )

    assert result.document.candidates == []
