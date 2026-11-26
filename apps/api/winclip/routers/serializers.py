"""Conversión de modelos SQLModel a esquemas de la API."""

from __future__ import annotations

from sqlmodel import Session, select

from winclip.core.models import Clip, Job, Project
from winclip.routers.schemas import ClipOut, JobOut, JobSummary, ProjectOut

ACTIVE_JOB_STATUSES = ("queued", "running")


def job_out(job: Job) -> JobOut:
    return JobOut.model_validate(job)


def job_summary(job: Job) -> JobSummary:
    return JobSummary.model_validate(job)


def clip_out(clip: Clip) -> ClipOut:
    rendered = clip.status == "rendered" and bool(clip.path)
    return ClipOut(
        **{
            field: getattr(clip, field)
            for field in (
                "id",
                "project_id",
                "status",
                "title",
                "description",
                "hashtags",
                "score",
                "hook",
                "start_sec",
                "end_sec",
                "duration",
                "created_at",
                "updated_at",
            )
        },
        video_url=f"/api/clips/{clip.id}/file" if rendered else None,
        thumb_url=f"/api/clips/{clip.id}/thumb" if rendered and clip.thumb_path else None,
    )


def project_out(
    session: Session,
    project: Project,
    *,
    jobs: list[Job] | None = None,
    clips: list[Clip] | None = None,
) -> ProjectOut:
    if clips is None:
        clips = list(session.exec(select(Clip).where(Clip.project_id == project.id)).all())
    if jobs is None:
        jobs = list(
            session.exec(
                select(Job).where(Job.project_id == project.id).order_by(Job.created_at, Job.id)
            ).all()
        )

    ordered = sorted(jobs, key=lambda job: (job.created_at, job.id))
    active = next(
        (job for job in reversed(ordered) if job.status in ACTIVE_JOB_STATUSES),
        None,
    )
    thumb = next(
        (
            f"/api/clips/{clip.id}/thumb"
            for clip in sorted(clips, key=lambda item: item.score, reverse=True)
            if clip.status == "rendered" and clip.thumb_path
        ),
        None,
    )
    return ProjectOut(
        **{
            field: getattr(project, field)
            for field in (
                "id",
                "workspace_id",
                "campaign_id",
                "source_type",
                "source_url",
                "title",
                "status",
                "requested_clips",
                "language",
                "duration",
                "subtitle_preset",
                "reframe_mode",
                "created_at",
                "updated_at",
            )
        },
        clips_count=len(clips),
        thumb_url=thumb,
        active_job=job_summary(active) if active is not None else None,
        latest_job=job_summary(ordered[-1]) if ordered else None,
        jobs=[job_out(job) for job in ordered],
    )
