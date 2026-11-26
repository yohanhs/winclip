"""Tests de los contratos Pydantic (`source/meta.json` y `transcript.json`)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from winclip.pipeline.schemas import SourceMeta, Transcript


def _meta_payload() -> dict[str, object]:
    return {
        "project_id": "01jex8z9abc123def456gh7890",
        "source_type": "url",
        "source_url": "https://www.youtube.com/watch?v=abc",
        "original_filename": "original.mp4",
        "title": "Título del video",
        "channel": "HookVault",
        "uploader_id": "@hookvault",
        "duration": 612.4,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "video_codec": "h264",
        "audio_codec": "aac",
        "audio_sample_rate": 48000,
        "has_audio": True,
        "file_size_bytes": 123456789,
        "created_at": "2026-11-26T15:00:00Z",
    }


def _transcript_payload() -> dict[str, object]:
    return {
        "language": "es",
        "duration": 3725.4,
        "model": "mlx-community/whisper-large-v3-turbo",
        "segments": [
            {
                "id": 0,
                "start": 0.0,
                "end": 4.2,
                "text": "Hola a todos…",
                "words": [{"w": "Hola", "s": 0.0, "e": 0.31, "p": 0.98}],
            }
        ],
    }


def test_source_meta_accepts_design_contract() -> None:
    meta = SourceMeta.model_validate(_meta_payload())

    assert meta.source_type == "url"
    assert meta.channel == "HookVault"
    assert meta.has_audio is True


def test_transcript_accepts_architecture_contract() -> None:
    transcript = Transcript.model_validate(_transcript_payload())

    assert transcript.language == "es"
    word = transcript.segments[0].words[0]
    assert (word.w, word.s, word.e, word.p) == ("Hola", 0.0, 0.31, 0.98)


def test_word_rejects_inverted_timestamps() -> None:
    payload = _transcript_payload()
    payload["segments"][0]["words"][0].update({"s": 1.0, "e": 0.5})  # type: ignore[index]

    with pytest.raises(ValidationError, match="anterior al inicio"):
        Transcript.model_validate(payload)


def test_segment_rejects_inverted_timestamps() -> None:
    payload = _transcript_payload()
    payload["segments"][0].update({"start": 5.0, "end": 4.0})  # type: ignore[index]

    with pytest.raises(ValidationError, match="anterior al inicio"):
        Transcript.model_validate(payload)


@pytest.mark.parametrize("probability", [-0.1, 1.1])
def test_word_rejects_probability_out_of_range(probability: float) -> None:
    payload = _transcript_payload()
    payload["segments"][0]["words"][0]["p"] = probability  # type: ignore[index]

    with pytest.raises(ValidationError):
        Transcript.model_validate(payload)


def test_contracts_forbid_unknown_fields() -> None:
    payload = _meta_payload()
    payload["extra"] = "no permitido"

    with pytest.raises(ValidationError):
        SourceMeta.model_validate(payload)
