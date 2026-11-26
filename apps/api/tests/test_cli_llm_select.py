"""Tests de los subcomandos `winclip llm test` y `winclip select`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fakes import FakeLLMProvider, FakeSelectionProvider
from typer.testing import CliRunner

from winclip import cli
from winclip.core.config import get_settings
from winclip.core.storage import LocalStorage
from winclip.llm.router import LLMRouter
from winclip.pipeline.schemas import Transcript, TranscriptSegment, WordTimestamp
from winclip.pipeline.select import CandidatesDocument

runner = CliRunner()
PROJECT_ID = "clipuno"


def _router(provider: object) -> LLMRouter:
    settings = get_settings()
    return LLMRouter(
        settings,
        {provider.name: provider},  # type: ignore[attr-defined]
        sleep_fn=lambda _seconds: None,
        jitter_fn=lambda: 0.0,
    )


def _write_rules(tmp_path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {"min_duration": 5, "max_duration": 30, **overrides}
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_transcript() -> None:
    storage = LocalStorage(get_settings().storage_dir)
    segments = []
    base = 0.0
    for index in range(4):
        texts = [f"tema{index}a", f"tema{index}b", f"cierre{index}."]
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
    storage.write_json_atomic(
        storage.transcript_path(PROJECT_ID),
        Transcript(
            language="es",
            duration=segments[-1].end,
            model="fake",
            segments=segments,
        ),
    )


def test_llm_test_reports_provider_and_attempts(
    cli_session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeLLMProvider(
        "fake",
        "fake-1",
        responses=['{"ok": true, "message": "pong"}'],
    )
    monkeypatch.setattr(cli, "_build_llm_router", lambda: _router(provider))

    result = runner.invoke(cli.app, ["llm", "test"])

    assert result.exit_code == 0, result.output
    assert "fake" in result.output
    assert "pong" in result.output
    assert "Intentos LLM" in result.output


def test_llm_test_fails_without_available_provider(
    cli_session: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeLLMProvider("fake", available=False)
    monkeypatch.setattr(cli, "_build_llm_router", lambda: _router(provider))

    result = runner.invoke(cli.app, ["llm", "test"])

    assert result.exit_code == 1
    assert "error" in result.output.lower()
    assert "sin credenciales" in result.output


def test_select_writes_candidates_and_prints_table(
    cli_session: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_transcript()
    provider = FakeSelectionProvider("fake", "fake-1", candidates_per_request=3)
    monkeypatch.setattr(cli, "_build_llm_router", lambda: _router(provider))

    result = runner.invoke(
        cli.app,
        ["select", PROJECT_ID, "--count", "2", "--rules", str(_write_rules(tmp_path))],
    )

    assert result.exit_code == 0, result.output
    assert "selección:" in result.output
    assert "Candidatos" in result.output
    assert "Clip 1" in result.output

    path = cli_session / "projects" / PROJECT_ID / "selection" / "candidates.json"
    document = CandidatesDocument.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert document.requested == 2
    assert len(document.candidates) == 2


def test_select_accepts_count_max(
    cli_session: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_transcript()
    provider = FakeSelectionProvider("fake", "fake-1", candidates_per_request=4, score=90)
    monkeypatch.setattr(cli, "_build_llm_router", lambda: _router(provider))

    result = runner.invoke(
        cli.app,
        ["select", PROJECT_ID, "--count", "max", "--rules", str(_write_rules(tmp_path))],
    )

    assert result.exit_code == 0, result.output
    path = cli_session / "projects" / PROJECT_ID / "selection" / "candidates.json"
    document = CandidatesDocument.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert document.requested == "max"
    assert document.candidates


def test_select_requires_transcript(cli_session: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_build_llm_router", lambda: _router(FakeSelectionProvider("fake")))

    result = runner.invoke(cli.app, ["select", "sinproyecto", "--count", "2"])

    assert result.exit_code == 1
    assert "winclip transcribe" in result.output


def test_select_rejects_invalid_count(cli_session: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_transcript()
    monkeypatch.setattr(cli, "_build_llm_router", lambda: _router(FakeSelectionProvider("fake")))

    result = runner.invoke(cli.app, ["select", PROJECT_ID, "--count", "0"])

    assert result.exit_code == 1
    assert "max" in result.output


def test_select_rejects_invalid_rules_before_llm(
    cli_session: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_transcript()
    provider = FakeSelectionProvider("fake")
    monkeypatch.setattr(cli, "_build_llm_router", lambda: _router(provider))
    broken = tmp_path / "rules.json"
    broken.write_text('{"language": "de"}', encoding="utf-8")

    result = runner.invoke(cli.app, ["select", PROJECT_ID, "--rules", str(broken)])

    assert result.exit_code == 1
    assert "reglas inválidas" in result.output
    assert provider.calls == []

    missing = runner.invoke(
        cli.app,
        ["select", PROJECT_ID, "--rules", str(tmp_path / "no-existe.json")],
    )
    assert missing.exit_code == 1
    assert "no existe el archivo de reglas" in missing.output


def test_llm_and_select_help_document_options() -> None:
    llm_help = runner.invoke(cli.app, ["llm", "test", "--help"])
    select_help = runner.invoke(cli.app, ["select", "--help"])

    assert llm_help.exit_code == 0
    assert select_help.exit_code == 0
    assert "--count" in select_help.output
    assert "--rules" in select_help.output
    assert "--no-cache" in select_help.output
