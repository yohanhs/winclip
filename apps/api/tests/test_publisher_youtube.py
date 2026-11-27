"""Tests de `YouTubeApiPublisher` con mocks de Google API (`task 2.1`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session

from winclip.accounts.crypto import LocalCredentialStore
from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db
from winclip.core.ids import new_clip_id, new_project_id, new_ulid
from winclip.core.models import Clip, Project, SocialAccount
from winclip.publishers.base import (
    PublishMeta,
    PublishValidationError,
    QuotaExceededError,
)
from winclip.publishers.youtube_api import YouTubeApiPublisher


class _FakeHttpError(Exception):
    def __init__(self, status: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.resp = SimpleNamespace(status=status)
        self.content = json.dumps(
            {"error": {"code": status, "message": message, "errors": [{"reason": reason}]}}
        ).encode("utf-8")


class _FakeUploadRequest:
    def __init__(self, video_id: str, fail: Exception | None = None) -> None:
        self.video_id = video_id
        self.fail = fail
        self.calls = 0

    def next_chunk(self) -> tuple[Any, dict[str, Any] | None]:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        if self.calls == 1:
            return SimpleNamespace(progress=lambda: 0.5), None
        return SimpleNamespace(progress=lambda: 1.0), {"id": self.video_id}


class _FakeYouTubeService:
    def __init__(
        self,
        *,
        video_id: str = "yt-abc123",
        upload_error: Exception | None = None,
        thumb_error: Exception | None = None,
        comment_error: Exception | None = None,
    ) -> None:
        self.video_id = video_id
        self.upload_error = upload_error
        self.thumb_error = thumb_error
        self.comment_error = comment_error
        self.insert_calls: list[dict[str, Any]] = []
        self.thumb_calls: list[dict[str, Any]] = []
        self.comment_calls: list[dict[str, Any]] = []

    def videos(self) -> Any:
        parent = self

        class _Videos:
            def insert(self, **kwargs: Any) -> _FakeUploadRequest:
                parent.insert_calls.append(kwargs)
                return _FakeUploadRequest(parent.video_id, fail=parent.upload_error)

        return _Videos()

    def thumbnails(self) -> Any:
        parent = self

        class _Thumbs:
            def set(self, **kwargs: Any) -> Any:
                parent.thumb_calls.append(kwargs)

                class _Exec:
                    def execute(self) -> dict[str, Any]:
                        if parent.thumb_error is not None:
                            raise parent.thumb_error
                        return {"items": []}

                return _Exec()

        return _Thumbs()

    def commentThreads(self) -> Any:
        parent = self

        class _Comments:
            def insert(self, **kwargs: Any) -> Any:
                parent.comment_calls.append(kwargs)

                class _Exec:
                    def execute(self) -> dict[str, Any]:
                        if parent.comment_error is not None:
                            raise parent.comment_error
                        return {"id": "comment-1"}

                return _Exec()

        return _Comments()


def _setup_fixture(tmp_path: Path) -> tuple[Settings, Session, Clip, SocialAccount]:
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
    thumb_rel = f"projects/{proj.id}/clips/clip1/thumb.jpg"
    clip_file = settings.storage_dir / clip_rel
    thumb_file = settings.storage_dir / thumb_rel
    clip_file.parent.mkdir(parents=True, exist_ok=True)
    clip_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    thumb_file.write_bytes(b"\xff\xd8\xff\xe0jpg")

    clip = Clip(
        id=new_clip_id(),
        project_id=proj.id,
        title="Short de prueba",
        status="rendered",
        path=clip_rel,
        thumb_path=thumb_rel,
    )
    acc = SocialAccount(
        id=new_ulid(),
        workspace_id=ws.id,
        platform="youtube",
        auth_method="api",
        display_name="Canal Principal",
        handle="@canal",
        status="connected",
    )
    session.add(clip)
    session.add(acc)
    session.commit()

    store = LocalCredentialStore(settings)
    store.save_credentials(
        acc.id,
        {
            "access_token": "ya29.fake-test-token",
            "refresh_token": "1//fake-refresh",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    )
    return settings, session, clip, acc


def test_youtube_immediate_upload_with_thumbnail_and_comment(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_fixture(tmp_path)
    try:
        fake = _FakeYouTubeService(video_id="vid-999")
        progress_events: list[tuple[float, str]] = []
        pub = YouTubeApiPublisher(
            settings=settings,
            session=session,
            service_factory=lambda _creds: fake,
            media_factory=lambda path, mime, res: {"path": str(path), "mime": mime, "res": res},
            on_progress=lambda pct, stage: progress_events.append((pct, stage)),
        )
        res = pub.publish(
            clip,
            acc,
            PublishMeta(
                title="Short inmediato",
                description="Descripción #Shorts",
                tags=["Shorts", "ai"],
                pinned_comment="Deja tu comentario",
                upload_thumbnail=True,
            ),
        )
        assert res.status == "published"
        assert res.external_id == "vid-999"
        assert res.external_url == "https://www.youtube.com/shorts/vid-999"
        assert len(fake.insert_calls) == 1
        assert len(fake.thumb_calls) == 1
        assert len(fake.comment_calls) == 1
        assert progress_events[-1] == (100.0, "done")
    finally:
        session.close()


def test_youtube_native_schedule_sets_private_and_publish_at(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_fixture(tmp_path)
    try:
        fake = _FakeYouTubeService(video_id="vid-sched")
        pub = YouTubeApiPublisher(
            settings=settings,
            session=session,
            service_factory=lambda _creds: fake,
            media_factory=lambda path, mime, res: {"path": str(path)},
        )
        future = datetime.now(UTC) + timedelta(days=2)
        res = pub.publish(
            clip,
            acc,
            PublishMeta(title="Programado", scheduled_at=future, privacy_status="public"),
        )
        assert res.status == "scheduled"
        assert res.external_id == "vid-sched"
        sent_status = fake.insert_calls[0]["body"]["status"]
        assert sent_status["privacyStatus"] == "private"
        assert sent_status["publishAt"].endswith("Z")
    finally:
        session.close()


def test_youtube_quota_exceeded_is_non_retryable(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_fixture(tmp_path)
    try:
        fake = _FakeYouTubeService(
            upload_error=_FakeHttpError(403, "quotaExceeded", "The request cannot be completed")
        )
        pub = YouTubeApiPublisher(
            settings=settings,
            session=session,
            service_factory=lambda _creds: fake,
            media_factory=lambda path, mime, res: {"path": str(path)},
        )
        with pytest.raises(QuotaExceededError) as exc_info:
            pub.publish(clip, acc, PublishMeta(title="Sin cuota"))
        assert exc_info.value.retryable is False
        assert exc_info.value.code == "quota_exceeded"
    finally:
        session.close()


def test_youtube_thumbnail_403_is_warning_and_idempotency_skips_reupload(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_fixture(tmp_path)
    try:
        fake = _FakeYouTubeService(
            thumb_error=_FakeHttpError(403, "forbidden", "Custom thumbnails disabled")
        )
        pub = YouTubeApiPublisher(
            settings=settings,
            session=session,
            service_factory=lambda _creds: fake,
            media_factory=lambda path, mime, res: {"path": str(path)},
        )
        res = pub.publish(
            clip,
            acc,
            PublishMeta(
                title="Reintento idempotente",
                existing_external_id="vid-existing",
                upload_thumbnail=True,
            ),
        )
        assert res.external_id == "vid-existing"
        assert len(fake.insert_calls) == 0  # No re-subió el video!
        assert len(fake.thumb_calls) == 1
        assert any("403" in w for w in res.warnings)
    finally:
        session.close()


def test_youtube_rejects_long_title_before_upload(tmp_path: Path) -> None:
    settings, session, clip, acc = _setup_fixture(tmp_path)
    try:
        fake = _FakeYouTubeService()
        pub = YouTubeApiPublisher(
            settings=settings,
            session=session,
            service_factory=lambda _creds: fake,
            media_factory=lambda path, mime, res: {"path": str(path)},
        )
        with pytest.raises(PublishValidationError):
            pub.publish(clip, acc, PublishMeta(title="x" * 101))
        assert len(fake.insert_calls) == 0
    finally:
        session.close()
