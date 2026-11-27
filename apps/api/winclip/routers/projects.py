"""`/api/projects`: creación (URL o subida streaming), listado, detalle y borrado."""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import delete
from sqlmodel import Session, select

from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_project_id
from winclip.core.models import Campaign, Clip, Job, JobEvent, Project, utcnow
from winclip.core.storage import LocalStorage, StoragePathError
from winclip.pipeline.subtitles.presets import SubtitlePresetError, load_preset
from winclip.routers.deps import EngineDep, SessionDep, SettingsDep
from winclip.routers.schemas import ClipOut, JobOut, ProjectCreate, ProjectCreated, ProjectOut
from winclip.routers.serializers import clip_out, project_out
from winclip.rules.schema import CampaignRules
from winclip.services.uploads import UploadError, stream_multipart
from winclip.worker import queue

router = APIRouter(prefix="/api/projects", tags=["projects"])

_OPENAPI_CREATE = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["source_url"],
                    "properties": {
                        "source_type": {"type": "string", "enum": ["url"]},
                        "source_url": {"type": "string", "format": "uri"},
                        "title": {"type": "string", "maxLength": 500},
                        "requested_clips": {
                            "oneOf": [{"type": "integer", "minimum": 1}, {"enum": ["max"]}]
                        },
                        "language": {"type": "string", "enum": ["auto", "es", "en"]},
                        "campaign_id": {"type": "string"},
                        "subtitle_preset": {"type": "string"},
                        "reframe_mode": {
                            "type": "string",
                            "enum": ["face", "center", "blur", "passthrough"],
                        },
                    },
                }
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "source_type": {"type": "string", "enum": ["file", "url"]},
                        "source_url": {"type": "string", "format": "uri"},
                        "title": {"type": "string", "maxLength": 500},
                        "requested_clips": {
                            "oneOf": [{"type": "integer", "minimum": 1}, {"enum": ["max"]}]
                        },
                        "language": {"type": "string", "enum": ["auto", "es", "en"]},
                        "campaign_id": {"type": "string"},
                        "subtitle_preset": {"type": "string"},
                        "reframe_mode": {
                            "type": "string",
                            "enum": ["face", "center", "blur", "passthrough"],
                        },
                    },
                }
            },
        },
    }
}


def _relative(storage: LocalStorage, path: Path) -> str:
    return path.resolve().relative_to(storage.root).as_posix()


def _validate_preset(name: str) -> str:
    try:
        load_preset(name)
    except SubtitlePresetError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return name


def _validation_detail(exc: ValidationError) -> list[dict[str, Any]]:
    """Errores de Pydantic serializables a JSON."""
    return exc.errors(include_url=False, include_context=False, include_input=False)


def _parse_requested(value: Any) -> int | str:
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if text == "max":
        return "max"
    try:
        return int(text)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "requested_clips debe ser un entero >= 1 o 'max'",
        ) from exc


def _parse_multipart_fields(fields: dict[str, str]) -> ProjectCreate:
    payload: dict[str, Any] = {}
    keys = (
        "source_url",
        "title",
        "campaign_id",
        "subtitle_preset",
        "reframe_mode",
        "language",
    )
    for key in keys:
        value = fields.get(key, "").strip()
        if value:
            payload[key] = value
    if "requested_clips" in fields:
        payload["requested_clips"] = _parse_requested(fields["requested_clips"])
    payload.setdefault("source_type", "file")
    if payload.get("source_type") == "file":
        payload.pop("source_url", None)
    elif not payload.get("source_url"):
        payload.pop("source_type")
        payload["source_type"] = "url"
    try:
        return ProjectCreate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _validation_detail(exc)) from exc


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"URL inválida: {url!r}; usa http(s)://…",
        )
    return url


