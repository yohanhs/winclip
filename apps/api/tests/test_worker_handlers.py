"""Tests de los handlers del worker con el pipeline completamente mockeado."""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_pipeline import FakePipeline, clip_dir_has_media, write_candidates
from sqlmodel import Session, select

from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db
from winclip.core.ids import new_clip_id, new_project_id
from winclip.core.models import Clip, Job, JobEvent, Project, utcnow
from winclip.core.storage import LocalStorage
from winclip.worker import queue
from winclip.worker.handlers import handle_job


@pytest.fixture
def env(tmp_path: Path):
    storage_dir = tmp_path / "storage"
    settings = Settings(
        _env_file=None,
        storage_dir=storage_dir,
        database_url=f"sqlite:///{storage_dir / 'winclip.db'}",
    )
    engine = init_db(settings)
    return settings, engine, LocalStorage(storage_dir)


def _project(engine, *, source_url: str | None = "https://example.com/video") -> Project:
    with Session(engine) as session:
        workspace = ensure_default_workspace(session)
        project = Project(
            id=new_project_id(),
            workspace_id=workspace.id,
            source_type="url" if source_url else "file",
            source_url=source_url,
            title="Demo",
            status="queued",
            requested_clips=2,
            language="es",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        return project


def _claim(engine, job: Job) -> Job:
    claimed = queue.claim_next(engine, worker_id="test", light_running=0, light_limit=4)
    assert claimed is not None and claimed.id == job.id
    return claimed


def test_pipeline_runs_all_stages_and_creates_rendered_clips(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    pipeline = FakePipeline(storage=storage)
    job = queue.enqueue(engine, job_type="pipeline", project_id=project.id, max_attempts=2)
    _claim(engine, job)

    final = handle_job(engine, job.id, settings=settings, backends=pipeline.backends())

    assert final.status == "done"
    assert final.progress == 100
    assert final.stage == "done"
    assert pipeline.calls[0] == "ingest"
    assert pipeline.calls[1] == "transcribe"
    assert pipeline.calls[2] == "select"
    assert sum(call.startswith("render:") for call in pipeline.calls) == 2

    with Session(engine) as session:
        clips = session.exec(select(Clip).where(Clip.project_id == project.id)).all()
        project_row = session.get(Project, project.id)
    assert len(clips) == 2
    assert all(clip.status == "rendered" for clip in clips)
    assert all(clip.path and clip.thumb_path for clip in clips)
    for clip in clips:
        assert storage.resolve_safe(clip.path or "").is_file()
        assert storage.resolve_safe(clip.thumb_path or "").is_file()
    assert project_row is not None and project_row.status == "ready"

    events = queue.list_events(engine)
    types = [event.event_type for event in events]
    assert types.count("clip.ready") == 2
    assert types[-1] == "job.done"
    clip_events = [event for event in events if event.event_type == "clip.ready"]
    assert {event.payload["video_url"] for event in clip_events} == {
        f"/api/clips/{clip.id}/file" for clip in clips
    }

    stages = [event.payload.get("stage") for event in events if event.event_type == "job.progress"]
    assert {"ingest", "transcribe", "select", "render"} <= {stage for stage in stages if stage}
    progresses = [
        event.payload["progress"] for event in events if event.event_type == "job.progress"
    ]
    assert progresses == sorted(progresses)


def test_pipeline_cancellation_stops_before_next_stage(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    job = queue.enqueue(engine, job_type="pipeline", project_id=project.id)
    _claim(engine, job)

    pipeline = FakePipeline(
        storage=storage,
        after_transcribe=lambda: queue.cancel_job(engine, job.id),
    )

    final = handle_job(engine, job.id, settings=settings, backends=pipeline.backends())

    assert final.status == "cancelled"
    assert final.heavy_active is False
    assert "select" not in pipeline.calls
    with Session(engine) as session:
        assert session.exec(select(Clip).where(Clip.project_id == project.id)).all() == []


def test_publish_fails_without_retries(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    job = queue.enqueue(engine, job_type="publish", project_id=project.id, max_attempts=3)
    _claim(engine, job)

    final = handle_job(engine, job.id, settings=settings, backends=FakePipeline(storage).backends())

    assert final.status == "failed"
    assert final.error is not None and "reservado" in final.error
    assert final.finished_at is not None
    assert final.next_run_at is None


def test_transient_failure_requeues_with_backoff(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    job = queue.enqueue(engine, job_type="pipeline", project_id=project.id, max_attempts=2)
    _claim(engine, job)

    pipeline = FakePipeline(storage=storage, fail_transcribe=True)
    retried = handle_job(engine, job.id, settings=settings, backends=pipeline.backends())

    assert retried.status == "queued"
    assert retried.attempts == 1
    assert retried.error is not None and "fallo simulado" in retried.error
    assert retried.next_run_at is not None and retried.next_run_at > utcnow()


def test_failure_without_attempts_left_marks_job_failed(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    job = queue.enqueue(engine, job_type="pipeline", project_id=project.id, max_attempts=1)
    _claim(engine, job)

    pipeline = FakePipeline(storage=storage, fail_transcribe=True)
    final = handle_job(engine, job.id, settings=settings, backends=pipeline.backends())

    assert final.status == "failed"
    with Session(engine) as session:
        project_row = session.get(Project, project.id)
    assert project_row is not None and project_row.status == "failed"
    assert queue.list_events(engine)[-1].event_type == "job.failed"


def test_render_job_uses_edited_clip_times(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    write_candidates(storage, project.id, 1)
    candidate = write_candidates(storage, project.id, 1)[0]

    clip_id = new_clip_id()
    clip = Clip(
        id=clip_id,
        project_id=project.id,
        candidate=candidate.model_dump(mode="json"),
        title="Editado",
        hashtags=["#edicion"],
        score=77,
        hook="Hook",
        start_sec=12.5,
        end_sec=42.25,
        duration=29.75,
    )
    with Session(engine) as session:
        session.add(clip)
        session.commit()

    job = queue.enqueue(
        engine, job_type="render", project_id=project.id, payload={"clip_id": clip_id}
    )
    _claim(engine, job)
    pipeline = FakePipeline(storage=storage, candidate_count=1)

    final = handle_job(engine, job.id, settings=settings, backends=pipeline.backends())

    assert final.status == "done"
    assert pipeline.calls == [f"render:{candidate.id}"]
    document = storage.read_json(storage.selection_path(project.id))
    stored = document["candidates"][0]
    assert stored["start"] == 12.5
    assert stored["end"] == 42.25
    assert stored["title"] == "Editado"

    with Session(engine) as session:
        refreshed = session.get(Clip, clip_id)
    assert refreshed is not None and refreshed.status == "rendered"
    assert refreshed.path is not None
    assert clip_dir_has_media(storage.resolve_safe(refreshed.path).parent)


def test_render_job_requires_clip_payload(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    job = queue.enqueue(engine, job_type="render", project_id=project.id, max_attempts=1)
    _claim(engine, job)

    final = handle_job(engine, job.id, settings=settings, backends=FakePipeline(storage).backends())

    assert final.status == "failed"
    assert final.error is not None and "payload.clip_id" in final.error


def test_ingest_stage_is_skipped_when_meta_exists(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    pipeline = FakePipeline(storage=storage)
    # Primera ejecución crea meta.json.
    first = queue.enqueue(engine, job_type="pipeline", project_id=project.id, max_attempts=1)
    _claim(engine, first)
    handle_job(engine, first.id, settings=settings, backends=pipeline.backends())

    pipeline.calls.clear()
    second = queue.enqueue(engine, job_type="ingest", project_id=project.id, max_attempts=1)
    _claim(engine, second)
    final = handle_job(engine, second.id, settings=settings, backends=pipeline.backends())

    assert final.status == "done"
    assert pipeline.calls == []


def test_job_events_are_persisted_with_project_id(env) -> None:
    settings, engine, storage = env
    project = _project(engine)
    pipeline = FakePipeline(storage=storage)
    job = queue.enqueue(engine, job_type="pipeline", project_id=project.id, max_attempts=1)
    _claim(engine, job)
    handle_job(engine, job.id, settings=settings, backends=pipeline.backends())

    with Session(engine) as session:
        events = session.exec(select(JobEvent).where(JobEvent.project_id == project.id)).all()
    assert events
    assert all(event.project_id == project.id for event in events)
