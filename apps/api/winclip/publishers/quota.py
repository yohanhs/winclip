"""Cálculo de cuotas diarias (YouTube 10k unidades/día) y límites por cuenta (`design.md`)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from winclip.core.config import Settings
from winclip.core.models import Publication, SocialAccount

COUNTED_PUBLICATION_STATUSES = ("published", "publishing", "scheduled")


def _today_utc_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def daily_limit_for_account(account: SocialAccount, settings: Settings) -> int:
    """Devuelve el límite diario conservador para la cuenta según plataforma y método."""
    if account.auth_method == "playwright":
        return settings.publish_daily_limit_playwright
    if account.platform == "youtube":
        return settings.publish_daily_limit_youtube_api
    if account.platform == "tiktok":
        return settings.publish_daily_limit_tiktok_api
    if account.platform == "instagram":
        return settings.publish_daily_limit_instagram_api
    return 10


def count_today_publications(
    session: Session,
    account_id: str,
    *,
    exclude_publication_id: str | None = None,
) -> int:
    """Cuenta publicaciones activas o completadas hoy (UTC) para `account_id`."""
    since = _today_utc_start()
    rows = session.exec(
        select(Publication).where(
            Publication.account_id == account_id,
            Publication.created_at >= since,
            Publication.status.in_(COUNTED_PUBLICATION_STATUSES),
        )
    ).all()
    if exclude_publication_id is not None:
        rows = [row for row in rows if row.id != exclude_publication_id]
    return len(rows)


def youtube_quota_usage(session: Session, settings: Settings) -> dict[str, int]:
    """Calcula el consumo diario estimado de YouTube Data API v3 en unidades."""
    since = _today_utc_start()
    yt_accounts = session.exec(
        select(SocialAccount.id).where(
            SocialAccount.platform == "youtube",
            SocialAccount.auth_method == "api",
        )
    ).all()
    if not yt_accounts:
        return {
            "youtube_units_used": 0,
            "youtube_units_limit": settings.youtube_daily_quota_units,
            "youtube_upload_cost": settings.youtube_upload_quota_cost,
            "youtube_uploads_today": 0,
        }
    pubs = session.exec(
        select(Publication).where(
            Publication.account_id.in_(list(yt_accounts)),
            Publication.created_at >= since,
            Publication.status.in_(COUNTED_PUBLICATION_STATUSES),
        )
    ).all()
    uploads = len(pubs)
    return {
        "youtube_units_used": uploads * settings.youtube_upload_quota_cost,
        "youtube_units_limit": settings.youtube_daily_quota_units,
        "youtube_upload_cost": settings.youtube_upload_quota_cost,
        "youtube_uploads_today": uploads,
    }


def account_quota_summary(
    session: Session, account: SocialAccount, settings: Settings
) -> dict[str, Any]:
    """Resumen de uso diario y límite para una cuenta social."""
    used = count_today_publications(session, account.id)
    limit = daily_limit_for_account(account, settings)
    return {
        "account_id": account.id,
        "platform": account.platform,
        "auth_method": account.auth_method,
        "display_name": account.display_name,
        "handle": account.handle,
        "alias": account.alias,
        "used_today": used,
        "daily_limit": limit,
        "remaining_today": max(0, limit - used),
    }
