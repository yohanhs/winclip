"""Conversión de modelos SQLModel a esquemas de la API."""

from __future__ import annotations

from sqlmodel import Session, select

from winclip.core.models import Campaign, Clip, Job, Project
from winclip.routers.schemas import CampaignOut, ClipOut, JobOut, JobSummary, ProjectOut
from winclip.rules.schema import CampaignRules, RuleViolation

ACTIVE_JOB_STATUSES = ("queued", "running")


def job_out(job: Job) -> JobOut:
    return JobOut.model_validate(job)


def job_summary(job: Job) -> JobSummary:
    return JobSummary.model_validate(job)


def clip_out(clip: Clip) -> ClipOut:
    rendered = clip.status == "rendered" and bool(clip.path)
    raw_violations = (clip.candidate or {}).get("rule_violations") or []
    violations: list[RuleViolation] = []
    for item in raw_violations:
        if isinstance(item, RuleViolation):
            violations.append(item)
        elif isinstance(item, dict):
            try:
                violations.append(RuleViolation.model_validate(item))
            except ValueError:
                continue
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
        rule_violations=violations,
    )


def campaign_out(session: Session, campaign: Campaign) -> CampaignOut:
    projects_count = len(
        session.exec(select(Project.id).where(Project.campaign_id == campaign.id)).all()
    )
    rules = CampaignRules.model_validate(campaign.rules_json)
    return CampaignOut(
        id=campaign.id,
        workspace_id=campaign.workspace_id,
        name=campaign.name,
        rules=rules,
        source_text=campaign.source_text,
        projects_count=projects_count,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
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
    campaign_name: str | None = None
    if project.campaign_id:
        campaign = session.get(Campaign, project.campaign_id)
        if campaign is not None:
            campaign_name = campaign.name
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
        campaign_name=campaign_name,
        clips_count=len(clips),
        thumb_url=thumb,
        active_job=job_summary(active) if active is not None else None,
        latest_job=job_summary(ordered[-1]) if ordered else None,
        jobs=[job_out(job) for job in ordered],
    )
