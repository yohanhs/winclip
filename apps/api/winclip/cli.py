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
from winclip.core.db import init_db
from winclip.core.doctor import CheckResult, has_errors, run_checks
from winclip.core.ids import InvalidProjectIdError
from winclip.core.storage import StoragePathError
from winclip.llm.router import LLMRouter
from winclip.llm.types import LLMError, ProviderAttempt
from winclip.pipeline.ingest import IngestError
from winclip.pipeline.ingest import ingest as run_ingest
from winclip.pipeline.render import RenderError, render_project_clips
from winclip.pipeline.render_models import RenderOptions, RenderProgress
from winclip.pipeline.select import SelectionError, select_clips
from winclip.pipeline.transcribe import (
    SUPPORTED_LANGUAGES,
    TranscriptionError,
)
from winclip.pipeline.transcribe import transcribe as run_transcribe
from winclip.rules.schema import RulesFileError
from winclip.worker.runner import run_worker

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

db_app = typer.Typer(
    help="Migraciones de la base de datos (Alembic).",
    no_args_is_help=True,
)
app.add_typer(db_app, name="db")

accounts_app = typer.Typer(
    help="Gestión de cuentas sociales (YouTube, TikTok, Instagram).",
    no_args_is_help=True,
)
app.add_typer(accounts_app, name="accounts")

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
    "reframe": "reencuadrando",
    "subtitles": "subtitulando",
    "encode": "codificando",
    "thumbnail": "miniatura",
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


