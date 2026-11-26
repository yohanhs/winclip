"""Cola persistente sobre la tabla `job`.

Cada operación abre su propia sesión y se apoya en una única sentencia
`UPDATE … RETURNING` para reclamar trabajo, de modo que dos workers nunca obtengan la
misma fila (design, decisión 3). La exclusividad pesada se decide en la misma sentencia
consultando si ya hay otro trabajo `running` con `heavy_active=1`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, func, or_, update
from sqlalchemy import select as sa_select
from sqlmodel import Session, select

from winclip.core.ids import new_job_id
from winclip.core.models import (
    HEAVY_JOB_TYPES,
    TERMINAL_JOB_STATUSES,
    Job,
    JobEvent,
    Project,
    utcnow,
)

BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 300.0
EVENT_RETENTION_HOURS = 24


class JobQueueError(RuntimeError):
    """Operación inválida sobre la cola (trabajo inexistente o estado incompatible)."""


def backoff_seconds(attempts: int) -> float:
    """Espera exponencial tras el intento `attempts` (1-based)."""
    exponent = max(0, attempts - 1)
    return min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2**exponent))


def _job_from_row(row: Any) -> Job:
    return Job(**dict(row._mapping))


def enqueue(
    engine: Engine,
    *,
    job_type: str,
    project_id: str | None = None,
    payload: dict[str, Any] | None = None,
    max_attempts: int | None = None,
) -> Job:
    """Crea un trabajo en estado `queued` y lo devuelve."""
    now = utcnow()
    job = Job(
        id=new_job_id(),
        project_id=project_id,
        type=job_type,
        payload=payload or {},
        status="queued",
        progress=0.0,
        stage="queued",
        attempts=0,
        max_attempts=max_attempts if max_attempts is not None else 3,
        next_run_at=now,
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
    return job


def get_job(session: Session, job_id: str) -> Job | None:
    """Trabajo por id, o `None` si no existe."""
    return session.get(Job, job_id)


def claim_next(
    engine: Engine,
    *,
    worker_id: str,
    light_running: int,
    light_limit: int,
) -> Job | None:
    """Reclama atómicamente el siguiente trabajo ejecutable, o `None`."""
    now = utcnow()
    job = Job.__table__
    heavy_exists = (
        sa_select(job.c.id).where(job.c.status == "running", job.c.heavy_active.is_(True)).exists()
    )
    eligible = (
        (job.c.status == "queued")
        & or_(job.c.next_run_at.is_(None), job.c.next_run_at <= now)
        & or_(
            (job.c.type.in_(HEAVY_JOB_TYPES)) & (~heavy_exists),
            (job.c.type.notin_(HEAVY_JOB_TYPES)) & (light_running < light_limit),
        )
    )
    candidate = sa_select(job.c.id).where(eligible).order_by(job.c.created_at, job.c.id).limit(1)

    statement = (
        update(job)
        .where(job.c.id == candidate.scalar_subquery())
        .values(
            status="running",
            worker_id=worker_id,
            started_at=func.coalesce(job.c.started_at, now),
            heartbeat_at=now,
            attempts=job.c.attempts + 1,
            heavy_active=job.c.type.in_(HEAVY_JOB_TYPES),
            next_run_at=None,
            updated_at=now,
        )
        .returning(*job.c)
    )
    with Session(engine) as session:
        row = session.connection().execute(statement).first()
        session.commit()
    return _job_from_row(row) if row is not None else None


def record_event(
    session: Session,
    *,
    event_type: str,
    payload: dict[str, Any],
    project_id: str | None = None,
    job_id: str | None = None,
) -> JobEvent:
    """Añade un evento al outbox en la sesión dada (sin commit propio)."""
    event = JobEvent(
        project_id=project_id,
        job_id=job_id,
        event_type=event_type,
        payload=payload,
        created_at=utcnow(),
    )
    session.add(event)
    return event


def emit_event(
    engine: Engine,
    *,
    event_type: str,
    payload: dict[str, Any],
    project_id: str | None = None,
    job_id: str | None = None,
) -> int:
    """Registra un evento en su propia transacción y devuelve su id."""
    with Session(engine) as session:
        event = record_event(
            session,
            event_type=event_type,
            payload=payload,
            project_id=project_id,
            job_id=job_id,
        )
        session.commit()
        session.refresh(event)
        return int(event.id or 0)


def update_progress(
    engine: Engine,
    job_id: str,
    *,
    progress: float | None = None,
    stage: str | None = None,
) -> Job:
    """Persiste progreso monótono y etapa, emitiendo `job.progress` si cambia algo."""
    now = utcnow()
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobQueueError(f"no existe el trabajo {job_id}")
        new_progress = job.progress
        if progress is not None:
            new_progress = round(min(100.0, max(job.progress, float(progress))), 2)
        new_stage = stage or job.stage
        changed = new_progress != job.progress or new_stage != job.stage
        if not changed:
            return job
        job.progress = new_progress
        job.stage = new_stage
        job.updated_at = now
        job.heartbeat_at = now
        session.add(job)
        record_event(
            session,
            event_type="job.progress",
            project_id=job.project_id,
            job_id=job.id,
            payload={
                "job_id": job.id,
                "project_id": job.project_id,
                "type": job.type,
                "status": job.status,
                "progress": job.progress,
                "stage": job.stage,
            },
        )
        session.commit()
        session.refresh(job)
    return job


def heartbeat(engine: Engine, job_id: str, *, worker_id: str) -> bool:
    """Renueva el latido; devuelve `False` si el trabajo ya no pertenece al worker."""
    with Session(engine) as session:
        result = session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "running", Job.worker_id == worker_id)
            .values(heartbeat_at=utcnow(), updated_at=utcnow())
        )
        session.commit()
        return bool(result.rowcount)


def acquire_heavy(engine: Engine, job_id: str) -> bool:
    """Marca el trabajo como pesado solo si ningún otro lo es (atómico)."""
    now = utcnow()
    job = Job.__table__
    others = (
        sa_select(job.c.id)
        .where(
            job.c.status == "running",
            job.c.heavy_active.is_(True),
            job.c.id != job_id,
        )
        .exists()
    )
    with Session(engine) as session:
        result = session.connection().execute(
            update(job)
            .where(job.c.id == job_id, Job.status == "running", ~others)
            .values(heavy_active=True, updated_at=now)
        )
        session.commit()
        return bool(result.rowcount)


def release_heavy(engine: Engine, job_id: str) -> None:
    """Libera el bloqueo pesado del trabajo."""
    with Session(engine) as session:
        session.execute(
            update(Job).where(Job.id == job_id).values(heavy_active=False, updated_at=utcnow())
        )
        session.commit()


def is_cancel_requested(engine: Engine, job_id: str) -> bool:
    """`True` si la API pidió cancelar el trabajo."""
    with Session(engine) as session:
        value = session.exec(select(Job.cancel_requested).where(Job.id == job_id)).first()
    return bool(value)


def _set_project_status(session: Session, project_id: str | None, status: str) -> None:
    if project_id is None:
        return
    project = session.get(Project, project_id)
    if project is not None:
        project.status = status
        project.updated_at = utcnow()
        session.add(project)


def complete_job(engine: Engine, job_id: str) -> Job:
    """Marca el trabajo como `done` al 100 %, libera el recurso y emite `job.done`."""
    now = utcnow()
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobQueueError(f"no existe el trabajo {job_id}")
        job.status = "done"
        job.progress = 100.0
        job.stage = "done"
        job.error = None
        job.next_run_at = None
        job.finished_at = now
        job.updated_at = now
        job.heavy_active = False
        job.cancel_requested = False
        session.add(job)
        record_event(
            session,
            event_type="job.done",
            project_id=job.project_id,
            job_id=job.id,
            payload={
                "job_id": job.id,
                "project_id": job.project_id,
                "type": job.type,
                "status": "done",
                "progress": 100.0,
                "stage": "done",
            },
        )
        session.commit()
        session.refresh(job)
    return job


def fail_job(
    engine: Engine,
    job_id: str,
    error: str,
    *,
    retryable: bool = True,
) -> Job:
    """Reintenta con backoff o marca `failed` si se agotaron los intentos."""
    now = utcnow()
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobQueueError(f"no existe el trabajo {job_id}")
        job.error = error.strip()[:2000] or "error desconocido"
        job.heavy_active = False
        job.worker_id = None
        job.heartbeat_at = None
        job.updated_at = now

        if retryable and job.attempts < job.max_attempts:
            job.status = "queued"
            job.stage = "retry"
            job.next_run_at = now + timedelta(seconds=backoff_seconds(job.attempts))
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

        job.status = "failed"
        job.stage = "failed"
        job.finished_at = now
        job.next_run_at = None
        session.add(job)
        _set_project_status(session, job.project_id, "failed")
        record_event(
            session,
            event_type="job.failed",
            project_id=job.project_id,
            job_id=job.id,
            payload={
                "job_id": job.id,
                "project_id": job.project_id,
                "type": job.type,
                "status": "failed",
                "stage": job.stage,
                "error": job.error,
            },
        )
        session.commit()
        session.refresh(job)
    return job


def cancel_job(engine: Engine, job_id: str) -> Job:
    """Cancela en cola al instante o marca `cancel_requested` si está en ejecución."""
    now = utcnow()
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobQueueError(f"no existe el trabajo {job_id}")
        if job.status in TERMINAL_JOB_STATUSES:
            raise JobQueueError(f"el trabajo {job_id} ya finalizó ({job.status})")
        if job.status == "queued":
            job.status = "cancelled"
            job.stage = "cancelled"
            job.finished_at = now
            job.next_run_at = None
            job.updated_at = now
            _set_project_status(session, job.project_id, "cancelled")
        else:
            job.cancel_requested = True
            job.updated_at = now
        session.add(job)
        session.commit()
        session.refresh(job)
        return job


def mark_cancelled(engine: Engine, job_id: str) -> Job:
    """Confirma la cancelación de un trabajo `running` desde el worker."""
    now = utcnow()
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise JobQueueError(f"no existe el trabajo {job_id}")
        job.status = "cancelled"
        job.stage = "cancelled"
        job.heavy_active = False
        job.cancel_requested = False
        job.finished_at = now
        job.updated_at = now
        session.add(job)
        _set_project_status(session, job.project_id, "cancelled")
        session.commit()
        session.refresh(job)
    return job


def running_counts(engine: Engine, *, worker_id: str) -> tuple[int, int]:
    """`(ligeros, pesados)` en ejecución para este worker."""
    with Session(engine) as session:
        running = session.exec(
            select(Job).where(Job.status == "running", Job.worker_id == worker_id)
        ).all()
    heavy = sum(1 for job in running if job.heavy_active)
    light = sum(1 for job in running if not job.heavy_active)
    return light, heavy


def recover_orphans(engine: Engine, *, stale_seconds: int) -> int:
    """Devuelve a `queued` los trabajos `running` con latido vencido."""
    cutoff = utcnow() - timedelta(seconds=stale_seconds)
    recovered = 0
    with Session(engine) as session:
        stale = session.exec(
            select(Job).where(
                Job.status == "running",
                or_(Job.heartbeat_at.is_(None), Job.heartbeat_at < cutoff),
            )
        ).all()
        for job in stale:
            job.attempts += 1
            job.heavy_active = False
            job.worker_id = None
            job.heartbeat_at = None
            job.updated_at = utcnow()
            if job.attempts >= job.max_attempts:
                job.status = "failed"
                job.stage = "failed"
                job.finished_at = utcnow()
                job.error = "trabajo huérfano: se agotaron los intentos tras una caída"
                _set_project_status(session, job.project_id, "failed")
                record_event(
                    session,
                    event_type="job.failed",
                    project_id=job.project_id,
                    job_id=job.id,
                    payload={
                        "job_id": job.id,
                        "project_id": job.project_id,
                        "type": job.type,
                        "status": "failed",
                        "stage": job.stage,
                        "error": job.error,
                    },
                )
            else:
                job.status = "queued"
                job.stage = "queued"
                job.next_run_at = utcnow()
                job.error = "trabajo huérfano: se devuelve a la cola"
            session.add(job)
            recovered += 1
        session.commit()
    return recovered


def purge_events(engine: Engine, *, max_age_hours: int = EVENT_RETENTION_HOURS) -> int:
    """Borra eventos antiguos del outbox y devuelve cuántos se eliminaron."""
    cutoff = utcnow() - timedelta(hours=max_age_hours)
    with Session(engine) as session:
        result = session.execute(JobEvent.__table__.delete().where(JobEvent.created_at < cutoff))
        session.commit()
        return int(result.rowcount or 0)


def list_events(
    engine: Engine,
    *,
    after_id: int = 0,
    project_id: str | None = None,
    limit: int = 200,
) -> list[JobEvent]:
    """Eventos con `id > after_id`, opcionalmente filtrados por proyecto."""
    with Session(engine) as session:
        statement = select(JobEvent).where(JobEvent.id > after_id)
        if project_id is not None:
            statement = statement.where(JobEvent.project_id == project_id)
        return list(session.exec(statement.order_by(JobEvent.id).limit(limit)).all())


def project_job_status(engine: Engine, project_id: str) -> str | None:
    """Estado del trabajo más reciente del proyecto (para no pisar `ready`)."""
    with Session(engine) as session:
        job = session.exec(
            select(Job)
            .where(Job.project_id == project_id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(1)
        ).first()
    return job.status if job is not None else None
