"""Tests de los subcomandos `winclip ingest` y `winclip transcribe`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from winclip import cli
from winclip.pipeline import transcribe as transcribe_module
from winclip.pipeline.schemas import Transcript
from winclip.pipeline.transcribe import RawSegment, RawTranscription, RawWord

runner = CliRunner()


class FakeMlxBackend:
    """Sustituye a `MlxWhisperBackend` en la CLI para no usar MLX."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def transcribe(self, _audio_path: Path, *, model: str, language: str | None):
        return RawTranscription(
            language="es",
            duration=2.0,
            segments=[
                RawSegment(
                    start=0.0,
                    end=1.0,
                    text="Hola mundo",
                    words=[
                        RawWord(w="Hola", s=0.0, e=0.5, p=0.9),
                        RawWord(w="mundo", s=0.5, e=1.0, p=0.8),
                    ],
                )
            ],
        )


def test_cli_ingest_local_file(cli_session: Path, synthetic_video: Path) -> None:
    result = runner.invoke(cli.app, ["ingest", str(synthetic_video), "--project-id", "clipuno"])

    assert result.exit_code == 0, result.output
    assert "clipuno" in result.output
    project = cli_session / "projects" / "clipuno"
    assert (project / "source" / "original.mp4").is_file()
    assert (project / "source" / "meta.json").is_file()
    assert (project / "audio" / "audio16k.wav").is_file()


def test_cli_ingest_rejects_invalid_project_id(cli_session: Path, synthetic_video: Path) -> None:
    result = runner.invoke(cli.app, ["ingest", str(synthetic_video), "--project-id", "../escape"])

    assert result.exit_code != 0
    assert "inválido" in result.output.lower()
    assert not (cli_session.parent / "escape").exists()


def test_cli_ingest_rejects_missing_file(cli_session: Path, tmp_path: Path) -> None:
    result = runner.invoke(cli.app, ["ingest", str(tmp_path / "no-existe.mp4")])

    assert result.exit_code == 1
    assert "no existe" in result.output


def test_cli_ingest_refuses_existing_project(cli_session: Path, synthetic_video: Path) -> None:
    first = runner.invoke(cli.app, ["ingest", str(synthetic_video), "--project-id", "repetido"])
    assert first.exit_code == 0, first.output

    second = runner.invoke(cli.app, ["ingest", str(synthetic_video), "--project-id", "repetido"])
    assert second.exit_code == 1
    assert "ya está ingestado" in second.output


def test_cli_transcribe_without_project(cli_session: Path) -> None:
    result = runner.invoke(cli.app, ["transcribe", "sinproyecto"])

    assert result.exit_code == 1
    assert "winclip ingest" in result.output


def test_cli_ingest_then_transcribe(
    cli_session: Path, synthetic_video: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(transcribe_module, "MlxWhisperBackend", FakeMlxBackend)
    ingested = runner.invoke(cli.app, ["ingest", str(synthetic_video), "--project-id", "cadena"])
    assert ingested.exit_code == 0, ingested.output

    result = runner.invoke(cli.app, ["transcribe", "cadena", "--model", "tiny", "--language", "es"])

    assert result.exit_code == 0, result.output
    path = cli_session / "projects" / "cadena" / "transcript" / "transcript.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    transcript = Transcript.model_validate(payload)
    assert transcript.model == "mlx-community/whisper-tiny"
    assert transcript.language == "es"
    assert path.is_file()

    reused = runner.invoke(cli.app, ["transcribe", "cadena"])
    assert reused.exit_code == 0, reused.output
    assert "reutilizando" in reused.output


def test_cli_transcribe_rejects_unsupported_language(cli_session: Path) -> None:
    result = runner.invoke(cli.app, ["transcribe", "cadena", "--language", "de"])

    assert result.exit_code != 0
    assert "es, en, auto" in result.output
