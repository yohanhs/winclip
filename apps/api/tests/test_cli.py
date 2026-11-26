"""Tests de la CLI `winclip`."""

from __future__ import annotations

from typer.testing import CliRunner

from winclip import cli
from winclip.core.doctor import CheckResult

runner = CliRunner()


def test_doctor_exit_0_without_errors(monkeypatch) -> None:
    results = [
        CheckResult(name="ffmpeg", status="ok", detail="ffmpeg-full con libass"),
        CheckResult(name="ollama", status="warn", detail="no responde", hint="ollama serve"),
    ]
    monkeypatch.setattr(cli, "run_checks", lambda settings: results)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "ffmpeg" in result.output


def test_doctor_exit_1_with_errors(monkeypatch) -> None:
    results = [
        CheckResult(
            name="ffmpeg", status="error", detail="sin libass", hint="brew install ffmpeg-full"
        ),
    ]
    monkeypatch.setattr(cli, "run_checks", lambda settings: results)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert "ffmpeg-full" in result.output


def test_version_command() -> None:
    result = runner.invoke(cli.app, ["version"])

    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"
