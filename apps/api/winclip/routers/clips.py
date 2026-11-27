"""`/api/clips`: edición, borrado, re-render y entrega de media con soporte Range."""

from __future__ import annotations

import contextlib
import re
import shutil
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session

from winclip.core.models import Campaign, Clip, Project, utcnow
from winclip.core.storage import LocalStorage, StoragePathError
from winclip.routers.deps import EngineDep, SessionDep, SettingsDep
from winclip.routers.schemas import ClipOut, ClipUpdate, JobOut
from winclip.routers.serializers import clip_out
from winclip.rules.schema import CampaignRules, RuleViolation
from winclip.rules.validator import validate_candidate
from winclip.worker import queue

router = APIRouter(prefix="/api/clips", tags=["clips"])

RANGE_CHUNK_BYTES = 256 * 1024
RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


def _clip_or_404(session: Session, clip_id: str) -> Clip:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no existe el clip {clip_id}")
    return clip


def _media_path(storage: LocalStorage, relative: str | None) -> Path:
    if not relative:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "el clip no tiene archivo en disco")
    try:
        path = storage.resolve_safe(relative)
    except StoragePathError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ruta de archivo no permitida") from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "el archivo del clip no existe")
    return path


def _parse_range(header: str, size: int) -> tuple[int, int]:
    match = RANGE_PATTERN.fullmatch(header.strip())
    if match is None:
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE,
            "cabecera Range inválida",
            headers={"Content-Range": f"bytes */{size}"},
        )
    raw_start, raw_end = match.groups()
    if not raw_start and not raw_end:
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE,
            "cabecera Range inválida",
            headers={"Content-Range": f"bytes */{size}"},
        )
    if not raw_start:
        suffix = int(raw_end)
        if suffix <= 0:
            raise HTTPException(
                status.HTTP_416_RANGE_NOT_SATISFIABLE,
                "cabecera Range inválida",
                headers={"Content-Range": f"bytes */{size}"},
            )
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(raw_start)
        end = int(raw_end) if raw_end else size - 1
    if size == 0 or start >= size or start > end:
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE,
            "rango fuera del archivo",
            headers={"Content-Range": f"bytes */{size}"},
        )
    return start, min(end, size - 1)


def _iter_file(path: Path, start: int, length: int) -> Iterator[bytes]:
    remaining = length
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(RANGE_CHUNK_BYTES, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _file_response(
    request: Request, path: Path, *, media_type: str, cache_control: str
) -> Response:
    size = path.stat().st_size
    range_header = request.headers.get("range")
    headers = {"Accept-Ranges": "bytes", "Cache-Control": cache_control}
    if range_header:
        start, end = _parse_range(range_header, size)
        length = end - start + 1
        headers.update(
            {
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Content-Length": str(length),
            }
        )
        return StreamingResponse(
            _iter_file(path, start, length),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=media_type,
            headers=headers,
        )
    headers["Content-Length"] = str(size)
    return StreamingResponse(
        _iter_file(path, 0, size),
        status_code=status.HTTP_200_OK,
        media_type=media_type,
        headers=headers,
    )


def _normalize_hashtags(values: list[str]) -> list[str]:
    tags: list[str] = []
    for raw in values:
        tag = " ".join(str(raw).split())
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag}"
        tag = "#" + tag[1:].replace("#", "").replace(" ", "")
        if tag == "#" or tag in tags:
            continue
        tags.append(tag)
    return tags


