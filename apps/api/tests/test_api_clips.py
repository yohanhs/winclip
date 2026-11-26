"""Tests de `/api/clips`: edición, Range, path traversal, borrado y re-render."""

from __future__ import annotations

from api_helpers import seed_clip, seed_project
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from winclip.core.models import Clip, Job
from winclip.core.storage import LocalStorage


def _seed(api_client: TestClient, api_settings) -> tuple[object, object, LocalStorage]:
    storage = LocalStorage(api_settings.storage_dir)
    project = seed_project(api_client.app.state.engine, storage=storage)
    clip = seed_clip(api_client.app.state.engine, storage, project.id, score=90)
    return project, clip, storage


def test_list_project_clips_sorted_by_score(api_client: TestClient, api_settings) -> None:
    storage = LocalStorage(api_settings.storage_dir)
    project = seed_project(api_client.app.state.engine, storage=storage)
    low = seed_clip(api_client.app.state.engine, storage, project.id, title="Bajo", score=10)
    high = seed_clip(api_client.app.state.engine, storage, project.id, title="Alto", score=99)

    response = api_client.get(f"/api/projects/{project.id}/clips")

    assert response.status_code == 200
    body = response.json()
    assert [clip["title"] for clip in body] == ["Alto", "Bajo"]
    assert body[0]["id"] == high.id
    assert body[0]["video_url"] == f"/api/clips/{high.id}/file"
    assert body[0]["thumb_url"] == f"/api/clips/{high.id}/thumb"
    assert body[1]["id"] == low.id
    assert api_client.get("/api/projects/no-existe/clips").status_code == 404


def test_patch_clip_updates_metadata_times_and_candidate(
    api_client: TestClient, api_settings
) -> None:
    _project, clip, _storage = _seed(api_client, api_settings)

    response = api_client.patch(
        f"/api/clips/{clip.id}",
        json={
            "title": "Nuevo título",
            "description": "Otra descripción",
            "hashtags": ["shorts", "#viral"],
            "start_sec": 2.5,
            "end_sec": 40.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Nuevo título"
    assert body["hashtags"] == ["#shorts", "#viral"]
    assert body["start_sec"] == 2.5
    assert body["end_sec"] == 40.0
    assert body["duration"] == 37.5

    with Session(api_client.app.state.engine) as session:
        stored = session.get(Clip, clip.id)
    assert stored is not None
    assert stored.candidate["start"] == 2.5
    assert stored.candidate["end"] == 40.0
    assert stored.candidate["title"] == "Nuevo título"


def test_patch_clip_rejects_invalid_times(api_client: TestClient, api_settings) -> None:
    _project, clip, _storage = _seed(api_client, api_settings)

    for payload in (
        {"start_sec": 10.0, "end_sec": 10.0},
        {"start_sec": 20.0, "end_sec": 5.0},
        {"start_sec": -1.0},
        {"end_sec": -0.5},
    ):
        response = api_client.patch(f"/api/clips/{clip.id}", json=payload)
        assert response.status_code == 422, payload

    with Session(api_client.app.state.engine) as session:
        stored = session.get(Clip, clip.id)
    assert stored is not None
    assert stored.start_sec == 1.0
    assert stored.end_sec == 31.0


def test_get_clip_file_supports_range(api_client: TestClient, api_settings) -> None:
    _project, clip, storage = _seed(api_client, api_settings)
    path = storage.clip_dir(_project.id, clip.id) / "clip.mp4"
    size = path.stat().st_size

    full = api_client.get(f"/api/clips/{clip.id}/file")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["content-length"] == str(size)
    assert len(full.content) == size

    partial = api_client.get(f"/api/clips/{clip.id}/file", headers={"Range": "bytes=0-1023"})
    assert partial.status_code == 206
    assert partial.headers["content-range"] == f"bytes 0-1023/{size}"
    assert partial.headers["accept-ranges"] == "bytes"
    assert partial.content == path.read_bytes()[:1024]

    suffix = api_client.get(f"/api/clips/{clip.id}/file", headers={"Range": "bytes=-10"})
    assert suffix.status_code == 206
    assert suffix.content == path.read_bytes()[-10:]


def test_get_clip_file_rejects_invalid_range(api_client: TestClient, api_settings) -> None:
    _project, clip, storage = _seed(api_client, api_settings)
    size = (storage.clip_dir(_project.id, clip.id) / "clip.mp4").stat().st_size

    response = api_client.get(
        f"/api/clips/{clip.id}/file", headers={"Range": f"bytes={size + 100}-"}
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{size}"

    malformed = api_client.get(f"/api/clips/{clip.id}/file", headers={"Range": "bytes=abc"})
    assert malformed.status_code == 416


def test_thumb_sets_cache_headers(api_client: TestClient, api_settings) -> None:
    _project, clip, _storage = _seed(api_client, api_settings)

    response = api_client.get(f"/api/clips/{clip.id}/thumb")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "max-age" in response.headers["cache-control"]


def test_media_blocks_path_traversal(api_client: TestClient, api_settings) -> None:
    _project, _clip, storage = _seed(api_client, api_settings)
    project = seed_project(api_client.app.state.engine, storage=storage)
    evil = seed_clip(
        api_client.app.state.engine,
        storage,
        project.id,
        with_files=False,
        path_override="../../etc/passwd",
    )

    response = api_client.get(f"/api/clips/{evil.id}/file")

    assert response.status_code == 403


def test_media_returns_404_without_file(api_client: TestClient, api_settings) -> None:
    storage = LocalStorage(api_settings.storage_dir)
    project = seed_project(api_client.app.state.engine, storage=storage)
    draft = seed_clip(api_client.app.state.engine, storage, project.id, with_files=False)

    assert api_client.get(f"/api/clips/{draft.id}/file").status_code == 404
    assert api_client.get(f"/api/clips/{draft.id}/thumb").status_code == 404
    assert api_client.get("/api/clips/no-existe/file").status_code == 404


def test_delete_clip_removes_only_that_clip(api_client: TestClient, api_settings) -> None:
    project, clip, storage = _seed(api_client, api_settings)
    other = seed_clip(api_client.app.state.engine, storage, project.id, title="Otro")

    response = api_client.delete(f"/api/clips/{clip.id}")

    assert response.status_code == 204
    assert not storage.clip_dir(project.id, clip.id).exists()
    assert storage.clip_dir(project.id, other.id).is_dir()
    assert api_client.get(f"/api/clips/{clip.id}/file").status_code == 404


def test_rerender_enqueues_render_job(api_client: TestClient, api_settings) -> None:
    project, clip, _storage = _seed(api_client, api_settings)

    response = api_client.post(f"/api/clips/{clip.id}/rerender")

    assert response.status_code == 202
    body = response.json()
    assert body["type"] == "render"
    assert body["status"] == "queued"
    assert body["project_id"] == project.id
    assert body["payload"]["clip_id"] == clip.id

    with Session(api_client.app.state.engine) as session:
        stored = session.get(Clip, clip.id)
        jobs = session.exec(select(Job).where(Job.project_id == project.id)).all()
    assert stored is not None and stored.status == "rendering"
    assert [job.type for job in jobs] == ["render"]
    assert api_client.post("/api/clips/no-existe/rerender").status_code == 404
