"""CLI de WinClip (`winclip …`)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.table import Table

from winclip import __version__
from winclip.core.config import get_settings
from winclip.core.doctor import CheckResult, has_errors, run_checks
from winclip.core.ids import InvalidProjectIdError
from winclip.core.storage import StoragePathError
from winclip.llm.router import LLMRouter
from winclip.llm.types import LLMError, ProviderAttempt
from winclip.pipeline.ingest import IngestError
from winclip.pipeline.ingest import ingest as run_ingest
from winclip.pipeline.select import SelectionError, select_clips
from winclip.pipeline.transcribe import (
    SUPPORTED_LANGUAGES,
    TranscriptionError,
)
from winclip.pipeline.transcribe import transcribe as run_transcribe
from winclip.rules.schema import RulesFileError

app = typer.Typer(
    name="winclip",
    help="WinClip: clipping local de vídeos largos a shorts verticales.",
    no_args_is_help=True,
    add_completion=False,
)

llm_app = typer.Typer(
    help="Proveedores LLM gratuitos y prueba de conectividad del router.",
    no_args_is_help=True,
)
app.add_typer(llm_app, name="llm")

_STATUS_STYLE = {"ok": "green", "warn": "yellow", "error": "red"}
_STATUS_LABEL = {"ok": "ok", "warn": "aviso", "error": "error"}
_STAGE_LABELS = {
    "download": "descargando",
    "copy": "copiando",
    "probe": "inspeccionando",
    "extract_audio": "extrayendo audio",
    "load_model": "cargando modelo",
    "transcribe": "transcribiendo",
    "save": "guardando",
}
_ATTEMPT_STYLE = {
    "ok": ("ok", "green"),
    "skipped": ("omitido", "yellow"),
    "error": ("error", "red"),
}


class _LLMPing(BaseModel):
    """Esquema mínimo para comprobar que el proveedor devuelve el JSON pedido."""

    ok: bool
    message: str


def _build_llm_router() -> LLMRouter:
    """Router real (los tests lo sustituyen por uno con proveedores falsos)."""
    return LLMRouter(get_settings())


def _progress_bar() -> Progress:
    return Progress(
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
    )


def _print_attempts(console: Console, attempts: list[ProviderAttempt]) -> None:
    table = Table(title="Intentos LLM", header_style="bold")
    table.add_column("Proveedor", style="bold")
    table.add_column("Modelo")
    table.add_column("Estado")
    table.add_column("Latencia")
    table.add_column("Detalle", overflow="fold", style="dim")
    for attempt in attempts:
        label, style = _ATTEMPT_STYLE[attempt.status]
        table.add_row(
            attempt.provider,
            attempt.model or "—",
            f"[{style}]{label}[/{style}]",
            f"{attempt.latency_ms} ms",
            attempt.error or "",
        )
    console.print(table)


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


@app.command("ingest")
def ingest_command(
    source: Annotated[str, typer.Argument(help="URL del video o ruta de un archivo local")],
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Identificador del proyecto (por defecto, un ULID)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Reingesta aunque el proyecto ya exista"),
    ] = False,
) -> None:
    """Descarga o copia un video, extrae metadatos y audio mono 16 kHz."""
    settings = get_settings()
    console = Console()
    progress_ui = _progress_bar()
    try:
        with progress_ui:
            task_id = progress_ui.add_task("preparando", total=100)

            def on_progress(value: float, stage: str) -> None:
                progress_ui.update(
                    task_id,
                    completed=min(100.0, max(0.0, value)),
                    description=_STAGE_LABELS.get(stage, stage),
                )

            result = run_ingest(
                source,
                settings=settings,
                project_id=project_id,
                force=force,
                progress=on_progress,
            )
    except (IngestError, InvalidProjectIdError, StoragePathError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]proyecto:[/green] {result.project_id}")
    console.print(f"video: {result.video_path}")
    console.print(f"audio: {result.audio_path}")
    meta = result.meta
    resolution = f"{meta.width}x{meta.height}" if meta.width and meta.height else "desconocida"
    console.print(f"duración: {meta.duration:.1f} s · {resolution} · {meta.video_codec or '?'}")


@app.command("transcribe")
def transcribe_command(
    project_id: Annotated[str, typer.Argument(help="Identificador del proyecto ingestado")],
    language: Annotated[
        str,
        typer.Option("--language", help="Idioma del audio: es, en o auto"),
    ] = "auto",
    model: Annotated[
        str | None,
        typer.Option("--model", help="Modelo de Whisper o el atajo 'tiny'"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Recalcula aunque ya exista transcript.json"),
    ] = False,
) -> None:
    """Transcribe el audio del proyecto con timestamps por palabra."""
    settings = get_settings()
    console = Console()
    if language.strip().lower() not in SUPPORTED_LANGUAGES:
        console.print(
            f"[red]error:[/red] idioma no soportado: {language}; valores válidos: es, en, auto"
        )
        raise typer.Exit(code=1)

    progress_ui = _progress_bar()
    try:
        with progress_ui:
            task_id = progress_ui.add_task("preparando", total=100)

            def on_progress(value: float, stage: str) -> None:
                progress_ui.update(
                    task_id,
                    completed=min(100.0, max(0.0, value)),
                    description=_STAGE_LABELS.get(stage, stage),
                )

            result = run_transcribe(
                project_id,
                settings=settings,
                language=language,
                model=model,
                force=force,
                progress=on_progress,
            )
    except (TranscriptionError, InvalidProjectIdError, StoragePathError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if result.reused:
        console.print("[yellow]reutilizando transcripción previa[/yellow]")
    console.print(f"[green]transcripción:[/green] {result.path}")
    console.print(
        f"idioma: {result.transcript.language} · modelo: {result.transcript.model} · "
        f"segmentos: {len(result.transcript.segments)}"
    )


@llm_app.command("test")
def llm_test_command() -> None:
    """Comprueba la conectividad LLM pidiendo un JSON mínimo al router."""
    console = Console()
    try:
        result = _build_llm_router().complete_json(
            "Responde siempre con un objeto JSON válido y sin texto adicional.",
            'Devuelve exactamente un objeto JSON con "ok": true y "message": "pong".',
            _LLMPing,
            logical_model="llm-test:v1",
            use_cache=False,
        )
    except LLMError as exc:
        console.print(f"[red]error:[/red] {exc}")
        attempts = getattr(exc, "attempts", None)
        if attempts:
            _print_attempts(console, attempts)
        raise typer.Exit(code=1) from exc

    console.print(f"[green]proveedor:[/green] {result.provider} · modelo: {result.model}")
    console.print(f"respuesta: {result.data.message}")
    console.print(
        f"tokens aprox.: {result.prompt_tokens} entrada · {result.completion_tokens} salida"
    )
    _print_attempts(console, result.attempts)


@app.command("select")
def select_command(
    project_id: Annotated[str, typer.Argument(help="Identificador del proyecto transcrito")],
    count: Annotated[
        str,
        typer.Option("--count", help="Número de clips (entero >= 1) o 'max'"),
    ] = "10",
    rules: Annotated[
        str | None,
        typer.Option("--rules", help="Archivo JSON de reglas de campaña (§6.4)"),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Ignora la caché local de respuestas LLM"),
    ] = False,
) -> None:
    """Selecciona clips con el router LLM y escribe selection/candidates.json."""
    console = Console()
    try:
        result = select_clips(
            project_id,
            count=count,
            rules_path=Path(rules) if rules else None,
            use_cache=not no_cache,
            router_factory=_build_llm_router,
        )
    except (
        SelectionError,
        RulesFileError,
        InvalidProjectIdError,
        StoragePathError,
        LLMError,
    ) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]selección:[/green] {result.path}")
    console.print(f"proveedor: {result.provider} · chunks: {result.chunks}")
    if result.cached:
        console.print("[yellow]respuesta desde caché[/yellow]")

    candidates = result.document.candidates
    if not candidates:
        console.print("[yellow]sin candidatos válidos con los filtros aplicados[/yellow]")
        return

    table = Table(title="Candidatos", header_style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Inicio", justify="right")
    table.add_column("Duración", justify="right")
    table.add_column("Título", overflow="fold")
    for candidate in candidates:
        table.add_row(
            str(candidate.score),
            f"{candidate.start:.1f}s",
            f"{candidate.end - candidate.start:.1f}s",
            candidate.title,
        )
    console.print(table)


@app.command()
def version() -> None:
    """Muestra la versión instalada."""
    typer.echo(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()
