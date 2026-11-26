"""`/api/jobs`: consulta y cancelación de trabajos."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session

from winclip.core.models import Job
from winclip.routers.deps import EngineDep, SessionDep
from winclip.routers.schemas import JobOut
from winclip.worker import queue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_or_404(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no existe el trabajo {job_id}")
    return job


@router.get("/{job_id}", response_model=JobOut, operation_id="getJob")
def get_job(job_id: str, session: SessionDep) -> JobOut:
    """Estado completo de un trabajo."""
    return JobOut.model_validate(_job_or_404(session, job_id))


@router.post("/{job_id}/cancel", response_model=JobOut, operation_id="cancelJob")
def cancel_job(job_id: str, session: SessionDep, engine: EngineDep) -> JobOut:
    """Cancela un trabajo `queued` o `running`; `409` si ya es terminal."""
    job = _job_or_404(session, job_id)
    if job.status in {"done", "failed", "cancelled"}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"el trabajo {job_id} ya finalizó ({job.status})",
        )
    try:
        updated = queue.cancel_job(engine, job_id)
    except queue.JobQueueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return JobOut.model_validate(updated)
