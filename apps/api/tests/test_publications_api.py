"""Tests del router REST `/api/publications` (`task 4.2`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from winclip.core.config import Settings
from winclip.core.db import ensure_default_workspace
from winclip.core.ids import new_clip_id, new_project_id, new_ulid
from winclip.core.models import Campaign, Clip, Job, Project, Publication, SocialAccount
from winclip.main import create_app


def _seed_api(tmp_path: Path):
    settings = Settings(storage_dir=tmp_path / "storage")
    app = create_app(settings)
    client = TestClient(app)
    client.__enter__()
    engine = app.state.engine

    with Session(engine) as session:
        ws = ensure_default_workspace(session)
        camp = Campaign(
            id=new_ulid(),
            workspace_id=ws.id,
            name="Campaña Test",
            rules_json={
                "name": "Campaña Test",
                "language": "es",
                "cta_text": "Sigue para más",
                "hashtags": ["#growth"],
            },
        )
        session.add(camp)
        session.flush()

        proj = Project(
            id=new_project_id(),
            workspace_id=ws.id,
            campaign_id=camp.id,
            title="Podcast Episodio 1",
            status="ready",
            language="es",
        )
        session.add(proj)
        session.flush()

        clips = []
        for idx in range(2):
            cid = new_clip_id()
            rel = f"projects/{proj.id}/clips/{cid}/clip.mp4"
            p = settings.storage_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"mp4-bytes")
            clip = Clip(
                id=cid,
                project_id=proj.id,
                title=f"Clip ganador {idx + 1}",
                description="Descripción útil",
                hashtags=["#clips"],
                status="rendered",
                path=rel,
            )
            session.add(clip)
            clips.append(clip)

        yt = SocialAccount(
            id=new_ulid(),
            workspace_id=ws.id,
            platform="youtube",
            auth_method="api",
            display_name="Canal YT",
            handle="@canalyt",
            status="connected",
            is_default=True,
        )
        tt = SocialAccount(
            id=new_ulid(),
            workspace_id=ws.id,
            platform="tiktok",
            auth_method="api",
            display_name="Cuenta TT",
            handle="@cuentatt",
            status="connected",
            capabilities_json={"direct_post": False},
        )
        ig_pw = SocialAccount(
            id=new_ulid(),
            workspace_id=ws.id,
            platform="instagram",
            auth_method="playwright",
            display_name="Cuenta IG",
            handle="@cuentaig",
            status="connected",
        )
        session.add(yt)
        session.add(tt)
        session.add(ig_pw)
        session.commit()
        return client, settings, engine, proj.id, [c.id for c in clips], yt.id, tt.id, ig_pw.id


def test_preview_meta_matrix_and_warnings(tmp_path: Path) -> None:
    client, _settings, _engine, _proj_id, clip_ids, yt_id, tt_id, ig_id = _seed_api(tmp_path)
    try:
        resp = client.post(
            "/api/publications/preview-meta",
            json={"clip_ids": clip_ids, "account_ids": [yt_id, tt_id, ig_id]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 6
        assert any("Inbox" in w for w in data["warnings"])
        assert any("Playwright" in w for w in data["warnings"])
        assert data["quota"]["youtube_units_limit"] == 10000
    finally:
        client.__exit__(None, None, None)


def test_create_matrix_duplicate_409_cancel_retry_and_screenshot(tmp_path: Path) -> None:
    client, settings, engine, proj_id, clip_ids, yt_id, tt_id, _ig_id = _seed_api(tmp_path)
    try:
        future = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
        payload = {
            "items": [
                {
                    "clip_id": clip_ids[0],
                    "account_id": yt_id,
                    "meta": {"title": "Short 1 #Shorts", "description": "Desc"},
                    "scheduled_at": future,
                },
                {
                    "clip_id": clip_ids[0],
                    "account_id": tt_id,
                    "meta": {"caption": "TikTok 1"},
                    "scheduled_at": future,
                },
            ],
            "force": False,
        }
        create_resp = client.post("/api/publications", json=payload)
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert len(created) == 2

        yt_pub = next(p for p in created if p["account_id"] == yt_id)
        tt_pub = next(p for p in created if p["account_id"] == tt_id)
        assert tt_pub["delivery_mode"] == "inbox"

        # YouTube API programa en servidor (job.run_at is None); TikTok difiere con run_at
        with Session(engine) as session:
            yt_job = session.get(Job, yt_pub["job_id"])
            tt_job = session.get(Job, tt_pub["job_id"])
            assert yt_job is not None and yt_job.run_at is None
            assert tt_job is not None and tt_job.run_at is not None

        # Duplicado activo sin force=true -> 409
        dup_resp = client.post("/api/publications", json=payload)
        assert dup_resp.status_code == 409

        # Filtrar por proyecto y plataforma
        list_resp = client.get(f"/api/publications?project_id={proj_id}&platform=tiktok")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        # Cancelar publicación programada de TikTok
        cancel_resp = client.post(f"/api/publications/{tt_pub['id']}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

        # Simular fallo con captura diagnóstica en yt_pub y probar screenshot + retry
        shot_rel = f"publications/{yt_pub['id']}/steps/01_error.png"
        shot_file = settings.storage_dir / shot_rel
        shot_file.parent.mkdir(parents=True, exist_ok=True)
        shot_file.write_bytes(b"\x89PNG\r\n\x1a\nfake-png")
        with Session(engine) as session:
            pub_db = session.get(Publication, yt_pub["id"])
            assert pub_db is not None
            pub_db.status = "failed"
            pub_db.error = "Fallo simulado"
            pub_db.error_code = "challenge_required"
            pub_db.external_id = "yt-already-uploaded"
            pub_db.screenshot_path = shot_rel
            session.add(pub_db)
            session.commit()

        detail_resp = client.get(f"/api/publications/{yt_pub['id']}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["step_screenshots"] == ["01_error.png"]

        shot_resp = client.get(f"/api/publications/{yt_pub['id']}/screenshot")
        assert shot_resp.status_code == 200
        assert shot_resp.headers["content-type"] == "image/png"

        retry_resp = client.post(f"/api/publications/{yt_pub['id']}/retry")
        assert retry_resp.status_code == 200
        retried = retry_resp.json()
        assert retried["status"] == "scheduled"
        assert retried["external_id"] == "yt-already-uploaded"

        # Quota endpoint
        quota_resp = client.get("/api/publications/quota")
        assert quota_resp.status_code == 200
        assert quota_resp.json()["youtube_units_used"] == 1600
    finally:
        client.__exit__(None, None, None)


def test_create_rejects_youtube_title_over_100_chars(tmp_path: Path) -> None:
    client, _settings, _engine, _proj_id, clip_ids, yt_id, _tt_id, _ig_id = _seed_api(tmp_path)
    try:
        resp = client.post(
            "/api/publications",
            json={
                "items": [
                    {
                        "clip_id": clip_ids[0],
                        "account_id": yt_id,
                        "meta": {"title": "a" * 101},
                    }
                ]
            },
        )
        assert resp.status_code == 422
    finally:
        client.__exit__(None, None, None)
