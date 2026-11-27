"""Tests de `winclip/accounts/health.py` (vigente, refresco transparente, revocado)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session

from winclip.accounts.crypto import LocalCredentialStore
from winclip.accounts.health import check_account
from winclip.core.config import Settings
from winclip.core.db import clear_engine_cache, ensure_default_workspace, init_db
from winclip.core.ids import new_ulid
from winclip.core.models import SocialAccount


def _setup(tmp_path: Path) -> tuple[Settings, LocalCredentialStore, Session, str]:
    clear_engine_cache()
    key = Fernet.generate_key().decode("ascii")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        winclip_secret_key=SecretStr(key),
        tiktok_client_key=SecretStr("fake-tt-key-test"),
        tiktok_client_secret=SecretStr("fake-tt-secret-test"),
        meta_app_id="fake-meta-id-test",
        meta_app_secret=SecretStr("fake-meta-secret-test"),
    )
    engine = init_db(settings)
    session = Session(engine)
    ws = ensure_default_workspace(session)
    return settings, LocalCredentialStore(settings), session, ws.id


def test_check_account_valid_token_updates_profile(tmp_path: Path) -> None:
    settings, store, session, ws_id = _setup(tmp_path)
    try:
        acc_id = new_ulid()
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        ref = store.save_credentials(
            acc_id,
            {
                "provider": "youtube",
                "access_token": "fake-valid-token-test",
                "refresh_token": "fake-refresh-token-test",
                "expires_at": future,
            },
        )
        acc = SocialAccount(
            id=acc_id,
            workspace_id=ws_id,
            platform="youtube",
            display_name="Old Name",
            handle="",
            auth_method="api",
            credentials_ref=ref,
            status="pending",
        )
        session.add(acc)
        session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer fake-valid-token-test"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "UC_NEW",
                            "snippet": {
                                "title": "Updated Channel",
                                "customUrl": "@updated",
                                "thumbnails": {"default": {"url": "https://example.com/a.jpg"}},
                            },
                        }
                    ]
                },
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            checked = check_account(session, acc, settings, http_client=client)

        assert checked.status == "connected"
        assert checked.display_name == "Updated Channel"
        assert checked.handle == "@updated"
        assert checked.avatar_url == "https://example.com/a.jpg"
        assert checked.last_check_at is not None
        assert checked.last_error is None
    finally:
        session.close()


def test_check_account_expired_token_refreshes_and_reencrypts(tmp_path: Path) -> None:
    settings, store, session, ws_id = _setup(tmp_path)
    try:
        acc_id = new_ulid()
        expired = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        ref = store.save_credentials(
            acc_id,
            {
                "provider": "youtube",
                "access_token": "fake-old-token-test",
                "refresh_token": "fake-refresh-token-test",
                "client_id": "fake-cid",
                "client_secret": "fake-csecret",
                "expires_at": expired,
            },
        )
        acc = SocialAccount(
            id=acc_id,
            workspace_id=ws_id,
            platform="youtube",
            display_name="HookVault",
            auth_method="api",
            credentials_ref=ref,
            status="expired",
        )
        session.add(acc)
        session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "fake-refreshed-token-test",
                        "expires_in": 3600,
                    },
                )
            assert request.headers["Authorization"] == "Bearer fake-refreshed-token-test"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "UC_HV",
                            "snippet": {"title": "HookVault", "customUrl": "@hookvault"},
                        }
                    ]
                },
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            checked = check_account(session, acc, settings, http_client=client)

        assert checked.status == "connected"
        assert checked.token_expires_at is not None
        reloaded = store.load_credentials(acc_id)
        assert reloaded["access_token"] == "fake-refreshed-token-test"
    finally:
        session.close()


def test_check_account_revoked_token_marks_expired(tmp_path: Path) -> None:
    settings, store, session, ws_id = _setup(tmp_path)
    try:
        acc_id = new_ulid()
        expired = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        ref = store.save_credentials(
            acc_id,
            {
                "provider": "tiktok",
                "access_token": "fake-revoked-token-test",
                "refresh_token": "fake-revoked-refresh-test",
                "expires_at": expired,
            },
        )
        acc = SocialAccount(
            id=acc_id,
            workspace_id=ws_id,
            platform="tiktok",
            display_name="TT Account",
            auth_method="api",
            credentials_ref=ref,
            status="connected",
        )
        session.add(acc)
        session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_grant"})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            checked = check_account(session, acc, settings, http_client=client)

        assert checked.status == "expired"
        assert checked.last_error is not None
        assert checked.last_check_at is not None
    finally:
        session.close()
