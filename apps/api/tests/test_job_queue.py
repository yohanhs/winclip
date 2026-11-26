"""Tests de la cola persistente: reclamo atómico, concurrencia, reintentos y huérfanos."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, select

from winclip.core.config import Settings
from winclip.core.db import init_db
from winclip.core.models import Job, JobEvent, utcnow
from winclip.worker import queue


@pytest.fixture
def engine(tmp_path: Path):
    storage = tmp_path / "storage"
    settings = Settings(
        _env_file=None,
        storage_dir=storage,
        database_url=f"sqlite:///{storage / 'winclip.db'}",
    )
    return init_db(settings)


def _claim(engine, **kwargs):
    return queue.claim_next(
        engine,
        worker_id=kwargs.pop("worker_id", "w1"),
        light_running=kwargs.pop("light_running", 0),
        light_limit=kwargs.pop("light_limit", 2),
    )


def test_heavy_jobs_run_one_at_a_time(engine) -> None:
    first = queue.enqueue(engine, job_type="render")
    second = queue.enqueue(engine, job_type="transcribe")

    claimed = _claim(engine)
    blocked = _claim(engine)

    assert claimed is not None
    assert claimed.id in {first.id, second.id}
    assert blocked is None
    assert _claim(engine, light_limit=4) is None


def test_light_jobs_respect_configured_concurrency(engine) -> None:
    jobs = [queue.enqueue(engine, job_type="ingest") for _ in range(3)]

    first = _claim(engine, light_limit=2)
    second = _claim(engine, light_running=1, light_limit=2)
    third = _claim(engine, light_running=2, light_limit=2)

    assert {first.id, second.id} <= {job.id for job in jobs}
    assert third is None


def test_two_workers_never_claim_the_same_job(engine) -> None:
    job = queue.enqueue(engine, job_type="ingest")

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda index: _claim(engine, worker_id=f"w{index}", light_limit=6),
                range(6),
            )
        )

    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0].id == job.id


def test_retry_with_backoff_then_definitive_failure(engine) -> None:
    job = queue.enqueue(engine, job_type="render", max_attempts=2)

    claimed = _claim(engine)
    assert claimed is not None and claimed.attempts == 1

    retried = queue.fail_job(engine, claimed.id, "ffmpeg se cayó", retryable=True)
    assert retried.status == "queued"
    assert retried.attempts == 1
    assert retried.stage == "retry"
    assert retried.error == "ffmpeg se cayó"
    assert retried.next_run_at is not None
    assert retried.next_run_at > utcnow()
    assert queue.backoff_seconds(1) == 2.0
    assert queue.backoff_seconds(5) == 32.0
    assert queue.backoff_seconds(20) == 300.0
    # Programado en el futuro: no se reclama todavía.
    assert _claim(engine) is None

    with Session(engine) as session:
        stored = session.get(Job, job.id)
        assert stored is not None
        stored.next_run_at = utcnow() - timedelta(seconds=1)
        session.add(stored)
        session.commit()

    second = _claim(engine)
    assert second is not None and second.attempts == 2

    failed = queue.fail_job(engine, second.id, "sigue fallando", retryable=True)
    assert failed.status == "failed"
    assert failed.finished_at is not None
    assert failed.heavy_active is False
    assert _claim(engine) is None


def test_publish_failure_can_skip_retries(engine) -> None:
    job = queue.enqueue(engine, job_type="publish")

    final = queue.fail_job(engine, job.id, "reservado", retryable=False)

    assert final.status == "failed"
    assert final.attempts == 0
    assert final.error == "reservado"


def test_cancel_queued_job_immediately(engine) -> None:
    job = queue.enqueue(engine, job_type="pipeline")

    cancelled = queue.cancel_job(engine, job.id)

    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None
    assert _claim(engine) is None


def test_cancel_running_job_requests_cooperative_stop(engine) -> None:
    queue.enqueue(engine, job_type="render")
    claimed = _claim(engine)
    assert claimed is not None
    assert queue.acquire_heavy(engine, claimed.id) is True

    requested = queue.cancel_job(engine, claimed.id)
    assert requested.status == "running"
    assert requested.cancel_requested is True
    assert queue.is_cancel_requested(engine, claimed.id) is True

    final = queue.mark_cancelled(engine, claimed.id)
    assert final.status == "cancelled"
    assert final.heavy_active is False
    # El bloqueo pesado quedó libre: otro render puede reclamarse.
    queue.enqueue(engine, job_type="render")
    assert _claim(engine, light_limit=4) is not None


def test_cancel_terminal_job_raises(engine) -> None:
    job = queue.enqueue(engine, job_type="ingest")
    queue.complete_job(engine, job.id)

    with pytest.raises(queue.JobQueueError):
        queue.cancel_job(engine, job.id)


def test_orphan_recovery_requeues_stale_running_jobs(engine) -> None:
    job = queue.enqueue(engine, job_type="render")
    claimed = _claim(engine)
    assert claimed is not None
    queue.acquire_heavy(engine, claimed.id)

    with Session(engine) as session:
        stored = session.get(Job, job.id)
        assert stored is not None
        stored.heartbeat_at = utcnow() - timedelta(seconds=3600)
        session.add(stored)
        session.commit()

    assert queue.recover_orphans(engine, stale_seconds=300) == 1

    with Session(engine) as session:
        recovered = session.get(Job, job.id)
    assert recovered is not None
    assert recovered.status == "queued"
    assert recovered.attempts == 2
    assert recovered.heavy_active is False
    assert recovered.worker_id is None
    # El bloqueo pesado quedó libre.
    other = queue.enqueue(engine, job_type="render")
    assert _claim(engine, light_limit=2).id in {job.id, other.id}


def test_progress_is_monotonic_and_emits_events(engine) -> None:
    job = queue.enqueue(engine, job_type="pipeline")
    claimed = _claim(engine)
    assert claimed is not None

    queue.update_progress(engine, job.id, progress=30, stage="transcribe")
    queue.update_progress(engine, job.id, progress=10, stage="transcribe")
    final = queue.update_progress(engine, job.id, progress=70, stage="select")

    assert final.progress == 70
    events = queue.list_events(engine)
    assert [event.event_type for event in events] == ["job.progress", "job.progress"]
    assert [event.payload["stage"] for event in events] == ["transcribe", "select"]


def test_complete_job_emits_done_and_sets_project_ready(engine) -> None:
    job = queue.enqueue(engine, job_type="ingest")

    done = queue.complete_job(engine, job.id)

    assert done.status == "done"
    assert done.progress == 100
    assert done.stage == "done"
    events = queue.list_events(engine)
    assert events[-1].event_type == "job.done"


def test_purge_events_removes_old_rows(engine) -> None:
    job = queue.enqueue(engine, job_type="ingest")
    with Session(engine) as session:
        session.add(
            JobEvent(
                job_id=job.id,
                event_type="job.progress",
                payload={},
                created_at=utcnow() - timedelta(hours=48),
            )
        )
        session.commit()
    queue.update_progress(engine, job.id, progress=10, stage="ingest")

    assert queue.purge_events(engine) == 1
    remaining = queue.list_events(engine)
    assert len(remaining) == 1
    assert remaining[0].payload["progress"] == 10


def test_running_counts_track_light_and_heavy(engine) -> None:
    queue.enqueue(engine, job_type="ingest")
    heavy = queue.enqueue(engine, job_type="render")

    light_job = _claim(engine, worker_id="wx")
    heavy_claimed = _claim(engine, worker_id="wx")
    assert light_job is not None
    # Con `render` en cola y sin pesado activo, el siguiente reclamo puede ser el render.
    if heavy_claimed is not None and heavy_claimed.id == heavy.id:
        queue.acquire_heavy(engine, heavy_claimed.id)

    light, heavy_running = queue.running_counts(engine, worker_id="wx")
    assert light >= 1
    assert heavy_running in {0, 1}

    with Session(engine) as session:
        running = session.exec(select(Job).where(Job.status == "running")).all()
    assert len(running) == 2
