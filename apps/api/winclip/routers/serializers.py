"""Conversión de modelos SQLModel a esquemas de la API."""

from __future__ import annotations

from sqlmodel import Session, select

from winclip.core.models import Campaign, Clip, Job, Project, Publication, SocialAccount
from winclip.core.storage import LocalStorage
from winclip.publishers.base import PublishMeta
from winclip.routers.schemas import (
    CampaignOut,
    ClipOut,
    JobOut,
    JobSummary,
    ProjectOut,
    PublicationDetailOut,
    PublicationOut,
    SocialAccountOut,
)
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
    overrides = clip.render_overrides or {}
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
        subtitle_preset=overrides.get("subtitle_preset"),
        reframe_mode=overrides.get("reframe_mode"),
        crop_x_pct=overrides.get("crop_x_pct"),
        crop_y_pct=overrides.get("crop_y_pct"),
        zoom_pct=overrides.get("zoom_pct"),
        subtitle_overrides=dict(clip.subtitle_overrides or {}),
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


def social_account_out(account: SocialAccount) -> SocialAccountOut:
    """Serializa `SocialAccount` excluyendo `credentials_ref` y cualquier secreto."""
    return SocialAccountOut(
        id=account.id,
        workspace_id=account.workspace_id,
        platform=account.platform,  # type: ignore[arg-type]
        display_name=account.display_name,
        handle=account.handle,
        alias=account.alias,
        avatar_url=account.avatar_url,
        auth_method=account.auth_method,  # type: ignore[arg-type]
        status=account.status,  # type: ignore[arg-type]
        is_default=account.is_default,
        capabilities=dict(account.capabilities_json or {}),
        external_account_id=account.external_account_id,
        token_expires_at=account.token_expires_at,
        last_check_at=account.last_check_at,
        last_error=account.last_error,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def publication_out(
    session: Session,
    pub: Publication,
    *,
    clip: Clip | None = None,
    project: Project | None = None,
    account: SocialAccount | None = None,
    job: Job | None = None,
) -> PublicationOut:
    """Serializa `Publication` enriquecida con datos del clip, proyecto, cuenta y job."""
    clip_obj = clip or session.get(Clip, pub.clip_id)
    project_obj = project or (
        session.get(Project, clip_obj.project_id) if clip_obj is not None else None
    )
    account_obj = account or session.get(SocialAccount, pub.account_id)
    job_obj = job or (session.get(Job, pub.job_id) if pub.job_id else None)

    meta = PublishMeta.model_validate(pub.meta_json or {})
    has_shot = bool(pub.screenshot_path)
    return PublicationOut(
        id=pub.id,
        workspace_id=pub.workspace_id,
        clip_id=pub.clip_id,
        project_id=clip_obj.project_id if clip_obj is not None else None,
        project_title=project_obj.title if project_obj is not None else None,
        clip_title=clip_obj.title if clip_obj is not None else "",
        clip_thumb_url=(
            f"/api/clips/{clip_obj.id}/thumb"
            if clip_obj is not None and clip_obj.status == "rendered" and clip_obj.thumb_path
            else None
        ),
        account_id=pub.account_id,
        account_platform=(account_obj.platform if account_obj is not None else "youtube"),  # type: ignore[arg-type]
        account_auth_method=(account_obj.auth_method if account_obj is not None else "api"),  # type: ignore[arg-type]
        account_display_name=account_obj.display_name if account_obj is not None else "",
        account_handle=account_obj.handle if account_obj is not None else "",
        account_alias=account_obj.alias if account_obj is not None else None,
        job_id=pub.job_id,
        job_progress=float(job_obj.progress) if job_obj is not None else 0.0,
        job_stage=job_obj.stage if job_obj is not None else None,
        status=pub.status,  # type: ignore[arg-type]
        delivery_mode=pub.delivery_mode,  # type: ignore[arg-type]
        scheduled_at=pub.scheduled_at,
        published_at=pub.published_at,
        meta=meta,
        external_id=pub.external_id,
        external_url=pub.external_url,
        error=pub.error,
        error_code=pub.error_code,
        warnings=list(pub.warnings_json or []),
        has_screenshot=has_shot,
        screenshot_url=f"/api/publications/{pub.id}/screenshot" if has_shot else None,
        attempts=pub.attempts,
        created_at=pub.created_at,
        updated_at=pub.updated_at,
    )


def publication_detail_out(
    session: Session,
    pub: Publication,
    storage: LocalStorage,
) -> PublicationDetailOut:
    """Extiende `PublicationOut` con la lista de capturas de pasos en disco."""
    base = publication_out(session, pub)
    steps_dir = storage.publication_steps_dir(pub.id)
    steps: list[str] = []
    if steps_dir.is_dir():
        for png in sorted(steps_dir.glob("*.png")):
            steps.append(png.name)
    return PublicationDetailOut(**base.model_dump(), step_screenshots=steps)
