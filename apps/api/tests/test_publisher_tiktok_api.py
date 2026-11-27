"""Tests de `TikTokApiPublisher` (Direct Post, fallback Inbox y fallo remoto, `task 2.2`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session

from winclip.accounts.crypto import LocalCredentialStore
from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db
from winclip.core.ids import new_clip_id, new_project_id, new_ulid
from winclip.core.models import Clip, Project, SocialAccount
from winclip.publishers.base import PermanentPublishError, PublishMeta
from winclip.publishers.tiktok_api import INBOX_NOTICE, TikTokApiPublisher


def _setup_tiktok(
    tmp_path: Path, *, direct_post: bool
) -> tuple[Settings, Session, Clip, SocialAccount]:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        winclip_secret_key=Fernet.generate_key().decode("ascii"),
    )
    engine = init_db(settings)
    session = Session(engine)
    ws = ensure_default_workspace(session)

    proj = Project(id=new_project_id(), workspace_id=ws.id, title="Video", status="ready")
    session.add(proj)
    session.flush()

    clip_rel = f"projects/{proj.id}/clips/clip1/clip.mp4"
    clip_file = settings.storage_dir / clip_rel
    clip_file.parent.mkdir(parents=True, exist_ok=True)
    clip_file.write_bytes(b"0123456789abcdef" * 64)

    clip = Clip(
        id=new_clip_id(),
        project_id=proj.id,
        title="Clip TikTok",
        status="rendered",
        path=clip_rel,
    )
    acc = SocialAccount(
        id=new_ulid(),
        workspace_id=ws.id,
        platform="tiktok",
        auth_method="api",
        display_name="Cuenta TT",
        handle="@cuentatt",
        status="connected",
        capabilities_json={"direct_post": direct_post},
    )
    session.add(clip)
    session.add(acc)
    session.commit()

    store = LocalCredentialStore(settings)
    store.save_credentials(
        acc.id,
        {
            "access_token": "tt-fake-access-token",
            "refresh_token": "tt-fake-refresh",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    )
    return settings, session, clip, acc


def test_tiktok_direct_post_success(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_tiktok(tmp_path, direct_post=True)
    calls: list[tuple[str, str]] = []
    poll_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        url = str(request.url)
        if url.endswith("/v2/post/publish/video/init/"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "publish_id": "pub-tt-1",
                        "upload_url": "https://open-upload.tiktokapis.com/upload/1",
                    },
                    "error": {"code": "ok"},
                },
            )
        if "open-upload.tiktokapis.com" in url:
            assert request.headers["Content-Type"] == "video/mp4"
            assert request.headers["Content-Range"].startswith("bytes 0-")
            return httpx.Response(201)
        if url.endswith("/v2/post/publish/status/fetch/"):
            poll_count["n"] += 1
            if poll_count["n"] == 1:
                return httpx.Response(
                    200,
                    json={"data": {"status": "PROCESSING_UPLOAD"}, "error": {"code": "ok"}},
                )
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "PUBLISH_COMPLETE",
                        "publicaly_available_post_id": ["7300112233"],
                    },
                    "error": {"code": "ok"},
                },
            )
        return httpx.Response(404)

    try:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        pub = TikTokApiPublisher(
            settings=settings,
            session=session,
            http_client=client,
            sleep_fn=lambda _: None,
            poll_intervals=(0.0, 0.0, 0.0),
        )
        res = pub.publish(clip, acc, PublishMeta(caption="Hola TikTok #ai", delivery_mode="direct"))
        assert res.delivery_mode == "direct"
        assert res.status == "published"
        assert res.external_id == "pub-tt-1"
        assert res.external_url == "https://www.tiktok.com/@cuentatt/video/7300112233"
        assert any("/video/init/" in url for _, url in calls)
    finally:
        session.close()


def test_tiktok_fallback_to_inbox_when_direct_post_unavailable(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_tiktok(tmp_path, direct_post=False)
    init_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "init" in url:
            init_urls.append(url)
            return httpx.Response(
                200,
                json={
                    "data": {
                        "publish_id": "pub-inbox-1",
                        "upload_url": "https://open-upload.tiktokapis.com/upload/inbox",
                    },
                    "error": {"code": "ok"},
                },
            )
        if "open-upload.tiktokapis.com" in url:
            return httpx.Response(201)
        if url.endswith("/v2/post/publish/status/fetch/"):
            return httpx.Response(
                200,
                json={"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok"}},
            )
        return httpx.Response(404)

    try:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        pub = TikTokApiPublisher(
            settings=settings,
            session=session,
            http_client=client,
            sleep_fn=lambda _: None,
            poll_intervals=(0.0, 0.0),
        )
        res = pub.publish(clip, acc, PublishMeta(caption="Borrador", delivery_mode="direct"))
        assert res.delivery_mode == "inbox"
        assert res.external_id == "pub-inbox-1"
        assert INBOX_NOTICE in res.warnings
        assert any("/inbox/video/init/" in u for u in init_urls)
    finally:
        session.close()


def test_tiktok_remote_failed_status_raises_permanent_error(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_tiktok(tmp_path, direct_post=True)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/v2/post/publish/video/init/"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "publish_id": "pub-fail-1",
                        "upload_url": "https://open-upload.tiktokapis.com/upload/fail",
                    },
                    "error": {"code": "ok"},
                },
            )
        if "open-upload.tiktokapis.com" in url:
            return httpx.Response(201)
        if url.endswith("/v2/post/publish/status/fetch/"):
            return httpx.Response(
                200,
                json={
                    "data": {"status": "FAILED", "fail_reason": "frame_rate_check_failed"},
                    "error": {"code": "ok"},
                },
            )
        return httpx.Response(404)

    try:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        pub = TikTokApiPublisher(
            settings=settings,
            session=session,
            http_client=client,
            sleep_fn=lambda _: None,
            poll_intervals=(0.0, 0.0),
        )
        with pytest.raises(PermanentPublishError, match="frame_rate_check_failed") as exc_info:
            pub.publish(clip, acc, PublishMeta(caption="Fallo"))
        assert exc_info.value.external_id == "pub-fail-1"
    finally:
        session.close()