@router.get(
    "/{clip_id}/file",
    response_class=StreamingResponse,
    operation_id="getClipFile",
    responses={206: {"description": "Contenido parcial"}, 416: {"description": "Rango inválido"}},
)
def get_clip_file(
    clip_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Entrega el MP4 con `Accept-Ranges` y `206` si llega `Range`."""
    clip = _clip_or_404(session, clip_id)
    path = _media_path(LocalStorage(settings.storage_dir), clip.path)
    return _file_response(request, path, media_type="video/mp4", cache_control="no-cache")


@router.get(
    "/{clip_id}/thumb",
    response_class=StreamingResponse,
    operation_id="getClipThumb",
    responses={206: {"description": "Contenido parcial"}, 416: {"description": "Rango inválido"}},
)
def get_clip_thumb(
    clip_id: str,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Entrega la miniatura JPEG con caché y soporte Range."""
    clip = _clip_or_404(session, clip_id)
    path = _media_path(LocalStorage(settings.storage_dir), clip.thumb_path)
    return _file_response(
        request,
        path,
        media_type="image/jpeg",
        cache_control="public, max-age=3600",
    )


@router.patch("/{clip_id}", response_model=ClipOut, operation_id="updateClip")
def update_clip(clip_id: str, payload: ClipUpdate, session: SessionDep) -> ClipOut:
    """Actualiza metadatos y tiempos (validando `0 <= start < end`)."""
    clip = _clip_or_404(session, clip_id)
    changes = payload.model_dump(exclude_unset=True)

    start = float(changes.get("start_sec", clip.start_sec))
    end = float(changes.get("end_sec", clip.end_sec))
    if start < 0 or end <= start:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "los tiempos deben cumplir 0 <= start_sec < end_sec",
        )

    if "title" in changes and changes["title"] is not None:
        clip.title = changes["title"]
    if "description" in changes and changes["description"] is not None:
        clip.description = changes["description"]
    if "hashtags" in changes and changes["hashtags"] is not None:
        clip.hashtags = _normalize_hashtags(changes["hashtags"])
    clip.start_sec = round(start, 3)
    clip.end_sec = round(end, 3)
    clip.duration = round(end - start, 3)

    candidate = dict(clip.candidate or {})
    candidate.update(
        {
            "start": clip.start_sec,
            "end": clip.end_sec,
            "title": clip.title,
            "description": clip.description,
            "hashtags": list(clip.hashtags),
        }
    )
    project = session.get(Project, clip.project_id)
    if project is not None and project.campaign_id:
        campaign = session.get(Campaign, project.campaign_id)
        if campaign is not None:
            rules = CampaignRules.model_validate(campaign.rules_json)
            existing_semantic = [
                RuleViolation.model_validate(item)
                for item in (candidate.get("rule_violations") or [])
                if isinstance(item, dict) and item.get("code") == "banned_topic_risk"
            ]
            violations = validate_candidate(
                start=clip.start_sec,
                end=clip.end_sec,
                rules=rules,
                title=clip.title,
                hook=clip.hook,
                description=clip.description,
                hashtags=clip.hashtags,
                existing_violations=existing_semantic,
            )
            candidate["rule_violations"] = [v.model_dump(mode="json") for v in violations]
    clip.candidate = candidate
    clip.updated_at = utcnow()
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return clip_out(clip)


@router.delete("/{clip_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="deleteClip")
def delete_clip(clip_id: str, session: SessionDep, settings: SettingsDep):
    """Borra el clip, su carpeta de render y deja intactos los demás."""
    clip = _clip_or_404(session, clip_id)
    storage = LocalStorage(settings.storage_dir)
    if clip.path:
        with contextlib.suppress(StoragePathError):
            shutil.rmtree(storage.resolve_safe(clip.path).parent, ignore_errors=True)
    session.delete(clip)
    session.commit()
    return None


@router.post(
    "/{clip_id}/rerender",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="rerenderClip",
)
def rerender_clip(
    clip_id: str,
    session: SessionDep,
    engine: EngineDep,
    settings: SettingsDep,
) -> JobOut:
    """Encola un trabajo `render` con los tiempos y metadatos actuales del clip."""
    clip = _clip_or_404(session, clip_id)
    project = session.get(Project, clip.project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "el proyecto del clip no existe")

    job = queue.enqueue(
        engine,
        job_type="render",
        project_id=clip.project_id,
        payload={"clip_id": clip.id},
        max_attempts=settings.job_max_attempts,
    )
    clip.status = "rendering"
    clip.updated_at = utcnow()
    session.add(clip)
    session.commit()
    return JobOut.model_validate(job)
