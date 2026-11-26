"""Tests del pipeline de transcripción con un backend falso."""

from __future__ import annotations

from pathlib import Path

import pytest

from winclip.core.config import Settings
from winclip.core.storage import LocalStorage
from winclip.pipeline.schemas import SourceMeta, Transcript
from winclip.pipeline.transcribe import (
    AudioNotReadyError,
    RawSegment,
    RawTranscription,
    RawWord,
    TranscriptionError,
    transcribe,
)


def _prepare_project(settings: Settings, project_id: str = "proyecto01") -> LocalStorage:
    storage = LocalStorage(settings.storage_dir)
    storage.ensure_project_dirs(project_id)
    storage.audio_path(project_id).write_bytes(b"RIFF-fake-wav")
    return storage


def _raw(language: str | None = "es", duration: float | None = None) -> RawTranscription:
    return RawTranscription(
        language=language,
        duration=duration,
        segments=[
            RawSegment(
                start=5.0,
                end=6.0,
                text="  segundo   segmento ",
                words=[RawWord(w=" segundo ", s=5.1, e=5.4, p=0.8)],
            ),
            RawSegment(
                start=0.0,
                end=4.2,
                text=" Hola a todos… ",
                words=[
                    RawWord(w=" Hola ", s=0.0, e=0.31, p=0.98),
                    RawWord(w="a", s=0.4, e=0.2, p=1.7),
                    RawWord(w="todos…", s=0.5, e=1.0, p=None),
                    RawWord(w="   ", s=1.1, e=1.2, p=0.5),
                ],
            ),
        ],
    )


class FakeBackend:
    """Backend que devuelve una transcripción fija y registra sus llamadas."""

    def __init__(self, result: RawTranscription) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def transcribe(self, audio_path: Path, *, model: str, language: str | None) -> RawTranscription:
        self.calls.append({"audio": audio_path, "model": model, "language": language})
        return self.result


def test_transcribe_writes_architecture_contract(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)
    result = transcribe(
        "proyecto01",
        settings=sample_settings,
        storage=storage,
        backend=FakeBackend(_raw()),
    )

    payload = storage.read_json(storage.transcript_path("proyecto01"))
    transcript = Transcript.model_validate(payload)

    assert set(payload) == {"language", "duration", "model", "segments"}
    assert set(payload["segments"][0]) == {"id", "start", "end", "text", "words"}
    assert set(payload["segments"][0]["words"][0]) == {"w", "s", "e", "p"}

    assert transcript.language == "es"
    assert transcript.model == sample_settings.whisper_model
    assert [segment.id for segment in transcript.segments] == [0, 1]
    assert [segment.text for segment in transcript.segments] == [
        "Hola a todos…",
        "segundo segmento",
    ]
    assert result.transcript.duration == 6.0

    words = transcript.segments[0].words
    assert [word.w for word in words] == ["Hola", "a", "todos…"]
    assert words[1].e == words[1].s
    assert words[1].p == 1.0
    assert words[2].p == 1.0


def test_transcribe_forces_language(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)
    backend = FakeBackend(_raw(language=None))

    result = transcribe(
        "proyecto01",
        settings=sample_settings,
        storage=storage,
        language="es",
        backend=backend,
    )

    assert backend.calls[0]["language"] == "es"
    assert result.transcript.language == "es"


def test_transcribe_auto_detects_language(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)
    backend = FakeBackend(_raw(language="en"))

    result = transcribe(
        "proyecto01",
        settings=sample_settings,
        storage=storage,
        language="auto",
        backend=backend,
    )

    assert backend.calls[0]["language"] is None
    assert result.transcript.language == "en"


def test_transcribe_rejects_unsupported_language(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)

    with pytest.raises(TranscriptionError, match="es, en, auto"):
        transcribe(
            "proyecto01",
            settings=sample_settings,
            storage=storage,
            language="de",
            backend=FakeBackend(_raw()),
        )


def test_transcribe_model_tiny_alias(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)
    backend = FakeBackend(_raw())

    result = transcribe(
        "proyecto01",
        settings=sample_settings,
        storage=storage,
        model="tiny",
        backend=backend,
    )

    assert backend.calls[0]["model"] == "mlx-community/whisper-tiny"
    assert result.transcript.model == "mlx-community/whisper-tiny"


def test_transcribe_uses_duration_from_source_meta(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)
    storage.write_json_atomic(
        storage.source_meta_path("proyecto01"),
        SourceMeta(
            project_id="proyecto01",
            source_type="file",
            original_filename="original.mp4",
            title="demo",
            duration=42.0,
            has_audio=True,
            file_size_bytes=1024,
        ),
    )

    result = transcribe(
        "proyecto01",
        settings=sample_settings,
        storage=storage,
        backend=FakeBackend(_raw()),
    )

    assert result.transcript.duration == 42.0


def test_transcribe_reuses_valid_transcript(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)
    first = transcribe(
        "proyecto01", settings=sample_settings, storage=storage, backend=FakeBackend(_raw())
    )
    before = first.path.read_bytes()

    class ExplodingBackend:
        def transcribe(self, *_args: object, **_kwargs: object) -> RawTranscription:
            raise AssertionError("no debe invocarse el motor si la transcripción existe")

    second = transcribe(
        "proyecto01",
        settings=sample_settings,
        storage=storage,
        backend=ExplodingBackend(),
    )

    assert second.reused is True
    assert second.transcript == first.transcript
    assert second.path.read_bytes() == before


def test_transcribe_force_recomputes(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)
    first_backend = FakeBackend(_raw())
    transcribe("proyecto01", settings=sample_settings, storage=storage, backend=first_backend)

    other = RawTranscription(
        language="en",
        duration=3.0,
        segments=[RawSegment(start=0.0, end=1.0, text="hi", words=[RawWord("hi", 0.0, 1.0, 0.9)])],
    )
    second_backend = FakeBackend(other)
    result = transcribe(
        "proyecto01",
        settings=sample_settings,
        storage=storage,
        force=True,
        backend=second_backend,
    )

    assert len(first_backend.calls) == 1
    assert len(second_backend.calls) == 1
    assert result.reused is False
    assert result.transcript.language == "en"


def test_transcribe_recomputes_when_existing_file_is_corrupt(
    sample_settings: Settings,
) -> None:
    storage = _prepare_project(sample_settings)
    path = storage.transcript_path("proyecto01")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ no es json", encoding="utf-8")

    result = transcribe(
        "proyecto01", settings=sample_settings, storage=storage, backend=FakeBackend(_raw())
    )

    assert result.reused is False
    assert Transcript.model_validate(storage.read_json(path)).language == "es"


def test_transcribe_without_audio_asks_for_ingest(sample_settings: Settings) -> None:
    with pytest.raises(AudioNotReadyError, match="winclip ingest"):
        transcribe(
            "sin-audio",
            settings=sample_settings,
            backend=FakeBackend(_raw()),
        )


def test_transcribe_progress_reaches_100(sample_settings: Settings) -> None:
    storage = _prepare_project(sample_settings)
    events: list[tuple[float, str]] = []

    transcribe(
        "proyecto01",
        settings=sample_settings,
        storage=storage,
        backend=FakeBackend(_raw()),
        progress=lambda value, stage: events.append((value, stage)),
    )

    values = [value for value, _ in events]
    stages = [stage for _, stage in events]
    assert values == sorted(values)
    assert values[-1] == 100.0
    assert stages[:2] == ["load_model", "transcribe"]
    assert stages[-1] == "save"
