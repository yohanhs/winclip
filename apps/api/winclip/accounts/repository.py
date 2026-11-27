"""Helpers transaccionales para el modelo `SocialAccount`."""

from __future__ import annotations

from sqlmodel import Session, select

from winclip.core.models import SocialAccount, utcnow


def set_default_account(session: Session, account: SocialAccount) -> SocialAccount:
    """Marca `account` como cuenta por defecto para su `(workspace_id, platform)`.

    Desmarca atómicamente cualquier otra cuenta por defecto en la misma plataforma
    antes de activar la nueva (cumple el índice único parcial en SQLite).
    """
    others = session.exec(
        select(SocialAccount).where(
            SocialAccount.workspace_id == account.workspace_id,
            SocialAccount.platform == account.platform,
            SocialAccount.is_default == True,  # noqa: E712
            SocialAccount.id != account.id,
        )
    ).all()
    now = utcnow()
    for other in others:
        other.is_default = False
        other.updated_at = now
        session.add(other)
    if others:
        session.flush()

    account.is_default = True
    account.updated_at = now
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def has_default_for_platform(session: Session, workspace_id: str, platform: str) -> bool:
    """Indica si ya existe una cuenta por defecto para `(workspace_id, platform)`."""
    existing = session.exec(
        select(SocialAccount.id).where(
            SocialAccount.workspace_id == workspace_id,
            SocialAccount.platform == platform,
            SocialAccount.is_default == True,  # noqa: E712
        )
    ).first()
    return existing is not None
