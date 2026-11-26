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


def test_db_upgrade_command_migrates_storage(cli_session) -> None:
    result = runner.invoke(cli.app, ["db", "upgrade"])

    assert result.exit_code == 0, result.output
    assert (cli_session / "winclip.db").is_file()
    assert "migraciones al día" in result.output


def test_worker_and_db_commands_are_registered() -> None:
    help_text = runner.invoke(cli.app, ["--help"]).output

    assert "worker" in help_text
    assert "db" in help_text

    worker_help = runner.invoke(cli.app, ["worker", "--help"])
    assert worker_help.exit_code == 0
    assert "--light-concurrency" in worker_help.output
    assert "--poll-interval" in worker_help.output

    db_help = runner.invoke(cli.app, ["db", "--help"])
    assert db_help.exit_code == 0
    assert "upgrade" in db_help.output
