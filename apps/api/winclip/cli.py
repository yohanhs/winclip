"""CLI de WinClip (`winclip …`)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from winclip import __version__
from winclip.core.config import get_settings
from winclip.core.doctor import CheckResult, has_errors, run_checks

app = typer.Typer(
    name="winclip",
    help="WinClip: clipping local de vídeos largos a shorts verticales.",
    no_args_is_help=True,
    add_completion=False,
)

_STATUS_STYLE = {"ok": "green", "warn": "yellow", "error": "red"}
_STATUS_LABEL = {"ok": "ok", "warn": "aviso", "error": "error"}


def _print_doctor_table(console: Console, app_name: str, results: list[CheckResult]) -> None:
    table = Table(title=f"{app_name} · doctor", show_lines=False, header_style="bold")
    table.add_column("Check", style="bold")
    table.add_column("Estado")
    table.add_column("Detalle", overflow="fold")
    table.add_column("Sugerencia", overflow="fold", style="dim")

    for result in results:
        style = _STATUS_STYLE[result.status]
        table.add_row(
            result.name,
            f"[{style}]{_STATUS_LABEL[result.status]}[/{style}]",
            result.detail,
            result.hint or "",
        )
    console.print(table)


@app.command()
def doctor() -> None:
    """Diagnostica las dependencias locales (ffmpeg-full, whisper, almacenamiento…)."""
    settings = get_settings()
    results = run_checks(settings)
    console = Console()
    _print_doctor_table(console, settings.app_name, results)

    errors = sum(result.status == "error" for result in results)
    warnings = sum(result.status == "warn" for result in results)
    console.print(f"{len(results)} checks · {errors} error(es) · {warnings} aviso(s)")

    if has_errors(results):
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Muestra la versión instalada."""
    typer.echo(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()
