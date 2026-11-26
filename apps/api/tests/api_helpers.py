"""Utilidades para sembrar proyectos y clips en los tests de la API."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import Engine
from sqlmodel import Session

from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_clip_id, new_project_id
from winclip.core.models import Clip, Project
from winclip.core.storage import LocalStorage


def seed_project(
    engine: Engine,
    *,
    storage: LocalStorage | None = None,
    title: str = "Demo",
    reframe_mode: str = "face",
    subtitle_preset: str = "bold-yellow",
    requested_clips: int | None = 2,
    source_url: str = "https://example.com/video",
) -> SimpleNamespace:
    project_id = new_project_id()
    with Session(engine) as session:
        workspace = ensure_default_workspace(session)
        session.add(
            Project(
                id=project_id,
                workspace_id=workspace.id,
                source_type="url",
                source_url=source_url,
                title=title,
                requested_clips=requested_clips,
                reframe_mode=reframe_mode,
                subtitle_preset=subtitle_preset,
            )
        )
        session.commit()
    if storage is not None:
        storage.ensure_project_dirs(project_id)
    return SimpleNamespace(id=project_id, title=title)


def seed_clip(
    engine: Engine,
    storage: LocalStorage,
    project_id: str,
    *,
    title: str = "Clip",
    clip_id: str | None = None,
    data: bytes = b"\x00\x00\x00\x18ftypmp42" + b"0" * 4096,
    with_files: bool = True,
    path_override: str | None = None,
    thumb_override: str | None = None,
    score: int = 80,
    start: float = 1.0,
    end: float = 31.0,
) -> SimpleNamespace:
    clip_id = clip_id or new_clip_id()
    clip_path = f"projects/{project_id}/clips/{clip_id}/clip.mp4"
    thumb_path = f"projects/{project_id}/clips/{clip_id}/thumb.jpg"
    if with_files:
        directory = storage.clip_dir(project_id, clip_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "clip.mp4").write_bytes(data)
        (directory / "thumb.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"1" * 256)
    with Session(engine) as session:
        session.add(
            Clip(
                id=clip_id,
                project_id=project_id,
                candidate={"id": f"cand-{clip_id}", "start": start, "end": end},
                status="rendered" if with_files else "draft",
                title=title,
                description="desc",
                hashtags=["#shorts"],
                score=score,
                hook="hook",
                start_sec=start,
                end_sec=end,
                duration=end - start,
                path=path_override
                if path_override is not None
                else (clip_path if with_files else None),
                thumb_path=(
                    thumb_override
                    if thumb_override is not None
                    else (thumb_path if with_files else None)
                ),
            )
        )
        session.commit()
    return SimpleNamespace(id=clip_id, directory=storage.clip_dir(project_id, clip_id))
