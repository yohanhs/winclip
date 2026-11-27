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
from winclip.core.models import Campaign, Clip, Job, Project, Publication, SocialAccount, utcnow
from winclip.core.storage import LocalStorage
from winclip.pipeline.ingest import extract_audio, probe_media
from winclip.pipeline.ingest import ingest as run_ingest
from winclip.pipeline.render import apply_campaign_to_render_options, render_clip
from winclip.pipeline.render_models import RenderOptions, RenderProgress
from winclip.pipeline.schemas import SourceMeta
from winclip.pipeline.select import ClipCandidate, SelectionError, select_clips
from winclip.pipeline.transcribe import transcribe as run_transcribe
from winclip.publishers.base import (
    DailyLimitExceededError,
    MissedScheduleWindowError,
    PermanentPublishError,
    PublishError,
    PublishMeta,
    PublishValidationError,
)
from winclip.publishers.quota import count_today_publications, daily_limit_for_account
from winclip.publishers.registry import get_publisher
from winclip.rules.schema import CampaignRules
from winclip.worker import queue

PUBLISH_BACKOFF_SCHEDULE = (30.0, 120.0, 600.0)

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


def _project_campaign(engine: Engine, project: Project) -> tuple[str | None, CampaignRules | None]:
    if not project.campaign_id:
        return None, None
    with Session(engine) as session:
        campaign = session.get(Campaign, project.campaign_id)
    if campaign is None:
        return None, None
    return campaign.id, CampaignRules.model_validate(campaign.rules_json)


def _run_select_stage(ctx: JobContext, project: Project, backends: PipelineBackends) -> None:
    ctx.check_cancel()
    requested: int | str = project.requested_clips or "max"
    campaign_id, campaign_rules = _project_campaign(ctx.engine, project)
    if campaign_rules is not None:
        result = backends.select(
            project.id,
            settings=ctx.settings,
            count=requested,
            rules=campaign_rules,
            campaign_id=campaign_id,
        )
    else:
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


