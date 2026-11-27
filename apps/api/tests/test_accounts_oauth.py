"""Tests unitarios de `winclip/accounts/oauth.py` (YouTube, TikTok, Instagram + CSRF)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlmodel import Session

from winclip.accounts.crypto import LocalCredentialStore
from winclip.accounts.oauth import (
    OAuthConfigError,
    OAuthStateError,
    OAuthStateManager,
    complete_oauth,
    confirm_instagram_selection,
    start_oauth,
)
from winclip.core.config import Settings
from winclip.core.db import clear_engine_cache, ensure_default_workspace, init_db


def _make_settings(tmp_path: Path, *, with_secrets: bool = True) -> Settings:
    key = Fernet.generate_key().decode("ascii")
    google_file = ""
    if with_secrets:
        secret_path = tmp_path / "client_secret_fixture.json"
        secret_path.write_text(
            json.dumps(
                {
                    "installed": {
                        "client_id": "fake-google-client-id-test",
                        "client_secret": "fake-google-client-secret-test",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                }
            ),
            encoding="utf-8",
        )
        google_file = str(secret_path)

    return Settings(
        storage_dir=tmp_path / "storage",
        winclip_secret_key=SecretStr(key),
        google_client_secret_file=google_file,
        tiktok_client_key=SecretStr("fake-tiktok-key-test" if with_secrets else ""),
        tiktok_client_secret=SecretStr("fake-tiktok-secret-test" if with_secrets else ""),
        meta_app_id="fake-meta-app-id-test" if with_secrets else "",
        meta_app_secret=SecretStr("fake-meta-app-secret-test" if with_secrets else ""),
    )


def test_missing_oauth_config_rejects_with_clear_message(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, with_secrets=False)
    mgr = OAuthStateManager()

    for platform, expected_var in (
        ("youtube", "GOOGLE_CLIENT_SECRET_FILE"),
        ("tiktok", "TIKTOK_CLIENT_KEY"),
        ("instagram", "META_APP_ID"),
    ):
        with pytest.raises(OAuthConfigError) as exc_info:
            start_oauth(platform, settings, workspace_id="ws1", state_manager=mgr)
        assert expected_var in exc_info.value.missing


def test_invalid_or_reused_state_is_rejected(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _make_settings(tmp_path)
    engine = init_db(settings)
    mgr = OAuthStateManager()

    with Session(engine) as session, pytest.raises(OAuthStateError):
        complete_oauth(
            session,
            settings,
            platform="youtube",
            code="fake-code",
            state="nonexistent-state",
            state_manager=mgr,
        )


def test_youtube_oauth_full_flow_encrypts_credentials(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _make_settings(tmp_path)
    engine = init_db(settings)
    mgr = OAuthStateManager()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "access_token": "fake-yt-access-token-test",
                    "refresh_token": "fake-yt-refresh-token-test",
                    "expires_in": 3600,
                    "scope": (
                        "https://www.googleapis.com/auth/youtube.upload "
                        "https://www.googleapis.com/auth/youtube.readonly"
                    ),
                },
            )
        if request.url.host == "www.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "UC_FAKE_123",
                            "snippet": {
                                "title": "HookVault",
                                "customUrl": "@hookvault",
                                "thumbnails": {"high": {"url": "https://example.com/yt.jpg"}},
                            },
                        }
                    ]
                },
            )
        return httpx.Response(404)

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        started = start_oauth("youtube", settings, workspace_id=ws.id, state_manager=mgr)
        qs = parse_qs(urlparse(started.auth_url).query)
        assert qs["access_type"] == ["offline"]
        assert qs["code_challenge_method"] == ["S256"]

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = complete_oauth(
                session,
                settings,
                platform="youtube",
                code="fake-auth-code",
                state=started.state,
                state_manager=mgr,
                http_client=client,
            )

        assert len(result.accounts) == 1
        acc = result.accounts[0]
        assert acc.platform == "youtube"
        assert acc.display_name == "HookVault"
        assert acc.handle == "@hookvault"
        assert acc.status == "connected"
        assert acc.is_default is True
        assert acc.capabilities_json["direct_post"] is True

        store = LocalCredentialStore(settings)
        loaded = store.load_credentials(acc.id)
        assert loaded["access_token"] == "fake-yt-access-token-test"
        assert loaded["refresh_token"] == "fake-yt-refresh-token-test"


def test_tiktok_oauth_detects_inbox_only_mode(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _make_settings(tmp_path)
    engine = init_db(settings)
    mgr = OAuthStateManager()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/v2/oauth/token/" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "access_token": "fake-tt-access-token-test",
                    "refresh_token": "fake-tt-refresh-token-test",
                    "expires_in": 86400,
                    "open_id": "tt_open_999",
                    "scope": "user.info.basic,video.upload",
                },
            )
        if "/v2/user/info/" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "user": {
                            "open_id": "tt_open_999",
                            "display_name": "HookVault Clips",
                            "username": "hookvault_clips",
                            "avatar_url": "https://example.com/tt.jpg",
                        }
                    },
                    "error": {"code": "ok"},
                },
            )
        return httpx.Response(404)

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        started = start_oauth(
            "tiktok", settings, workspace_id=ws.id, direct_post=False, state_manager=mgr
        )
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = complete_oauth(
                session,
                settings,
                platform="tiktok",
                code="fake-tt-code",
                state=started.state,
                state_manager=mgr,
                http_client=client,
            )

        assert len(result.accounts) == 1
        acc = result.accounts[0]
        assert acc.handle == "@hookvault_clips"
        assert acc.capabilities_json["direct_post"] is False
        assert acc.capabilities_json["inbox_only"] is True


def test_instagram_oauth_multi_account_selection(tmp_path: Path) -> None:
    clear_engine_cache()
    settings = _make_settings(tmp_path)
    engine = init_db(settings)
    mgr = OAuthStateManager()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/oauth/access_token" in url and "fb_exchange_token" not in url:
            return httpx.Response(200, json={"access_token": "fake-ig-short-token-test"})
        if "/oauth/access_token" in url and "fb_exchange_token" in url:
            return httpx.Response(
                200, json={"access_token": "fake-ig-long-token-test", "expires_in": 5184000}
            )
        if "/me/accounts" in url:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "page_1",
                            "name": "Page One",
                            "access_token": "fake-page-token-1",
                            "instagram_business_account": {
                                "id": "ig_101",
                                "username": "creator_one",
                                "name": "Creator One",
                                "profile_picture_url": "https://example.com/ig1.jpg",
                            },
                        },
                        {
                            "id": "page_2",
                            "name": "Page Two",
                            "access_token": "fake-page-token-2",
                            "instagram_business_account": {
                                "id": "ig_202",
                                "username": "creator_two",
                                "name": "Creator Two",
                                "profile_picture_url": "https://example.com/ig2.jpg",
                            },
                        },
                    ]
                },
            )
        return httpx.Response(404)

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        started = start_oauth("instagram", settings, workspace_id=ws.id, state_manager=mgr)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = complete_oauth(
                session,
                settings,
                platform="instagram",
                code="fake-meta-code",
                state=started.state,
                state_manager=mgr,
                http_client=client,
            )

        assert result.pending_selection_token is not None
        assert len(result.instagram_candidates) == 2
        assert result.accounts == []

        saved = confirm_instagram_selection(
            session,
            settings,
            selection_token=result.pending_selection_token,
            external_account_ids=["ig_202"],
            state_manager=mgr,
        )
        assert len(saved) == 1
        assert saved[0].handle == "@creator_two"
        assert saved[0].external_account_id == "ig_202"
        assert saved[0].status == "connected"
