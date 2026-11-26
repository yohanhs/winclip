"""Tests del bucle del worker (`winclip worker`)."""

from __future__ import annotations

import signal
import threading
import time
from datetime import timedelta
from pathlib import Path

from fake_pipeline import FakePipeline
from sqlmodel import Session

from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db
from winclip.core.ids import new_project_id
from winclip.core.models import Job, Project, utcnow
from winclip.core.storage import LocalStorage
from winclip.worker import queue
from winclip.worker.runner import WorkerRunner, signal_handlers


def _env(tmp_path: Path):
    storage_dir = tmp_path / "storage"
    settings = Settings(
        _env_file=None,
        storage_dir=storage_dir,
        database_url=f"sqlite:///{storage_dir / 'winclip.db'}",
        worker_poll_interval=0.05,
        job_stale_seconds=60,
    )
    engine = init_db(settings)
    with Session(engine) as session:
        workspace = ensure_default_workspace(session)
        project = Project(
            id=new_project_id(),
            workspace_id=workspace.id,
            source_type="url",
            source_url="https://example.com/v",
            title="Demo",
            requested_clips=1,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
    return settings, engine, LocalStorage(storage_dir), project


def _wait_status(engine, job_id: str, expected: str, timeout: float = 10.0) -> Job:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with Session(engine) as session:
            job = session.get(Job, job_id)
        if job is not None and job.status == expected:
            return job
        time.sleep(0.05)
    raise AssertionError(f"el trabajo {job_id} no llegó a {expected}")


def test_runner_processes_queued_job_and_stops_cleanly(tmp_path: Path) -> None:
    settings, engine, storage, project = _env(tmp_path)
    job = queue.enqueue(engine, job_type="pipeline", project_id=project.id, max_attempts=1)
    runner = WorkerRunner(
        engine, settings, backends=FakePipeline(storage, candidate_count=1).backends()
    )
    stop = threading.Event()
    thread = threading.Thread(target=runner.run, args=(stop,), daemon=True)

    thread.start()
    try:
        final = _wait_status(engine, job.id, "done")
        assert final.progress == 100
    finally:
        stop.set()
        thread.join(timeout=10)

    assert not thread.is_alive()


def test_runner_recovers_orphans_on_start(tmp_path: Path) -> None:
    settings, engine, storage, project = _env(tmp_path)
    job = queue.enqueue(engine, job_type="pipeline", project_id=project.id, max_attempts=3)
    claimed = queue.claim_next(engine, worker_id="muerto", light_running=0, light_limit=2)
    assert claimed is not None
    with Session(engine) as session:
        stored = session.get(Job, job.id)
        assert stored is not None
        stored.heartbeat_at = utcnow() - timedelta(hours=1)
        session.add(stored)
        session.commit()

    runner = WorkerRunner(
        engine, settings, backends=FakePipeline(storage, candidate_count=1).backends()
    )
    stop = threading.Event()
    thread = threading.Thread(target=runner.run, args=(stop,), daemon=True)
    thread.start()
    try:
        recovered = _wait_status(engine, job.id, "done")
        # 1 al reclamar + 1 al recuperar el huérfano + 1 al reclamarlo de nuevo.
        assert recovered.attempts == 3
    finally:
        stop.set()
        thread.join(timeout=10)


def test_signal_handlers_convert_sigterm_into_clean_stop() -> None:
    stop = threading.Event()
    previous = signal.getsignal(signal.SIGTERM)

    with signal_handlers(stop):
        signal.raise_signal(signal.SIGTERM)
        assert stop.is_set()

    assert signal.getsignal(signal.SIGTERM) is previous


def test_signal_handlers_restore_both_signals() -> None:
    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)
    stop = threading.Event()

    with signal_handlers(stop):
        assert signal.getsignal(signal.SIGINT) is not previous_int

    assert signal.getsignal(signal.SIGINT) is previous_int
    assert signal.getsignal(signal.SIGTERM) is previous_term