def _render_options(
    project: Project,
    *,
    force: bool,
    clip: Clip | None = None,
    campaign_rules: CampaignRules | None = None,
    storage: LocalStorage | None = None,
) -> RenderOptions:
    """Resuelve opciones en cascada: clip.render_overrides > campaign.rules > project > defaults."""
    overrides = dict((clip.render_overrides if clip is not None else None) or {})
    word_overrides = dict((clip.subtitle_overrides if clip is not None else None) or {})

    clip_preset = overrides.get("subtitle_preset")
    preset = (
        str(clip_preset)
        if clip_preset
        else (
            campaign_rules.subtitle_preset
            if campaign_rules is not None and campaign_rules.subtitle_preset
            else (project.subtitle_preset or "bold-yellow")
        )
    )

    raw_mode = overrides.get("reframe_mode") or project.reframe_mode or "face"
    mode = raw_mode if raw_mode != "passthrough" else "center"

    crop_x_pct = float(overrides["crop_x_pct"]) if overrides.get("crop_x_pct") is not None else 50.0
    crop_y_pct = float(overrides["crop_y_pct"]) if overrides.get("crop_y_pct") is not None else 50.0
    zoom_pct = float(overrides["zoom_pct"]) if overrides.get("zoom_pct") is not None else 100.0

    base = RenderOptions(
        preset=preset,
        reframe=mode,  # type: ignore[arg-type]
        engine="ass",
        crop_x_pct=crop_x_pct,
        crop_y_pct=crop_y_pct,
        zoom_pct=zoom_pct,
        word_overrides=word_overrides,
        hook_overlay=True,
        force=force,
    )
    if campaign_rules is not None and storage is not None:
        return apply_campaign_to_render_options(
            base,
            campaign_rules,
            storage=storage,
            preset_overridden=True,
        )
    return base


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

    _, campaign_rules = _project_campaign(ctx.engine, project)
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

            target_options = _render_options(
                project,
                force=True,
                clip=target,
                campaign_rules=campaign_rules,
                storage=ctx.storage,
            )

            base = start_progress + span * index / len(targets)
            share = span / len(targets)

            def on_progress(progress: RenderProgress, base=base, share=share) -> None:
                ctx.progress(base + share * progress.percent / 100.0, "render")

            manifest = backends.render(
                project.id,
                candidate_id,
                target_options,
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


def _emit_publication_event(
    engine: Engine,
    pub: Publication,
    *,
    project_id: str | None,
    progress: float | None = None,
    stage: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "publication_id": pub.id,
        "clip_id": pub.clip_id,
        "account_id": pub.account_id,
        "project_id": project_id,
        "job_id": pub.job_id,
        "status": pub.status,
        "delivery_mode": pub.delivery_mode,
        "external_id": pub.external_id,
        "external_url": pub.external_url,
        "error": pub.error,
        "error_code": pub.error_code,
        "warnings": list(pub.warnings_json or []),
        "has_screenshot": bool(pub.screenshot_path),
    }
    if progress is not None:
        payload["progress"] = progress
    if stage is not None:
        payload["stage"] = stage
    queue.emit_event(
        engine,
        event_type="publication.updated",
        project_id=project_id,
        job_id=pub.job_id,
        payload=payload,
    )


def _publish_backoff(attempts: int) -> float:
    idx = max(0, min(len(PUBLISH_BACKOFF_SCHEDULE) - 1, attempts - 1))
    return PUBLISH_BACKOFF_SCHEDULE[idx]


def handle_publish(ctx: JobContext, _project: Project | None, _backends: PipelineBackends) -> None:
    """Ejecuta un trabajo `publish` para un registro `Publication`."""
    publication_id = str(ctx.job.payload.get("publication_id") or "").strip()
    if not publication_id:
        raise PublishValidationError("El trabajo publish necesita payload.publication_id")

    with Session(ctx.engine) as session:
        pub = session.get(Publication, publication_id)
        if pub is None:
            raise PublishValidationError(f"No existe la publicación {publication_id}")
        if pub.status == "cancelled":
            raise JobCancelled("publicación cancelada por el usuario")

        clip = session.get(Clip, pub.clip_id)
        if clip is None:
            raise PublishValidationError(f"No existe el clip {pub.clip_id}")
        account = session.get(SocialAccount, pub.account_id)
        if account is None:
            raise PublishValidationError(f"No existe la cuenta {pub.account_id}")

        project_id = clip.project_id

        # Ventana de programación perdida (solo para jobs diferidos con run_at)
        if ctx.job.run_at is not None:
            run_at = ctx.job.run_at
            now = utcnow()
            now_cmp = now.replace(tzinfo=None) if run_at.tzinfo is None else now
            late_seconds = (now_cmp - run_at).total_seconds()
            if late_seconds > ctx.settings.publish_missed_schedule_window_seconds:
                raise MissedScheduleWindowError(
                    "Se superó la ventana de programación diferida mientras WinClip estuvo "
                    "apagado. Reintenta o reprograma la publicación manualmente."
                )

        # Límite diario por cuenta (omitir si se autorizó `force` o si ya tiene `external_id`)
        force_limit = bool(ctx.job.payload.get("force_daily_limit"))
        if not force_limit and not pub.external_id:
            used_today = count_today_publications(
                session, account.id, exclude_publication_id=pub.id
            )
            limit = daily_limit_for_account(account, ctx.settings)
            if used_today >= limit:
                raise DailyLimitExceededError(
                    f"La cuenta {account.display_name or account.handle} alcanzó su límite diario "
                    f"({used_today}/{limit})."
                )

        pub.status = "publishing"
        pub.attempts = int(pub.attempts or 0) + 1
        pub.error = None
        pub.error_code = None
        pub.updated_at = utcnow()
        session.add(pub)
        session.commit()
        session.refresh(pub)
        _emit_publication_event(ctx.engine, pub, project_id=project_id, progress=5.0, stage="start")

        meta_dict = dict(pub.meta_json or {})
        meta = PublishMeta.model_validate(meta_dict)
        meta.publication_id = pub.id
        meta.existing_external_id = pub.external_id
        meta.existing_external_url = pub.external_url
        if pub.scheduled_at is not None:
            meta.scheduled_at = pub.scheduled_at

        def on_progress(percent: float, stage: str) -> None:
            ctx.progress(percent, stage)
            _emit_publication_event(
                ctx.engine, pub, project_id=project_id, progress=percent, stage=stage
            )

        publisher = get_publisher(
            account,
            settings=ctx.settings,
            session=session,
            on_progress=on_progress,
        )
        result = publisher.publish(clip, account, meta)

        pub.status = result.status
        pub.delivery_mode = result.delivery_mode
        if result.external_id:
            pub.external_id = result.external_id
        if result.external_url:
            pub.external_url = result.external_url
        pub.warnings_json = list(result.warnings)
        if result.screenshot_path:
            pub.screenshot_path = result.screenshot_path
        if result.status == "published":
            pub.published_at = utcnow()
        pub.error = None
        pub.error_code = None
        pub.updated_at = utcnow()
        session.add(pub)
        session.commit()
        session.refresh(pub)
        _emit_publication_event(
            ctx.engine, pub, project_id=project_id, progress=100.0, stage="done"
        )


def _handle_publish_error(
    engine: Engine,
    job: Job,
    exc: Exception,
) -> Job:
    """Persiste el estado de fallo o reintento en `Publication` y en la cola `Job`."""
    publication_id = str(job.payload.get("publication_id") or "").strip()
    is_publish_err = isinstance(exc, PublishError)
    retryable = bool(exc.retryable) if is_publish_err else False
    err_code = exc.code if is_publish_err else "publish_error"
    err_msg = str(exc) or type(exc).__name__
    will_retry = retryable and job.attempts < job.max_attempts

    if publication_id:
        with Session(engine) as session:
            pub = session.get(Publication, publication_id)
            if pub is not None:
                if is_publish_err and exc.external_id:
                    pub.external_id = exc.external_id
                if is_publish_err and exc.external_url:
                    pub.external_url = exc.external_url
                if is_publish_err and exc.screenshot_path:
                    pub.screenshot_path = exc.screenshot_path
                pub.error = err_msg[:2000]
                pub.error_code = err_code
                pub.status = "scheduled" if will_retry else "failed"
                pub.updated_at = utcnow()
                session.add(pub)

                if err_code == "session_expired":
                    account = session.get(SocialAccount, pub.account_id)
                    if account is not None:
                        account.status = "expired"
                        account.last_error = err_msg[:500]
                        account.updated_at = utcnow()
                        session.add(account)

                clip = session.get(Clip, pub.clip_id)
                project_id = clip.project_id if clip is not None else job.project_id
                session.commit()
                session.refresh(pub)
                _emit_publication_event(
                    engine, pub, project_id=project_id, stage="retry" if will_retry else "failed"
                )

    return queue.fail_job(
        engine,
        job.id,
        err_msg,
        retryable=retryable,
        backoff_override_seconds=_publish_backoff(job.attempts) if will_retry else None,
    )


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
            handle_publish(ctx, None, backends)
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
    except PublishError as exc:
        if job.type == "publish":
            return _handle_publish_error(engine, job, exc)
        return queue.fail_job(engine, job_id, str(exc), retryable=exc.retryable)
    except Exception as exc:
        if job.type == "publish":
            return _handle_publish_error(
                engine,
                job,
                PermanentPublishError(f"{type(exc).__name__}: {exc}"),
            )
        return queue.fail_job(engine, job_id, f"{type(exc).__name__}: {exc}", retryable=True)