@router.post(
    "",
    response_model=ProjectCreated,
    status_code=status.HTTP_201_CREATED,
    operation_id="createProject",
    openapi_extra=_OPENAPI_CREATE,
)
async def create_project(
    request: Request,
    session: SessionDep,
    engine: EngineDep,
    settings: SettingsDep,
) -> ProjectCreated:
    """Crea un proyecto desde una URL (JSON) o un archivo (multipart streaming)."""
    storage = LocalStorage(settings.storage_dir)
    content_type = (request.headers.get("content-type") or "").lower()
    project_id = new_project_id()
    project_dir = storage.project_dir(project_id)
    file_path: Path | None = None
    filename: str | None = None

    if content_type.startswith("multipart/form-data"):
        storage.ensure_project_dirs(project_id)
        try:
            upload = await stream_multipart(
                request,
                directory=storage.source_dir(project_id),
                max_bytes=settings.upload_max_bytes,
            )
        except UploadError as exc:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(exc.status_code, str(exc)) from exc
        except Exception:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise
        if upload.file_path is None:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "el formulario multipart necesita un archivo de video en el campo 'file'",
            )
        payload = _parse_multipart_fields(upload.fields)
        file_path = upload.file_path
        filename = upload.filename
    else:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "cuerpo JSON inválido"
            ) from exc
        try:
            payload = ProjectCreate.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, _validation_detail(exc)
            ) from exc

    if payload.source_type == "url" and not payload.source_url:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "source_url es obligatoria para crear un proyecto desde una URL",
        )
    if payload.source_url:
        _validate_url(payload.source_url)

    campaign: Campaign | None = None
    campaign_rules: CampaignRules | None = None
    if payload.campaign_id:
        campaign = session.get(Campaign, payload.campaign_id)
        if campaign is None:
            if file_path is not None:
                shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"no existe la campaña {payload.campaign_id}",
            )
        campaign_rules = CampaignRules.model_validate(campaign.rules_json)

    requested_clips = payload.requested_clips
    language = payload.language
    subtitle_preset_raw = payload.subtitle_preset
    if campaign_rules is not None:
        if "requested_clips" not in payload.model_fields_set and campaign_rules.max_clips:
            requested_clips = campaign_rules.max_clips
        if "language" not in payload.model_fields_set and campaign_rules.language:
            language = campaign_rules.language
        if "subtitle_preset" not in payload.model_fields_set and campaign_rules.subtitle_preset:
            subtitle_preset_raw = campaign_rules.subtitle_preset

    preset = _validate_preset(subtitle_preset_raw)

    title = (payload.title or "").strip()
    if not title:
        title = Path(filename).stem if filename else (payload.source_url or "Proyecto")

    workspace = ensure_default_workspace(session)
    project = Project(
        id=project_id,
        workspace_id=workspace.id,
        campaign_id=campaign.id if campaign is not None else None,
        source_type=payload.source_type,
        source_url=payload.source_url,
        title=title,
        status="queued",
        requested_clips=(requested_clips if isinstance(requested_clips, int) else None),
        language=language,
        subtitle_preset=preset,
        reframe_mode=payload.reframe_mode,
        source_path=_relative(storage, file_path) if file_path is not None else None,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    job = queue.enqueue(
        engine,
        job_type="pipeline",
        project_id=project.id,
        payload={
            "requested_clips": requested_clips,
            "language": language,
            "subtitle_preset": preset,
            "reframe_mode": payload.reframe_mode,
            "campaign_id": project.campaign_id,
        },
        max_attempts=settings.job_max_attempts,
    )

    with Session(engine) as fresh:
        stored_project = fresh.get(Project, project.id)
        assert stored_project is not None
        stored_jobs = list(
            fresh.exec(
                select(Job).where(Job.project_id == project.id).order_by(Job.created_at)
            ).all()
        )
        result = project_out(fresh, stored_project, jobs=stored_jobs)
    return ProjectCreated(project=result, job=JobOut.model_validate(job))


@router.get("", response_model=list[ProjectOut], operation_id="listProjects")
def list_projects(session: SessionDep) -> list[ProjectOut]:
    """Proyectos del más reciente al más antiguo con resumen de clips y trabajos."""
    projects = session.exec(
        select(Project).order_by(Project.created_at.desc(), Project.id.desc())
    ).all()
    return [project_out(session, project) for project in projects]


@router.get("/{project_id}", response_model=ProjectOut, operation_id="getProject")
def get_project(project_id: str, session: SessionDep) -> ProjectOut:
    """Detalle de un proyecto con sus clips y trabajos."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no existe el proyecto {project_id}")
    return project_out(session, project)


@router.get(
    "/{project_id}/clips",
    response_model=list[ClipOut],
    operation_id="listProjectClips",
)
def list_project_clips(project_id: str, session: SessionDep) -> list[ClipOut]:
    """Clips del proyecto ordenados por `score` descendente."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no existe el proyecto {project_id}")
    clips = session.exec(
        select(Clip)
        .where(Clip.project_id == project_id)
        .order_by(Clip.score.desc(), Clip.start_sec)
    ).all()
    return [clip_out(clip) for clip in clips]


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteProject",
)
def delete_project(
    project_id: str,
    session: SessionDep,
    engine: EngineDep,
    settings: SettingsDep,
):
    """Cancela trabajos activos y borra el proyecto, sus filas y su carpeta."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no existe el proyecto {project_id}")

    active = session.exec(
        select(Job).where(Job.project_id == project_id, Job.status.in_(("queued", "running")))
    ).all()
    for job in active:
        try:
            queue.cancel_job(engine, job.id)
        except queue.JobQueueError:
            continue

    session.execute(delete(JobEvent).where(JobEvent.project_id == project_id))
    session.execute(delete(Job).where(Job.project_id == project_id))
    session.execute(delete(Clip).where(Clip.project_id == project_id))
    session.execute(delete(Project).where(Project.id == project_id))
    session.commit()

    storage = LocalStorage(settings.storage_dir)
    with contextlib.suppress(StoragePathError):
        shutil.rmtree(storage.project_dir(project_id), ignore_errors=True)
    return None