@app.command("render")
def render_command(
    project_id: Annotated[str, typer.Argument(help="Identificador del proyecto seleccionado")],
    clip: Annotated[
        str | None,
        typer.Option("--clip", help="Identificador del candidato a renderizar"),
    ] = None,
    all_clips: Annotated[
        bool,
        typer.Option("--all", help="Renderiza todos los candidatos del proyecto"),
    ] = False,
    preset: Annotated[
        str,
        typer.Option("--preset", help="Preset de subtítulos (bold-yellow, hormozi, …)"),
    ] = "bold-yellow",
    reframe: Annotated[
        str,
        typer.Option("--reframe", help="Modo de reencuadre: face, center o blur"),
    ] = "face",
    engine: Annotated[
        str,
        typer.Option("--engine", help="Motor de subtítulos: ass (libass) o pil"),
    ] = "ass",
    font: Annotated[
        str | None,
        typer.Option("--font", help="Fuente a usar (local en USER_FONTS_DIR o OFL)"),
    ] = None,
    crop_x_pct: Annotated[
        float,
        typer.Option("--crop-x-pct", help="Centro horizontal del recorte en modo center (0-100)"),
    ] = 50.0,
    crop_y_pct: Annotated[
        float,
        typer.Option("--crop-y-pct", help="Centro vertical del recorte en modo center (0-100)"),
    ] = 50.0,
    zoom_pct: Annotated[
        float,
        typer.Option("--zoom-pct", help="Zoom del recorte en modo center (100-300)"),
    ] = 100.0,
    hook_overlay: Annotated[
        bool,
        typer.Option("--hook-overlay/--no-hook-overlay", help="Superpone el hook del candidato"),
    ] = True,
    hook_seconds: Annotated[
        float,
        typer.Option("--hook-seconds", help="Segundos que el hook permanece visible"),
    ] = 3.0,
    watermark: Annotated[
        str | None,
        typer.Option("--watermark", help="PNG de marca de agua (esquina superior derecha)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Vuelve a renderizar aunque el clip esté vigente"),
    ] = False,
) -> None:
    """Renderiza clips verticales 9:16 con subtítulos, hook y miniatura."""
    settings = get_settings()
    console = Console()
    try:
        options = RenderOptions(
            preset=preset,
            reframe=reframe,
            engine=engine,
            font=font,
            crop_x_pct=crop_x_pct,
            crop_y_pct=crop_y_pct,
            zoom_pct=zoom_pct,
            hook_overlay=hook_overlay,
            hook_seconds=hook_seconds,
            watermark_path=Path(watermark) if watermark else None,
            force=force,
        )
    except ValueError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    progress_ui = _progress_bar()
    try:
        with progress_ui:
            task_id = progress_ui.add_task("preparando", total=100)

            def on_progress(value: RenderProgress) -> None:
                progress_ui.update(
                    task_id,
                    completed=min(100.0, max(0.0, value.percent)),
                    description=f"{_STAGE_LABELS.get(value.stage, value.stage)}: {value.message}",
                )

            manifests = render_project_clips(
                project_id,
                options=options,
                all_clips=all_clips,
                candidate_ids=[clip] if clip else None,
                settings=settings,
                on_progress=on_progress,
            )
    except (RenderError, InvalidProjectIdError, StoragePathError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Clips renderizados", header_style="bold")
    table.add_column("Clip", style="bold")
    table.add_column("Candidato")
    table.add_column("Duración", justify="right")
    table.add_column("Reencuadre")
    table.add_column("Subtítulos")
    table.add_column("Ruta", overflow="fold")
    clips_dir = settings.storage_dir / "projects" / project_id / "clips"
    for manifest in manifests:
        table.add_row(
            manifest.clip_id,
            manifest.candidate_id,
            f"{manifest.duration:.1f}s",
            manifest.reframe.mode,
            f"{manifest.subtitles.engine} · {manifest.subtitles.preset}",
            str(clips_dir / manifest.clip_id),
        )
    console.print(table)


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Aplica las migraciones pendientes y garantiza el workspace por defecto."""
    settings = get_settings()
    console = Console()
    try:
        init_db(settings)
    except Exception as exc:
        console.print(f"[red]error:[/red] no se pudo migrar la base de datos: {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]base de datos:[/green] {settings.database_url}")
    console.print("migraciones al día (head)")


@app.command("worker")
def worker_command(
    light_concurrency: Annotated[
        int | None,
        typer.Option("--light-concurrency", help="Trabajos ligeros simultáneos"),
    ] = None,
    poll_interval: Annotated[
        float | None,
        typer.Option("--poll-interval", help="Segundos entre sondeos de la cola"),
    ] = None,
) -> None:
    """Procesa la cola de trabajos en un proceso aparte (SIGINT/SIGTERM limpios)."""
    settings = get_settings()
    updates: dict[str, object] = {}
    if light_concurrency is not None:
        updates["worker_light_concurrency"] = light_concurrency
    if poll_interval is not None:
        updates["worker_poll_interval"] = poll_interval
    if updates:
        settings = settings.model_copy(update=updates)

    console = Console()
    engine = init_db(settings)
    console.print(
        f"[green]worker[/green] base de datos: {settings.database_url} · "
        f"ligeros={settings.worker_light_concurrency} · pesados=1 a la vez"
    )
    runner = run_worker(engine, settings)
    console.print(f"worker detenido ({runner.worker_id})")


@app.command()
def version() -> None:
    """Muestra la versión instalada."""
    typer.echo(__version__)


@accounts_app.command("list")
def accounts_list_command() -> None:
    """Lista todas las cuentas sociales conectadas en el workspace."""
    from sqlmodel import Session, select

    from winclip.core.models import SocialAccount

    settings = get_settings()
    engine = init_db(settings)
    console = Console()
    with Session(engine) as session:
        accounts = session.exec(
            select(SocialAccount).order_by(
                SocialAccount.platform,
                SocialAccount.is_default.desc(),
                SocialAccount.created_at.asc(),
            )
        ).all()

    if not accounts:
        console.print("[yellow]No hay cuentas sociales registradas.[/yellow]")
        return

    table = Table(title="Cuentas sociales", header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Plataforma", style="bold")
    table.add_column("Nombre / Alias")
    table.add_column("Handle")
    table.add_column("Método")
    table.add_column("Estado")
    table.add_column("Default")
    for acc in accounts:
        label = f"{acc.display_name} ({acc.alias})" if acc.alias else acc.display_name
        status_color = "green" if acc.status == "connected" else "red"
        table.add_row(
            acc.id,
            acc.platform,
            label,
            acc.handle or "—",
            acc.auth_method,
            f"[{status_color}]{acc.status}[/{status_color}]",
            "★" if acc.is_default else "",
        )
    console.print(table)


@accounts_app.command("check")
def accounts_check_command(
    account_id: Annotated[
        str | None,
        typer.Argument(help="ID de la cuenta a comprobar (si se omite, comprueba todas)"),
    ] = None,
) -> None:
    """Comprueba la salud y refresca tokens de una o todas las cuentas sociales."""
    from sqlmodel import Session, select

    from winclip.accounts.health import check_account
    from winclip.core.models import SocialAccount

    settings = get_settings()
    engine = init_db(settings)
    console = Console()
    with Session(engine) as session:
        if account_id:
            acc = session.get(SocialAccount, account_id)
            if acc is None:
                console.print(f"[red]error:[/red] no existe la cuenta {account_id}")
                raise typer.Exit(code=1)
            targets = [acc]
        else:
            targets = list(session.exec(select(SocialAccount)).all())

        if not targets:
            console.print("[yellow]No hay cuentas registradas para comprobar.[/yellow]")
            return

        has_failure = False
        for acc in targets:
            updated = check_account(session, acc, settings)
            ok = updated.status == "connected"
            if not ok:
                has_failure = True
            color = "green" if ok else "red"
            detail = f" · {updated.last_error}" if updated.last_error else ""
            console.print(
                f"[{color}]{updated.status}[/{color}] {updated.platform} · "
                f"{updated.display_name} ({updated.handle or updated.id}){detail}"
            )

    if has_failure:
        raise typer.Exit(code=1)


@accounts_app.command("import")
def accounts_import_command(
    path: Annotated[str, typer.Argument(help="Archivo JSON o carpeta de tokens locales")],
    platform: Annotated[
        str | None,
        typer.Option("--platform", help="Plataforma esperada: youtube o tiktok"),
    ] = None,
    alias: Annotated[
        str | None,
        typer.Option("--alias", help="Alias opcional para la cuenta importada"),
    ] = None,
    no_check: Annotated[
        bool,
        typer.Option("--no-check", help="Omite la verificación remota tras importar"),
    ] = False,
) -> None:
    """Importa tokens locales existentes en modo solo lectura y los cifra en STORAGE_DIR."""
    from sqlmodel import Session

    from winclip.accounts.importer import TokenImportError, import_local_tokens

    settings = get_settings()
    engine = init_db(settings)
    console = Console()
    with Session(engine) as session:
        try:
            accounts = import_local_tokens(
                session,
                settings,
                path,
                platform=platform,
                alias=alias,
                run_health_check=not no_check,
            )
        except TokenImportError as exc:
            console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    for acc in accounts:
        console.print(
            f"[green]importada:[/green] {acc.platform} · {acc.display_name} "
            f"({acc.handle or acc.id}) · estado={acc.status}"
        )


if __name__ == "__main__":  # pragma: no cover
    app()
