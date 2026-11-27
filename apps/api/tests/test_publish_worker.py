"""Tests del handler `publish`: reintentos, ventana perdida, límites e idempotencia (`4.1`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session

from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace, init_db
from winclip.core.ids import new_clip_id, new_project_id, new_publication_id, new_ulid
from winclip.core.models import Clip, Project, Publication, SocialAccount
from winclip.publishers.base import (
    AccountStatus,
    AuthExpiredError,
    PublishMeta,
    PublishResult,
    TransientPublishError,
)
from winclip.publishers.registry import clear_custom_publishers, register_publisher
from winclip.worker import queue
from winclip.worker.handlers import handle_job


def _seed(tmp_path: Path, *, platform: str = "youtube", daily_limit_yt: int = 6):
    settings = Settings(
        storage_dir=tmp_path / "storage",
        publish_daily_limit_youtube_api=daily_limit_yt,
        publish_missed_schedule_window_seconds=3600,
    )
    engine = init_db(settings)
    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        proj = Project(id=new_project_id(), workspace_id=ws.id, title="Proyecto", status="ready")
        session.add(proj)
        session.flush()
        clip_rel = f"projects/{proj.id}/clips/c1/clip.mp4"
        clip_path = settings.storage_dir / clip_rel
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        clip_path.write_bytes(b"mp4-bytes")
        clip = Clip(
            id=new_clip_id(),
            project_id=proj.id,
            title="Clip 1",
            status="rendered",
            path=clip_rel,
        )
        acc = SocialAccount(
            id=new_ulid(),
            workspace_id=ws.id,
            platform=platform,
            auth_method="api",
            display_name="Canal Test",
            handle="@canaltest",
            status="connected",
        )
        session.add(clip)
        session.add(acc)
        session.commit()
        return settings, engine, ws.id, proj.id, clip.id, acc.id


def test_publish_worker_happy_path_and_sse_events(tmp_path: Path) -> None:
    settings, engine, ws_id, proj_id, clip_id, acc_id = _seed(tmp_path)
    seen_existing: list[str | None] = []

    class _OkPublisher:
        platform = "youtube"

        def __init__(self, *, on_progress: Any = None, **_kwargs: Any) -> None:
            self.on_progress = on_progress

        def check(self, _account: SocialAccount) -> AccountStatus:
            return AccountStatus(status="connected")

        def publish(self, _clip: Clip, _account: SocialAccount, meta: PublishMeta) -> PublishResult:
            seen_existing.append(meta.existing_external_id)
            if self.on_progress:
                self.on_progress(50.0, "uploading")
            return PublishResult(
                external_id="yt-100",
                external_url="https://www.youtube.com/shorts/yt-100",
                status="published",
                warnings=["aviso menor"],
            )

    clear_custom_publishers()
    register_publisher("youtube", "api", _OkPublisher)
    try:
        with Session(engine) as session:
            pub = Publication(
                id=new_publication_id(),
                workspace_id=ws_id,
                clip_id=clip_id,
                account_id=acc_id,
                status="scheduled",
                meta_json={"title": "Short 1"},
            )
            session.add(pub)
            session.commit()
            pub_id = pub.id

        job = queue.enqueue(
            engine,
            job_type="publish",
            project_id=proj_id,
            payload={"publication_id": pub_id},
        )
        with Session(engine) as session:
            stored_pub = session.get(Publication, pub_id)
            assert stored_pub is not None
            stored_pub.job_id = job.id
            session.add(stored_pub)
            session.commit()

        claimed = queue.claim_next(engine, worker_id="w1", light_running=0, light_limit=2)
        assert claimed is not None
        final_job = handle_job(engine, claimed.id, settings=settings)
        assert final_job.status == "done"

        with Session(engine) as session:
            updated = session.get(Publication, pub_id)
            assert updated is not None
            assert updated.status == "published"
            assert updated.external_id == "yt-100"
            assert updated.external_url == "https://www.youtube.com/shorts/yt-100"
            assert updated.warnings_json == ["aviso menor"]
            assert updated.attempts == 1

        events = queue.list_events(engine, project_id=proj_id)
        assert any(e.event_type == "publication.updated" for e in events)
        assert seen_existing == [None]
    finally:
        clear_custom_publishers()


def test_publish_worker_retries_transient_error_with_backoff_and_preserves_external_id(
    tmp_path: Path,
) -> None:
    settings, engine, ws_id, proj_id, clip_id, acc_id = _seed(tmp_path)

    class _TransientPublisher:
        platform = "youtube"

        def __init__(self, **_kwargs: Any) -> None:
            pass

        def check(self, _account: SocialAccount) -> AccountStatus:
            return AccountStatus(status="connected")

        def publish(
            self, _clip: Clip, _account: SocialAccount, _meta: PublishMeta
        ) -> PublishResult:
            raise TransientPublishError("503 temporal", external_id="yt-partial")

    clear_custom_publishers()
    register_publisher("youtube", "api", _TransientPublisher)
    try:
        with Session(engine) as session:
            pub = Publication(
                id=new_publication_id(),
                workspace_id=ws_id,
                clip_id=clip_id,
                account_id=acc_id,
                status="scheduled",
                meta_json={"title": "Retry me"},
            )
            session.add(pub)
            session.commit()
            pub_id = pub.id

        queue.enqueue(
            engine,
            job_type="publish",
            project_id=proj_id,
            payload={"publication_id": pub_id},
            max_attempts=3,
        )
        claimed = queue.claim_next(engine, worker_id="w1", light_running=0, light_limit=2)
        assert claimed is not None
        retried = handle_job(engine, claimed.id, settings=settings)
        assert retried.status == "queued"
        assert retried.next_run_at is not None

        with Session(engine) as session:
            stored = session.get(Publication, pub_id)
            assert stored is not None
            assert stored.status == "scheduled"
            assert stored.external_id == "yt-partial"
            assert stored.error_code == "transient_error"
    finally:
        clear_custom_publishers()


def test_publish_worker_permanent_auth_error_marks_account_expired_without_retry(
    tmp_path: Path,
) -> None:
    settings, engine, ws_id, proj_id, clip_id, acc_id = _seed(tmp_path)

    class _AuthFailPublisher:
        platform = "youtube"

        def __init__(self, **_kwargs: Any) -> None:
            pass

        def check(self, _account: SocialAccount) -> AccountStatus:
            return AccountStatus(status="expired")

        def publish(
            self, _clip: Clip, _account: SocialAccount, _meta: PublishMeta
        ) -> PublishResult:
            raise AuthExpiredError("token revocado")

    clear_custom_publishers()
    register_publisher("youtube", "api", _AuthFailPublisher)
    try:
        with Session(engine) as session:
            pub = Publication(
                id=new_publication_id(),
                workspace_id=ws_id,
                clip_id=clip_id,
                account_id=acc_id,
                status="scheduled",
                meta_json={"title": "Auth fail"},
            )
            session.add(pub)
            session.commit()
            pub_id = pub.id

        queue.enqueue(
            engine,
            job_type="publish",
            project_id=proj_id,
            payload={"publication_id": pub_id},
            max_attempts=3,
        )
        claimed = queue.claim_next(engine, worker_id="w1", light_running=0, light_limit=2)
        assert claimed is not None
        final = handle_job(engine, claimed.id, settings=settings)
        assert final.status == "failed"

        with Session(engine) as session:
            stored = session.get(Publication, pub_id)
            acc = session.get(SocialAccount, acc_id)
            assert stored is not None and stored.status == "failed"
            assert stored.error_code == "session_expired"
            assert acc is not None and acc.status == "expired"
    finally:
        clear_custom_publishers()


def test_publish_worker_rejects_missed_schedule_window_and_daily_limit(tmp_path: Path) -> None:
    settings, engine, ws_id, proj_id, clip_id, acc_id = _seed(tmp_path, daily_limit_yt=1)

    with Session(engine) as session:
        # Publicación ya existente hoy (consume límite diario 1/1)
        session.add(
            Publication(
                id=new_publication_id(),
                workspace_id=ws_id,
                clip_id=clip_id,
                account_id=acc_id,
                status="published",
                meta_json={"title": "Previa"},
            )
        )
        pub_missed = Publication(
            id=new_publication_id(),
            workspace_id=ws_id,
            clip_id=clip_id,
            account_id=acc_id,
            status="scheduled",
            meta_json={"title": "Tarde"},
        )
        pub_limit = Publication(
            id=new_publication_id(),
            workspace_id=ws_id,
            clip_id=clip_id,
            account_id=acc_id,
            status="scheduled",
            meta_json={"title": "Limite"},
        )
        session.add(pub_missed)
        session.add(pub_limit)
        session.commit()
        missed_id, limit_id = pub_missed.id, pub_limit.id

    # 1. Ventana de programación perdida (3 horas tarde > 1h configurada)
    queue.enqueue(
        engine,
        job_type="publish",
        project_id=proj_id,
        payload={"publication_id": missed_id},
        run_at=datetime.now(UTC) - timedelta(hours=3),
    )
    claimed_missed = queue.claim_next(engine, worker_id="w1", light_running=0, light_limit=2)
    assert claimed_missed is not None
    res_missed = handle_job(engine, claimed_missed.id, settings=settings)
    assert res_missed.status == "failed"

    with Session(engine) as session:
        stored_missed = session.get(Publication, missed_id)
        assert stored_missed is not None
        assert stored_missed.error_code == "missed_schedule_window"

    # 2. Límite diario excedido
    queue.enqueue(
        engine,
        job_type="publish",
        project_id=proj_id,
        payload={"publication_id": limit_id},
    )
    claimed_limit = queue.claim_next(engine, worker_id="w1", light_running=0, light_limit=2)
    assert claimed_limit is not None
    res_limit = handle_job(engine, claimed_limit.id, settings=settings)
    assert res_limit.status == "failed"

    with Session(engine) as session:
        stored_limit = session.get(Publication, limit_id)
        assert stored_limit is not None
        assert stored_limit.error_code == "daily_limit_exceeded"
