"""Tests de modelo `Publication`, migración `0004` y cola diferida `run_at` (`task 1.3`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session

from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db
from winclip.core.ids import new_clip_id, new_project_id, new_publication_id, new_ulid
from winclip.core.models import Clip, Project, Publication, SocialAccount
from winclip.worker import queue


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(storage_dir=tmp_path / "storage")


def test_migration_0004_creates_publication_and_job_run_at(tmp_path: Path) -> None:
    engine = init_db(_make_settings(tmp_path))

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        proj = Project(id=new_project_id(), workspace_id=ws.id, title="Video", status="ready")
        clip = Clip(id=new_clip_id(), project_id=proj.id, title="Clip 1", status="rendered")
        acc = SocialAccount(
            id=new_ulid(),
            workspace_id=ws.id,
            platform="youtube",
            auth_method="api",
            display_name="Canal",
            handle="@canal",
            status="connected",
        )
        session.add(proj)
        session.flush()
        session.add(clip)
        session.add(acc)
        session.commit()

        pub = Publication(
            id=new_publication_id(),
            workspace_id=ws.id,
            clip_id=clip.id,
            account_id=acc.id,
            status="scheduled",
            delivery_mode="direct",
            meta_json={"title": "Clip 1"},
            warnings_json=["aviso"],
        )
        session.add(pub)
        session.commit()

        loaded = session.get(Publication, pub.id)
        assert loaded is not None
        assert loaded.status == "scheduled"
        assert loaded.delivery_mode == "direct"
        assert loaded.meta_json == {"title": "Clip 1"}
        assert loaded.warnings_json == ["aviso"]


def test_queue_respects_run_at_and_cancel_does_not_mutate_project(tmp_path: Path) -> None:
    engine = init_db(_make_settings(tmp_path))

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        proj = Project(id=new_project_id(), workspace_id=ws.id, title="Listo", status="ready")
        session.add(proj)
        session.commit()
        project_id = proj.id

    future = datetime.now(UTC) + timedelta(hours=2)
    future_job = queue.enqueue(
        engine,
        job_type="publish",
        project_id=project_id,
        payload={"publication_id": "pub-future"},
        run_at=future,
    )
    assert future_job.run_at is not None

    # No debe reclamarse antes de `run_at`.
    claimed = queue.claim_next(engine, worker_id="w1", light_running=0, light_limit=2)
    assert claimed is None

    # Cancelar job programado no debe alterar el estado `ready` del proyecto.
    cancelled = queue.cancel_job(engine, future_job.id)
    assert cancelled.status == "cancelled"
    with Session(engine) as session:
        proj_after = session.get(Project, project_id)
        assert proj_after is not None
        assert proj_after.status == "ready"

    # Un job con `run_at` en el pasado sí se reclama inmediatamente.
    past = datetime.now(UTC) - timedelta(seconds=5)
    due_job = queue.enqueue(
        engine,
        job_type="publish",
        project_id=project_id,
        payload={"publication_id": "pub-due"},
        run_at=past,
    )
    claimed_due = queue.claim_next(engine, worker_id="w1", light_running=0, light_limit=2)
    assert claimed_due is not None
    assert claimed_due.id == due_job.id

    # Fallar definitivamente un job `publish` tampoco debe marcar el proyecto como `failed`.
    failed = queue.fail_job(engine, due_job.id, "cuota agotada", retryable=False)
    assert failed.status == "failed"
    with Session(engine) as session:
        proj_final = session.get(Project, project_id)
        assert proj_final is not None
        assert proj_final.status == "ready"
