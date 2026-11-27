"""Tests del modelo `SocialAccount`, migración Alembic 0003 y helper `set_default_account`."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from winclip.accounts.repository import has_default_for_platform, set_default_account
from winclip.core.config import Settings
from winclip.core.db import clear_engine_cache, ensure_default_workspace, init_db
from winclip.core.ids import new_ulid
from winclip.core.models import SocialAccount


def test_social_account_migration_and_multiple_accounts_per_platform(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = Settings(storage_dir=tmp_path)
    engine = init_db(settings)

    with Session(engine) as session:
        workspace = ensure_default_workspace(session)
        acc1 = SocialAccount(
            id=new_ulid(),
            workspace_id=workspace.id,
            platform="youtube",
            display_name="HookVault",
            handle="@hookvault",
            alias="Canal Principal",
            auth_method="api",
            credentials_ref="accounts/a1/credentials.enc",
            status="connected",
            is_default=True,
            capabilities_json={"direct_post": True},
        )
        acc2 = SocialAccount(
            id=new_ulid(),
            workspace_id=workspace.id,
            platform="youtube",
            display_name="Dinero en Voz Baja",
            handle="@dineroenvb",
            alias="Canal Finanzas",
            auth_method="api",
            credentials_ref="accounts/a2/credentials.enc",
            status="connected",
            is_default=False,
        )
        session.add(acc1)
        session.add(acc2)
        session.commit()

        rows = session.exec(select(SocialAccount).where(SocialAccount.platform == "youtube")).all()
        assert len(rows) == 2
        assert has_default_for_platform(session, workspace.id, "youtube") is True
        assert has_default_for_platform(session, workspace.id, "tiktok") is False


def test_set_default_account_atomically_switches_default_per_platform(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = Settings(storage_dir=tmp_path)
    engine = init_db(settings)

    with Session(engine) as session:
        workspace = ensure_default_workspace(session)
        tt1 = SocialAccount(
            id=new_ulid(),
            workspace_id=workspace.id,
            platform="tiktok",
            display_name="TT Uno",
            handle="@tt1",
            auth_method="api",
            credentials_ref="accounts/t1/credentials.enc",
            status="connected",
            is_default=True,
        )
        tt2 = SocialAccount(
            id=new_ulid(),
            workspace_id=workspace.id,
            platform="tiktok",
            display_name="TT Dos",
            handle="@tt2",
            auth_method="playwright",
            credentials_ref="accounts/t2/profile",
            status="connected",
            is_default=False,
        )
        yt1 = SocialAccount(
            id=new_ulid(),
            workspace_id=workspace.id,
            platform="youtube",
            display_name="YT Uno",
            handle="@yt1",
            auth_method="api",
            credentials_ref="accounts/y1/credentials.enc",
            status="connected",
            is_default=True,
        )
        session.add_all([tt1, tt2, yt1])
        session.commit()

        updated = set_default_account(session, tt2)
        assert updated.is_default is True

        session.refresh(tt1)
        session.refresh(yt1)
        assert tt1.is_default is False
        assert yt1.is_default is True


def test_db_unique_partial_index_blocks_two_defaults_same_platform(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = Settings(storage_dir=tmp_path)
    engine = init_db(settings)

    with Session(engine) as session:
        workspace = ensure_default_workspace(session)
        ig1 = SocialAccount(
            id=new_ulid(),
            workspace_id=workspace.id,
            platform="instagram",
            display_name="IG 1",
            auth_method="api",
            credentials_ref="accounts/i1/credentials.enc",
            status="connected",
            is_default=True,
        )
        ig2 = SocialAccount(
            id=new_ulid(),
            workspace_id=workspace.id,
            platform="instagram",
            display_name="IG 2",
            auth_method="api",
            credentials_ref="accounts/i2/credentials.enc",
            status="connected",
            is_default=True,
        )
        session.add(ig1)
        session.commit()

        session.add(ig2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
