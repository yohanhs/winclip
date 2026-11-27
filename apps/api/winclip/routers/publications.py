"""Router `/api/publications`: publicación multi-cuenta, programación, cuotas e historial."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_publication_id
from winclip.core.models import Campaign, Clip, Job, Project, Publication, SocialAccount, utcnow
from winclip.core.storage import LocalStorage, StoragePathError
from winclip.publishers.base import DeliveryMode, PublishError, PublishValidationError
from winclip.publishers.metadata import build_platform_meta, validate_publish_meta
from winclip.publishers.quota import (
    account_quota_summary,
    count_today_publications,
    daily_limit_for_account,
    youtube_quota_usage,
)
from winclip.publishers.youtube_api import YouTubeApiPublisher
from winclip.routers.deps import EngineDep, SessionDep, SettingsDep
from winclip.routers.schemas import (
    AccountQuotaOut,
    PreviewMetaItemOut,
    PreviewMetaOut,
    PreviewMetaRequest,
    PublicationCancelRequest,
    PublicationDetailOut,
    PublicationOut,
    PublicationsCreateRequest,
    QuotaSummaryOut,
)
from winclip.routers.serializers import publication_detail_out, publication_out
from winclip.worker import queue

router = APIRouter(prefix="/api/publications", tags=["publications"])

ACTIVE_OR_DONE_STATUSES = ("scheduled", "publishing", "published")


def _normalize_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(UTC) if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _build_quota_summary(session: Session, settings: Settings) -> QuotaSummaryOut:
    yt = youtube_quota_usage(session, settings)
    accounts = list(
        session.exec(select(SocialAccount).order_by(SocialAccount.platform, SocialAccount.id)).all()
    )
    acc_rows = [
        AccountQuotaOut(**account_quota_summary(session, acc, settings)) for acc in accounts
    ]
    return QuotaSummaryOut(
        youtube_units_used=yt["youtube_units_used"],
        youtube_units_limit=yt["youtube_units_limit"],
        youtube_upload_cost=yt["youtube_upload_cost"],
        youtube_uploads_today=yt["youtube_uploads_today"],
        accounts=acc_rows,
    )


def _emit_pub_updated(
    engine: EngineDep,
    pub: Publication,
    *,
    project_id: str | None,
) -> None:
    queue.emit_event(
        engine,
        event_type="publication.updated",
        project_id=project_id,
        job_id=pub.job_id,
        payload={
            "publication_id": pub.id,
            "clip_id": pub.clip_id,
            "account_id": pub.account_id,
            "project_id": project_id,
            "job_id": pub.job_id,
            "status": pub.status,
            "delivery_mode": pub.delivery_mode,
            "external_id": pub.external_id,
            "external_url": pub.external_url,
            "error": pub.error,
            "error_code": pub.error_code,
            "warnings": list(pub.warnings_json or []),
            "has_screenshot": bool(pub.screenshot_path),
        },
    )


@router.get("/quota", response_model=QuotaSummaryOut, operation_id="getPublicationsQuota")
def get_publications_quota(
    session: SessionDep,
    settings: SettingsDep,
) -> QuotaSummaryOut:
    """Resumen de consumo diario de cuota YouTube y límites por cuenta."""
    return _build_quota_summary(session, settings)


@router.post(
    "/preview-meta",
    response_model=PreviewMetaOut,
    operation_id="previewPublicationMeta",
)
def preview_publication_meta(
    body: PreviewMetaRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> PreviewMetaOut:
    """Precalcula metadatos propuestos por `(clip, cuenta)` junto con avisos y cuotas."""
    clips: list[Clip] = []
    for clip_id in body.clip_ids:
        clip = session.get(Clip, clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail=f"Clip no encontrado: {clip_id}")
        clips.append(clip)

    accounts: list[SocialAccount] = []
    for account_id in body.account_ids:
        acc = session.get(SocialAccount, account_id)
        if acc is None:
            raise HTTPException(status_code=404, detail=f"Cuenta no encontrada: {account_id}")
        accounts.append(acc)

    projects_cache: dict[str, Project | None] = {}
    campaigns_cache: dict[str, Campaign | None] = {}
    items: list[PreviewMetaItemOut] = []
    global_warnings: list[str] = []

    quota = _build_quota_summary(session, settings)
    yt_batch_count = 0
    has_playwright = False
    has_tiktok_inbox = False

    for clip in clips:
        if clip.project_id not in projects_cache:
            projects_cache[clip.project_id] = session.get(Project, clip.project_id)
        project = projects_cache[clip.project_id]
        campaign: Campaign | None = None
        if project is not None and project.campaign_id:
            if project.campaign_id not in campaigns_cache:
                campaigns_cache[project.campaign_id] = session.get(Campaign, project.campaign_id)
            campaign = campaigns_cache[project.campaign_id]

        for acc in accounts:
            item_warnings: list[str] = []
            delivery_mode: DeliveryMode = "direct"
            if (
                acc.platform == "tiktok"
                and acc.auth_method == "api"
                and not bool((acc.capabilities_json or {}).get("direct_post"))
            ):
                delivery_mode = "inbox"
                has_tiktok_inbox = True
                item_warnings.append(
                    "Cuenta TikTok sin permiso Direct Post: se enviará como borrador al Inbox."
                )
            if acc.auth_method == "playwright":
                has_playwright = True
                item_warnings.append(
                    "Cuenta Playwright: automatización web sujeta a riesgos de ToS y anti-bot."
                )
            if acc.platform == "youtube" and acc.auth_method == "api":
                yt_batch_count += 1
            if acc.status == "expired":
                item_warnings.append("La sesión de esta cuenta está expirada; reconéctala antes.")

            meta = build_platform_meta(
                clip,
                campaign,
                acc.platform,  # type: ignore[arg-type]
                delivery_mode=delivery_mode,
                language_fallback=(project.language if project else "es"),
            )
            items.append(
                PreviewMetaItemOut(
                    clip_id=clip.id,
                    account_id=acc.id,
                    platform=acc.platform,  # type: ignore[arg-type]
                    auth_method=acc.auth_method,  # type: ignore[arg-type]
                    delivery_mode=delivery_mode,
                    meta=meta,
                    warnings=item_warnings,
                )
            )

    if yt_batch_count > 0:
        projected = quota.youtube_units_used + yt_batch_count * quota.youtube_upload_cost
        if projected > quota.youtube_units_limit:
            global_warnings.append(
                f"Este lote superaría la cuota diaria estándar de YouTube "
                f"({projected:,}/{quota.youtube_units_limit:,} unidades; ~6 videos/día)."
            )
    if has_tiktok_inbox:
        global_warnings.append(
            "Las cuentas de TikTok sin auditoría Direct Post recibirán los videos en el Inbox "
            "para finalizar la publicación desde la app móvil."
        )
    if has_playwright:
        global_warnings.append(
            "Aviso ToS: las cuentas conectadas vía Playwright usan navegador automatizado visible "
            "y se detienen ante cualquier CAPTCHA/2FA."
        )

    for acc in accounts:
        used = count_today_publications(session, acc.id)
        limit = daily_limit_for_account(acc, settings)
        if used + len(clips) > limit:
            global_warnings.append(
                f"La cuenta {acc.alias or acc.display_name or acc.handle} superaría su límite "
                f"diario ({used + len(clips)}/{limit})."
            )

    return PreviewMetaOut(items=items, warnings=global_warnings, quota=quota)


@router.post(
    "",
    response_model=list[PublicationOut],
    status_code=status.HTTP_201_CREATED,
    operation_id="createPublications",
)
def create_publications(
    body: PublicationsCreateRequest,
    session: SessionDep,
    engine: EngineDep,
    settings: SettingsDep,
) -> list[PublicationOut]:
    """Crea publicaciones y encola un job `publish` independiente por cada `(clip, cuenta)`."""
    workspace = ensure_default_workspace(session)
    now = utcnow()
    per_account_batch: dict[str, int] = {}
    validated_rows: list[tuple[Clip, SocialAccount, datetime | None, DeliveryMode, dict]] = []

    for item in body.items:
        clip = session.get(Clip, item.clip_id)
        if clip is None:
            raise HTTPException(status_code=404, detail=f"Clip no encontrado: {item.clip_id}")
        if clip.status != "rendered" or not clip.path:
            raise HTTPException(
                status_code=409,
                detail=f"El clip {clip.id} no está renderizado; renderízalo antes de publicar",
            )

        account = session.get(SocialAccount, item.account_id)
        if account is None:
            raise HTTPException(status_code=404, detail=f"Cuenta no encontrada: {item.account_id}")
        if account.status == "expired" and not body.force:
            acc_label = account.display_name or account.handle
            raise HTTPException(
                status_code=409,
                detail=f"La cuenta {acc_label} está expirada; reconéctala",
            )

        meta = item.meta.model_copy()
        scheduled_utc = _normalize_utc(item.scheduled_at or meta.scheduled_at)
        meta.scheduled_at = scheduled_utc

        try:
            validate_publish_meta(account.platform, meta)  # type: ignore[arg-type]
        except PublishValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Protección contra duplicados activos o ya publicados (409 sin force=true)
        if not body.force:
            existing = session.exec(
                select(Publication).where(
                    Publication.clip_id == clip.id,
                    Publication.account_id == account.id,
                    Publication.status.in_(ACTIVE_OR_DONE_STATUSES),
                )
            ).first()
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Ya existe una publicación ({existing.status}) para el clip {clip.id} "
                        f"en la cuenta {account.display_name or account.handle}. Usa force=true "
                        "para duplicar explícitamente."
                    ),
                )

        per_account_batch[account.id] = per_account_batch.get(account.id, 0) + 1
        used_today = count_today_publications(session, account.id)
        limit = daily_limit_for_account(account, settings)
        if used_today + per_account_batch[account.id] > limit and not body.force:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"La cuenta {account.display_name or account.handle} supera su límite diario "
                    f"({used_today}/{limit}). Confirma con force=true para continuar."
                ),
            )

        delivery_mode: DeliveryMode = meta.delivery_mode
        if (
            account.platform == "tiktok"
            and account.auth_method == "api"
            and not bool((account.capabilities_json or {}).get("direct_post"))
        ):
            delivery_mode = "inbox"
            meta.delivery_mode = "inbox"

        validated_rows.append(
            (clip, account, scheduled_utc, delivery_mode, meta.model_dump(mode="json"))
        )

    created: list[PublicationOut] = []
    for clip, account, scheduled_utc, delivery_mode, meta_dict in validated_rows:
        pub = Publication(
            id=new_publication_id(),
            workspace_id=workspace.id,
            clip_id=clip.id,
            account_id=account.id,
            status="scheduled",
            delivery_mode=delivery_mode,
            scheduled_at=scheduled_utc,
            meta_json=meta_dict,
            warnings_json=[],
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        session.add(pub)
        session.commit()
        session.refresh(pub)

        # YouTube API programa en servidor (run_at=None -> sube de inmediato con publishAt).
        # TikTok / Instagram difieren la ejecución local en el worker con job.run_at.
        is_future = scheduled_utc is not None and scheduled_utc > now
        run_at = (
            None
            if (not is_future or (account.platform == "youtube" and account.auth_method == "api"))
            else scheduled_utc
        )
        job = queue.enqueue(
            engine,
            job_type="publish",
            project_id=clip.project_id,
            payload={
                "publication_id": pub.id,
                "clip_id": clip.id,
                "account_id": account.id,
                "force_daily_limit": body.force,
            },
            max_attempts=settings.job_max_attempts,
            run_at=run_at,
        )
        pub.job_id = job.id
        pub.updated_at = utcnow()
        session.add(pub)
        session.commit()
        session.refresh(pub)

        _emit_pub_updated(engine, pub, project_id=clip.project_id)
        created.append(publication_out(session, pub, clip=clip, account=account, job=job))

    return created


@router.get("", response_model=list[PublicationOut], operation_id="listPublications")
def list_publications(
    session: SessionDep,
    project_id: str | None = Query(default=None),
    clip_id: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[PublicationOut]:
    """Lista publicaciones filtrables ordenadas de más reciente a más antigua."""
    stmt = select(Publication)
    if clip_id:
        stmt = stmt.where(Publication.clip_id == clip_id)
    if account_id:
        stmt = stmt.where(Publication.account_id == account_id)
    if status_filter:
        stmt = stmt.where(Publication.status == status_filter)
    if project_id:
        clip_ids = list(session.exec(select(Clip.id).where(Clip.project_id == project_id)).all())
        if not clip_ids:
            return []
        stmt = stmt.where(Publication.clip_id.in_(clip_ids))
    if platform:
        acc_ids = list(
            session.exec(select(SocialAccount.id).where(SocialAccount.platform == platform)).all()
        )
        if not acc_ids:
            return []
        stmt = stmt.where(Publication.account_id.in_(acc_ids))

    rows = list(
        session.exec(stmt.order_by(Publication.created_at.desc(), Publication.id.desc())).all()
    )
    return [publication_out(session, row) for row in rows]


@router.get(
    "/{publication_id}",
    response_model=PublicationDetailOut,
    operation_id="getPublication",
)
def get_publication(
    publication_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> PublicationDetailOut:
    """Devuelve el detalle completo de una publicación (incluyendo capturas por paso)."""
    pub = session.get(Publication, publication_id)
    if pub is None:
        raise HTTPException(status_code=404, detail=f"Publicación no encontrada: {publication_id}")
    return publication_detail_out(session, pub, LocalStorage(settings.storage_dir))


@router.get(
    "/{publication_id}/screenshot",
    operation_id="getPublicationScreenshot",
)
def get_publication_screenshot(
    publication_id: str,
    session: SessionDep,
    settings: SettingsDep,
) -> FileResponse:
    """Sirve la captura PNG diagnóstica validando ruta dentro de `STORAGE_DIR`."""
    pub = session.get(Publication, publication_id)
    if pub is None:
        raise HTTPException(status_code=404, detail=f"Publicación no encontrada: {publication_id}")
    if not pub.screenshot_path:
        raise HTTPException(status_code=404, detail="La publicación no tiene captura asociada")

    storage = LocalStorage(settings.storage_dir)
    try:
        resolved = storage.resolve_safe(pub.screenshot_path)
    except StoragePathError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Archivo de captura no encontrado en disco")
    return FileResponse(resolved, media_type="image/png")


@router.post(
    "/{publication_id}/retry",
    response_model=PublicationOut,
    operation_id="retryPublication",
)
def retry_publication(
    publication_id: str,
    session: SessionDep,
    engine: EngineDep,
    settings: SettingsDep,
) -> PublicationOut:
    """Reencola una publicación `failed` respetando idempotencia por `external_id`."""
    pub = session.get(Publication, publication_id)
    if pub is None:
        raise HTTPException(status_code=404, detail=f"Publicación no encontrada: {publication_id}")
    if pub.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden reintentar publicaciones fallidas (estado: {pub.status})",
        )

    clip = session.get(Clip, pub.clip_id)
    project_id = clip.project_id if clip is not None else None

    job = queue.enqueue(
        engine,
        job_type="publish",
        project_id=project_id,
        payload={
            "publication_id": pub.id,
            "clip_id": pub.clip_id,
            "account_id": pub.account_id,
        },
        max_attempts=settings.job_max_attempts,
        run_at=None,
    )
    pub.status = "scheduled"
    pub.job_id = job.id
    pub.error = None
    pub.error_code = None
    pub.updated_at = utcnow()
    session.add(pub)
    session.commit()
    session.refresh(pub)

    _emit_pub_updated(engine, pub, project_id=project_id)
    return publication_out(session, pub, clip=clip, job=job)


@router.post(
    "/{publication_id}/cancel",
    response_model=PublicationOut,
    operation_id="cancelPublication",
)
def cancel_publication(
    publication_id: str,
    session: SessionDep,
    engine: EngineDep,
    settings: SettingsDep,
    body: PublicationCancelRequest | None = None,
) -> PublicationOut:
    """Cancela una publicación `scheduled` y su job diferido pendiente."""
    pub = session.get(Publication, publication_id)
    if pub is None:
        raise HTTPException(status_code=404, detail=f"Publicación no encontrada: {publication_id}")
    if pub.status != "scheduled":
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden cancelar publicaciones programadas (estado: {pub.status})",
        )

    delete_remote = bool(body.delete_remote) if body is not None else False
    warnings = list(pub.warnings_json or [])

    if pub.job_id:
        job = session.get(Job, pub.job_id)
        if job is not None and job.status in ("queued", "running"):
            with contextlib.suppress(queue.JobQueueError):
                queue.cancel_job(engine, pub.job_id)

    account = session.get(SocialAccount, pub.account_id)
    if (
        account is not None
        and account.platform == "youtube"
        and account.auth_method == "api"
        and pub.external_id
    ):
        if delete_remote:
            try:
                YouTubeApiPublisher(settings=settings, session=session).delete_video(
                    account, pub.external_id
                )
            except PublishError as exc:
                warnings.append(f"Cancelada localmente, pero no se pudo borrar en YouTube ({exc}).")
        else:
            warnings.append(
                "Cancelada localmente en WinClip. El video ya fue subido como programado en "
                "YouTube Studio; elimínalo allí o cancela con delete_remote=true si lo deseas."
            )

    pub.status = "cancelled"
    pub.warnings_json = warnings
    pub.updated_at = utcnow()
    session.add(pub)
    session.commit()
    session.refresh(pub)

    clip = session.get(Clip, pub.clip_id)
    _emit_pub_updated(engine, pub, project_id=clip.project_id if clip else None)
    return publication_out(session, pub, clip=clip, account=account)
