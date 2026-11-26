"""Handlers de los tipos de trabajo: `ingest`, `transcribe`, `select`, `render`, `pipeline`.

El pipeline completo es un único trabajo (design, decisión 3) que adquiere el bloqueo
pesado solo en las fases que usan GPU/MLX/ffmpeg, comprueba la cancelación entre etapas y
persiste los clips en cada fase.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from winclip.core.config import Settings
from winclip.core.ids import new_clip_id
from winclip.core.models import Clip, Job, Project, utcnow
from winclip.core.storage import LocalStorage
from winclip.pipeline.ingest import extract_audio, probe_media
from winclip.pipeline.ingest import ingest as run_ingest
from winclip.pipeline.render import render_clip
from winclip.pipeline.render_models import RenderOptions, RenderProgress
from winclip.pipeline.schemas import SourceMeta
from winclip.pipeline.select import ClipCandidate, SelectionError, select_clips
from winclip.pipeline.transcribe import transcribe as run_transcribe
from winclip.worker import queue

PIPELINE_STAGES = ("ingest", "transcribe", "select", "render")
HEAVY_STAGES = frozenset({"transcribe", "render"})
INGEST_PROGRESS_END = 25.0
TRANSCRIBE_PROGRESS_END = 60.0
SELECT_PROGRESS_END = 70.0
HEAVY_POLL_SECONDS = 0.25
RESERVED_PUBLISH_MESSAGE = (
    "el tipo de trabajo 'publish' está reservado para una fase posterior "
    "(change add-publishers); no hay publicadores habilitados todavía"
)


class HandlerError(RuntimeError):
    """Fallo de un handler con mensaje apto para el usuario."""


class JobCancelled(HandlerError):
    """El trabajo fue cancelado en un punto seguro."""


class ReservedJobTypeError(HandlerError):
    """Tipo de trabajo reservado a un change futuro: falla sin reintentos."""


@dataclass
class PipelineBackends:
    """Funciones del pipeline inyectables (mocks en tests, reales en producción)."""

    ingest: Callable[..., Any] = run_ingest
    transcribe: Callable[..., Any] = run_transcribe
    select: Callable[..., Any] = select_clips
    render: Callable[..., Any] = render_clip
    poll_seconds: float = HEAVY_POLL_SECONDS


@dataclass
class JobContext:
    """Estado compartido por las etapas de un trabajo."""

    engine: Engine
    job: Job
    settings: Settings
    storage: LocalStorage
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def check_cancel(self) -> None:
        if self.cancel_event.is_set() or queue.is_cancel_requested(self.engine, self.job.id):
            raise JobCancelled("trabajo cancelado por el usuario")

    def progress(self, percent: float, stage: str) -> None:
        self.check_cancel()
        if stage != self.job.stage:
            self.job.stage = stage
        queue.update_progress(self.engine, self.job.id, progress=percent, stage=stage)

    def acquire_heavy(self, backends: PipelineBackends) -> None:
        """Espera a que no haya otro trabajo pesado y toma el bloqueo."""
        while not queue.acquire_heavy(self.engine, self.job.id):
            self.check_cancel()
            time.sleep(backends.poll_seconds)
        self.job.heavy_active = True

    def release_heavy(self) -> None:
        queue.release_heavy(self.engine, self.job.id)
        self.job.heavy_active = False


def _project(engine: Engine, project_id: str | None) -> Project:
    if project_id is None:
        raise HandlerError("el trabajo no tiene proyecto asociado")
    with Session(engine) as session:
        project = session.get(Project, project_id)
    if project is None:
        raise HandlerError(f"no existe el proyecto {project_id}")
    return project


def _save_project(engine: Engine, project: Project, **values: Any) -> Project:
    with Session(engine) as session:
        stored = session.get(Project, project.id)
        if stored is None:
            raise HandlerError(f"no existe el proyecto {project.id}")
        for key, value in values.items():
            setattr(stored, key, value)
        stored.updated_at = utcnow()
        session.add(stored)
        session.commit()
        session.refresh(stored)
        return stored


def _relative(storage: LocalStorage, path: Path) -> str:
    return path.resolve().relative_to(storage.root).as_posix()


def _ingest_uploaded(ctx: JobContext, project: Project) -> None:
    """Proyecto subido por la API: ya está en `source/`; solo meta + audio."""
    storage = ctx.storage
    source_path = project.source_path
    if not source_path:
        raise HandlerError(f"el proyecto {project.id} no tiene archivo fuente subido")
    video_path = storage.resolve_safe(source_path)
    if not video_path.is_file():
        raise HandlerError(f"no existe el archivo fuente {source_path}")

    probe = probe_media(video_path, ctx.settings)
    ctx.progress(15.0, "probe")
    if not probe.has_audio:
        raise HandlerError(f"el video {video_path.name} no contiene audio para transcribir")
    extract_audio(video_path, storage.audio_path(project.id), ctx.settings)
    ctx.progress(INGEST_PROGRESS_END, "extract_audio")

    meta = SourceMeta(
        project_id=project.id,
        source_type="file",
        source_url=project.source_url,
        original_filename=video_path.name,
        title=project.title or video_path.stem,
        channel=None,
        uploader_id=None,
        duration=probe.duration,
        width=probe.width,
        height=probe.height,
        fps=probe.fps,
        video_codec=probe.video_codec,
        audio_codec=probe.audio_codec,
        audio_sample_rate=probe.audio_sample_rate,
        has_audio=probe.has_audio,
        file_size_bytes=video_path.stat().st_size,
    )
    storage.write_json_atomic(storage.source_meta_path(project.id), meta)
    _save_project(
        ctx.engine,
        project,
        duration=probe.duration,
        source_path=_relative(storage, video_path),
        status="processing",
    )


def _run_ingest_stage(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    ctx.progress(0.0, "ingest")
    if ctx.storage.source_meta_path(project.id).is_file():
        ctx.progress(INGEST_PROGRESS_END, "ingest")
        return
    if project.source_url:
        result = backends.ingest(
            project.source_url,
            settings=ctx.settings,
            project_id=project.id,
            force=True,
            progress=lambda value, stage: ctx.progress(
                value * INGEST_PROGRESS_END / 100.0, "ingest"
            ),
        )
        _save_project(
            ctx.engine,
            project,
            duration=result.meta.duration,
            source_path=_relative(ctx.storage, result.video_path),
            status="processing",
        )
    else:
        _ingest_uploaded(ctx, project)
    ctx.progress(INGEST_PROGRESS_END, "ingest")


def _run_transcribe_stage(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    ctx.check_cancel()
    ctx.acquire_heavy(backends)
    try:
        backends.transcribe(
            project.id,
            settings=ctx.settings,
            language=project.language or "auto",
            progress=lambda value, stage: ctx.progress(
                INGEST_PROGRESS_END
                + (TRANSCRIBE_PROGRESS_END - INGEST_PROGRESS_END) * value / 100.0,
                stage if stage in {"load_model", "transcribe"} else "transcribe",
            ),
        )
    finally:
        ctx.release_heavy()
    ctx.progress(TRANSCRIBE_PROGRESS_END, "transcribe")


def _run_select_stage(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    ctx.check_cancel()
    requested: int | str = project.requested_clips or "max"
    result = backends.select(project.id, settings=ctx.settings, count=requested)
    _sync_clips(ctx.engine, project.id, result.document.candidates)
    ctx.progress(SELECT_PROGRESS_END, "select")


def _sync_clips(engine: Engine, project_id: str, candidates: list[ClipCandidate]) -> list[Clip]:
    """Crea o actualiza una fila `clip` por candidato, conservando ids existentes."""
    now = utcnow()
    with Session(engine) as session:
        existing = session.exec(select(Clip).where(Clip.project_id == project_id)).all()
        by_candidate = {
            str((clip.candidate or {}).get("id")): clip for clip in existing if clip.candidate
        }
        saved: list[Clip] = []
        for candidate in candidates:
            clip = by_candidate.get(candidate.id)
            if clip is None:
                clip = Clip(id=new_clip_id(), project_id=project_id, status="draft")
            clip.candidate = candidate.model_dump(mode="json")
            clip.title = candidate.title
            clip.description = candidate.description
            clip.hashtags = list(candidate.hashtags)
            clip.score = candidate.score
            clip.hook = candidate.hook
            clip.start_sec = candidate.start
            clip.end_sec = candidate.end
            clip.duration = round(candidate.end - candidate.start, 3)
            clip.updated_at = now
            session.add(clip)
            saved.append(clip)
        session.commit()
        for clip in saved:
            session.refresh(clip)
        return saved


def _render_options(project: Project, *, force: bool) -> RenderOptions:
    mode = project.reframe_mode if project.reframe_mode != "passthrough" else "center"
    return RenderOptions(
        preset=project.subtitle_preset,
        reframe=mode,  # type: ignore[arg-type]
        engine="ass",
        hook_overlay=True,
        force=force,
    )


def _clip_for_project(engine: Engine, project_id: str, candidate_id: str) -> Clip | None:
    with Session(engine) as session:
        clips = session.exec(select(Clip).where(Clip.project_id == project_id)).all()
    for clip in clips:
        if str((clip.candidate or {}).get("id")) == candidate_id:
            return clip
    return None


def _sync_candidate_times(ctx: JobContext, project_id: str, clip: Clip) -> None:
    """Reescribe `candidates.json` con los tiempos editados del clip antes de re-renderizar."""
    path = ctx.storage.selection_path(project_id)
    if not path.is_file() or not clip.candidate:
        return
    payload = ctx.storage.read_json(path)
    candidates = payload.get("candidates") or []
    candidate_id = str(clip.candidate.get("id"))
    for item in candidates:
        if str(item.get("id")) != candidate_id:
            continue
        item.update(
            {
                "start": clip.start_sec,
                "end": clip.end_sec,
                "title": clip.title,
                "hook": clip.hook,
                "description": clip.description,
                "hashtags": list(clip.hashtags),
                "score": clip.score,
            }
        )
    payload["candidates"] = candidates
    ctx.storage.write_json_atomic(path, payload)


def _apply_render(
    ctx: JobContext,
    project: Project,
    clip: Clip,
    manifest: Any,
) -> Clip:
    """Guarda rutas del clip renderizado y emite `clip.ready`."""
    storage = ctx.storage
    video = storage.clip_video_path(project.id, manifest.clip_id)
    thumb = storage.clip_thumb_path(project.id, manifest.clip_id)
    with Session(ctx.engine) as session:
        stored = session.get(Clip, clip.id)
        if stored is None:
            raise HandlerError(f"no existe el clip {clip.id}")
        stored.status = "rendered"
        stored.path = _relative(storage, video)
        stored.thumb_path = _relative(storage, thumb)
        stored.duration = manifest.duration
        stored.updated_at = utcnow()
        session.add(stored)
        queue.record_event(
            session,
            event_type="clip.ready",
            project_id=project.id,
            job_id=ctx.job.id,
            payload={
                "project_id": project.id,
                "job_id": ctx.job.id,
                "clip_id": stored.id,
                "status": "rendered",
                "thumb_url": f"/api/clips/{stored.id}/thumb",
                "video_url": f"/api/clips/{stored.id}/file",
            },
        )
        session.commit()
        session.refresh(stored)
        return stored


def _run_render_stage(
    ctx: JobContext,
    project: Project,
    backends: PipelineBackends,
    *,
    clip: Clip | None = None,
) -> list[Clip]:
    ctx.check_cancel()
    with Session(ctx.engine) as session:
        clips = session.exec(
            select(Clip).where(Clip.project_id == project.id, Clip.status != "rendered")
        ).all()
    targets = [clip] if clip is not None else clips
    if not targets:
        raise HandlerError("el proyecto no tiene clips que renderizar")

    options = _render_options(project, force=True)
    start_progress = SELECT_PROGRESS_END if clip is None else 0.0
    span = 100.0 - start_progress
    rendered: list[Clip] = []

    ctx.acquire_heavy(backends)
    try:
        for index, target in enumerate(targets):
            ctx.check_cancel()
            candidate_id = str((target.candidate or {}).get("id") or "")
            if not candidate_id:
                raise HandlerError(f"el clip {target.id} no tiene candidato asociado")
            if clip is not None:
                _sync_candidate_times(ctx, project.id, target)

            base = start_progress + span * index / len(targets)
            share = span / len(targets)

            def on_progress(progress: RenderProgress, base=base, share=share) -> None:
                ctx.progress(base + share * progress.percent / 100.0, "render")

            manifest = backends.render(
                project.id,
                candidate_id,
                options,
                settings=ctx.settings,
                on_progress=on_progress,
                clip_id=target.id,
            )
            rendered.append(_apply_render(ctx, project, target, manifest))
            ctx.progress(base + share, "render")
    finally:
        ctx.release_heavy()
    return rendered


def handle_pipeline(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    _save_project(ctx.engine, project, status="processing")
    _run_ingest_stage(ctx, project, backends)
    _run_transcribe_stage(ctx, project, backends)
    _run_select_stage(ctx, project, backends)
    _run_render_stage(ctx, project, backends)
    _save_project(ctx.engine, project, status="ready")


def handle_ingest(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    _run_ingest_stage(ctx, project, backends)
    _save_project(ctx.engine, project, status="ready")


def handle_transcribe(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    _run_transcribe_stage(ctx, project, backends)


def handle_select(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    _run_select_stage(ctx, project, backends)


def handle_render(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    clip_id = ctx.job.payload.get("clip_id")
    if not clip_id:
        raise HandlerError("el trabajo render necesita payload.clip_id")
    with Session(ctx.engine) as session:
        clip = session.get(Clip, str(clip_id))
    if clip is None or clip.project_id != project.id:
        raise HandlerError(f"no existe el clip {clip_id} en el proyecto {project.id}")
    _run_render_stage(ctx, project, backends, clip=clip)
    _save_project(ctx.engine, project, status="ready")


HANDLERS: dict[str, Callable[[JobContext, Project, PipelineBackends], None]] = {
    "ingest": handle_ingest,
    "transcribe": handle_transcribe,
    "select": handle_select,
    "render": handle_render,
    "pipeline": handle_pipeline,
}


def handle_publish(_ctx: JobContext, _project: Project, _backends: PipelineBackends) -> None:
    raise ReservedJobTypeError(RESERVED_PUBLISH_MESSAGE)


def handle_job(
    engine: Engine,
    job_id: str,
    *,
    settings: Settings,
    backends: PipelineBackends | None = None,
    cancel_event: threading.Event | None = None,
) -> Job:
    """Ejecuta un trabajo reclamado y deja su estado final en la cola."""
    backends = backends or PipelineBackends()
    with Session(engine) as session:
        job = session.get(Job, job_id)
    if job is None:
        raise HandlerError(f"no existe el trabajo {job_id}")

    ctx = JobContext(
        engine=engine,
        job=job,
        settings=settings,
        storage=LocalStorage(settings.storage_dir),
        cancel_event=cancel_event or threading.Event(),
    )
    try:
        if job.type == "publish":
            handle_publish(ctx, _project(engine, job.project_id), backends)
            return queue.complete_job(engine, job_id)
        project = _project(engine, job.project_id)
        handler = HANDLERS.get(job.type)
        if handler is None:
            raise ReservedJobTypeError(f"tipo de trabajo desconocido: {job.type}")
        handler(ctx, project, backends)
        return queue.complete_job(engine, job_id)
    except JobCancelled:
        return queue.mark_cancelled(engine, job_id)
    except (ReservedJobTypeError, SelectionError) as exc:
        return queue.fail_job(engine, job_id, str(exc), retryable=False)
    except Exception as exc:
        return queue.fail_job(engine, job_id, f"{type(exc).__name__}: {exc}", retryable=True)
