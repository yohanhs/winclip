"""Tests de `core/db.py` y `core/models.py`."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db, session_scope
from winclip.core.ids import new_clip_id, new_job_id, new_project_id
from winclip.core.models import Clip, Job, JobEvent, Project, Workspace, utcnow


def _settings(tmp_path: Path) -> Settings:
    storage = tmp_path / "storage"
    return Settings(
        _env_file=None,
        storage_dir=storage,
        database_url=f"sqlite:///{storage / 'winclip.db'}",
    )


def test_init_db_creates_one_default_workspace_idempotently(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = init_db(settings)
    init_db(settings)

    with Session(engine) as session:
        workspaces = session.exec(select(Workspace)).all()
        again = ensure_default_workspace(session)

    assert len(workspaces) == 1
    assert workspaces[0].name == "Default"
    assert again.id == workspaces[0].id


def test_sqlite_pragmas_are_applied(tmp_path: Path) -> None:
    engine = init_db(_settings(tmp_path))

    with engine.connect() as connection:
        journal = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()

    assert str(journal).lower() == "wal"
    assert int(busy) == 5000
    assert int(foreign_keys) == 1


def test_project_clip_job_relations_and_foreign_keys(tmp_path: Path) -> None:
    engine = init_db(_settings(tmp_path))
    project_id = new_project_id()
    with Session(engine) as session:
        workspace = ensure_default_workspace(session)
        session.add(
            Project(
                id=project_id,
                workspace_id=workspace.id,
                source_type="url",
                source_url="https://example.com/v",
                title="Demo",
            )
        )
        session.commit()

        clip = Clip(
            id=new_clip_id(),
            project_id=project_id,
            candidate={"id": "cand-1"},
            title="Clip 1",
            hashtags=["#shorts"],
            score=80,
            start_sec=1.0,
            end_sec=30.0,
            duration=29.0,
        )
        job = Job(id=new_job_id(), project_id=project_id, type="pipeline")
        event = JobEvent(
            project_id=project_id, job_id=job.id, event_type="job.progress", payload={}
        )
        session.add_all([clip, job, event])
        session.commit()

        assert (
            session.exec(select(Clip).where(Clip.project_id == project_id)).one().title == "Clip 1"
        )
        assert (
            session.exec(select(Job).where(Job.project_id == project_id)).one().type == "pipeline"
        )
        assert session.exec(select(JobEvent).where(JobEvent.project_id == project_id)).one().id

        orphan = Clip(id=new_clip_id(), project_id="no-existe", candidate={}, title="x")
        session.add(orphan)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_job_defaults_and_aware_timestamps(tmp_path: Path) -> None:
    engine = init_db(_settings(tmp_path))
    job_id = new_job_id()
    with Session(engine) as session:
        session.add(Job(id=job_id, type="ingest"))
        session.commit()
        job = session.get(Job, job_id)

    assert job is not None
    assert job.status == "queued"
    assert job.progress == 0
    assert job.attempts == 0
    assert job.max_attempts == 3
    assert job.cancel_requested is False
    assert job.heavy_active is False
    assert job.created_at.tzinfo is not None
    assert job.created_at <= utcnow()


def test_session_scope_commits_and_rolls_back(tmp_path: Path) -> None:
    engine = init_db(_settings(tmp_path))
    project_id = new_project_id()
    with Session(engine) as session:
        workspace_id = ensure_default_workspace(session).id

    with session_scope(engine) as session:
        session.add(Project(id=project_id, workspace_id=workspace_id, title="ok"))

    with pytest.raises(RuntimeError), session_scope(engine) as session:
        session.add(Project(id=new_project_id(), workspace_id=workspace_id, title="rollback"))
        raise RuntimeError("boom")

    with Session(engine) as session:
        titles = [project.title for project in session.exec(select(Project)).all()]
    assert titles == ["ok"]

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM project")).scalar() == 1
