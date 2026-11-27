"""Tests de `InstagramGraphPublisher` con subida reanudable local (`task 2.3`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session

from winclip.accounts.crypto import LocalCredentialStore
from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db
from winclip.core.ids import new_clip_id, new_project_id, new_ulid
from winclip.core.models import Clip, Project, SocialAccount
from winclip.publishers.base import (
    PermanentPublishError,
    PublishMeta,
    PublishValidationError,
)
from winclip.publishers.instagram_graph import InstagramGraphPublisher


def _setup_instagram(tmp_path: Path) -> tuple[Settings, Session, Clip, SocialAccount]:
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
    clip_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" * 32)

    clip = Clip(
        id=new_clip_id(),
        project_id=proj.id,
        title="Reel IG",
        status="rendered",
        path=clip_rel,
    )
    acc = SocialAccount(
        id=new_ulid(),
        workspace_id=ws.id,
        platform="instagram",
        auth_method="api",
        display_name="Cuenta IG",
        handle="@cuentaig",
        external_account_id="17841400001",
        status="connected",
    )
    session.add(clip)
    session.add(acc)
    session.commit()

    store = LocalCredentialStore(settings)
    store.save_credentials(
        acc.id,
        {
            "access_token": "ig-fake-access-token",
            "page_access_token": "ig-fake-page-token",
            "ig_user_id": "17841400001",
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
    )
    return settings, session, clip, acc


def _ok_probe(_path: Path, _settings: Settings) -> SimpleNamespace:
    return SimpleNamespace(duration=32.5, video_codec="h264", width=1080, height=1920)


def test_instagram_resumable_upload_end_to_end(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_instagram(tmp_path)
    poll_calls = {"n": 0}
    rupload_called = {"ok": False}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and url.endswith("/17841400001/media"):
            return httpx.Response(
                200,
                json={
                    "id": "container-123",
                    "uri": "https://rupload.facebook.com/ig-api-upload/v21.0/container-123",
                },
            )
        if request.method == "POST" and "rupload.facebook.com" in url:
            assert request.headers["Authorization"] == "OAuth ig-fake-page-token"
            assert request.headers["offset"] == "0"
            assert int(request.headers["file_size"]) > 0
            rupload_called["ok"] = True
            return httpx.Response(200, json={"success": True})
        if request.method == "GET" and "/container-123" in url:
            poll_calls["n"] += 1
            status_code = "IN_PROGRESS" if poll_calls["n"] == 1 else "FINISHED"
            return httpx.Response(200, json={"status_code": status_code, "status": "ok"})
        if request.method == "POST" and url.endswith("/17841400001/media_publish"):
            return httpx.Response(200, json={"id": "media-777"})
        if request.method == "GET" and "/media-777" in url:
            return httpx.Response(
                200, json={"permalink": "https://www.instagram.com/reel/C9xyz123/"}
            )
        return httpx.Response(404)

    try:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        pub = InstagramGraphPublisher(
            settings=settings,
            session=session,
            http_client=client,
            sleep_fn=lambda _: None,
            probe_fn=_ok_probe,
            poll_intervals=(0.0, 0.0, 0.0),
        )
        res = pub.publish(clip, acc, PublishMeta(caption="Mi Reel #reels", share_to_feed=True))
        assert rupload_called["ok"] is True
        assert res.status == "published"
        assert res.external_id == "media-777"
        assert res.external_url == "https://www.instagram.com/reel/C9xyz123/"
    finally:
        session.close()


def test_instagram_processing_error_raises_permanent_error(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_instagram(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and url.endswith("/17841400001/media"):
            return httpx.Response(
                200,
                json={
                    "id": "container-err",
                    "uri": "https://rupload.facebook.com/ig-api-upload/v21.0/container-err",
                },
            )
        if request.method == "POST" and "rupload.facebook.com" in url:
            return httpx.Response(200, json={"success": True})
        if request.method == "GET" and "/container-err" in url:
            return httpx.Response(
                200, json={"status_code": "ERROR", "status": "Unsupported audio codec"}
            )
        return httpx.Response(404)

    try:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        pub = InstagramGraphPublisher(
            settings=settings,
            session=session,
            http_client=client,
            sleep_fn=lambda _: None,
            probe_fn=_ok_probe,
            poll_intervals=(0.0, 0.0),
        )
        with pytest.raises(PermanentPublishError, match="Unsupported audio codec"):
            pub.publish(clip, acc, PublishMeta(caption="Fallo"))
    finally:
        session.close()


def test_instagram_validates_reel_codec_and_duration_before_upload(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_instagram(tmp_path)
    try:
        pub = InstagramGraphPublisher(
            settings=settings,
            session=session,
            probe_fn=lambda _p, _s: SimpleNamespace(
                duration=2.0, video_codec="h264", width=1080, height=1920
            ),
        )
        with pytest.raises(PublishValidationError, match="demasiado corto"):
            pub.publish(clip, acc, PublishMeta(caption="Corto"))

        pub_codec = InstagramGraphPublisher(
            settings=settings,
            session=session,
            probe_fn=lambda _p, _s: SimpleNamespace(
                duration=20.0, video_codec="vp9", width=1080, height=1920
            ),
        )
        with pytest.raises(PublishValidationError, match="Códec de video incompatible"):
            pub_codec.publish(clip, acc, PublishMeta(caption="Mal codec"))
    finally:
        session.close()
