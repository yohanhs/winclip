"""Tests de `/api/projects`."""

from __future__ import annotations

from pathlib import Path

from api_helpers import seed_clip
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from winclip.core.config import Settings
from winclip.core.models import Clip, Job, Project
from winclip.core.storage import LocalStorage
from winclip.main import create_app

PAYLOAD = {
    "source_url": "https://example.com/video",
    "requested_clips": 5,
    "language": "es",
    "subtitle_preset": "hormozi",
    "reframe_mode": "blur",
}


def test_create_project_from_url(api_client: TestClient) -> None:
    response = api_client.post("/api/projects", json=PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    project = body["project"]
    job = body["job"]
    assert project["source_type"] == "url"
    assert project["source_url"] == PAYLOAD["source_url"]
    assert project["requested_clips"] == 5
    assert project["language"] == "es"
    assert project["subtitle_preset"] == "hormozi"
    assert project["reframe_mode"] == "blur"
    assert project["status"] == "queued"
    assert project["clips_count"] == 0
    assert job["type"] == "pipeline"
    assert job["status"] == "queued"
    assert job["project_id"] == project["id"]
    assert job["progress"] == 0


def test_create_project_with_max_clips(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/projects",
        json={"source_url": "https://example.com/v", "requested_clips": "max"},
    )

    assert response.status_code == 201
    assert response.json()["project"]["requested_clips"] is None


def test_create_project_rejects_invalid_input(api_client: TestClient) -> None:
    cases = [
        {"requested_clips": 5},
        {"source_url": "https://example.com/v", "requested_clips": 0},
        {"source_url": "https://example.com/v", "language": "fr"},
        {"source_url": "no-es-una-url"},
        {"source_url": "https://example.com/v", "reframe_mode": "zoom"},
        {"source_url": "https://example.com/v", "subtitle_preset": "no-existe"},
    ]
    for payload in cases:
        response = api_client.post("/api/projects", json=payload)
        assert response.status_code in {400, 422}, payload

    with Session(api_client.app.state.engine) as session:
        assert session.exec(select(Project)).all() == []


def test_create_project_upload_streams_file_to_storage(
    api_client: TestClient, api_settings: Settings
) -> None:
    video = b"\x00\x00\x00\x18ftypmp42" + b"video" * 50_000

    response = api_client.post(
        "/api/projects",
        data={"requested_clips": "3", "language": "en", "title": "Mi subida"},
        files={"file": ("grabacion.mp4", video, "video/mp4")},
    )

    assert response.status_code == 201
    project = response.json()["project"]
    assert project["source_type"] == "file"
    assert project["requested_clips"] == 3
    assert project["language"] == "en"
    assert project["title"] == "Mi subida"

    stored = LocalStorage(api_settings.storage_dir).source_dir(project["id"]) / "original.mp4"
    assert stored.is_file()
    assert stored.read_bytes() == video


def test_upload_rejects_bad_extension_and_cleans_up(
    api_client: TestClient, api_settings: Settings
) -> None:
    response = api_client.post(
        "/api/projects",
        data={"requested_clips": "2"},
        files={"file": ("notas.txt", b"hola", "text/plain")},
    )

    assert response.status_code == 400
    projects_dir = api_settings.storage_dir / "projects"
    assert not projects_dir.exists() or list(projects_dir.iterdir()) == []


def test_upload_rejects_empty_file(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/projects",
        data={"requested_clips": "2"},
        files={"file": ("vacio.mp4", b"", "video/mp4")},
    )

    assert response.status_code == 400


def test_upload_rejects_file_over_limit(api_settings: Settings) -> None:
    limited = api_settings.model_copy(update={"upload_max_bytes": 1024})
    with TestClient(create_app(limited)) as client:
        response = client.post(
            "/api/projects",
            data={"requested_clips": "2"},
            files={"file": ("grande.mp4", b"x" * 5000, "video/mp4")},
        )

    assert response.status_code == 413


def test_upload_requires_file_part(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/projects",
        data={"requested_clips": "2"},
        files={"campo": (None, "sin archivo")},
    )

    assert response.status_code == 422


def test_list_projects_orders_newest_first(api_client: TestClient) -> None:
    first = api_client.post("/api/projects", json={"source_url": "https://example.com/a"}).json()
    second = api_client.post("/api/projects", json={"source_url": "https://example.com/b"}).json()

    response = api_client.get("/api/projects")

    assert response.status_code == 200
    ids = [project["id"] for project in response.json()]
    assert ids == [second["project"]["id"], first["project"]["id"]]
    assert all(project["clips_count"] == 0 for project in response.json())


def test_get_project_detail_and_404(api_client: TestClient) -> None:
    project_id = api_client.post("/api/projects", json=PAYLOAD).json()["project"]["id"]

    response = api_client.get(f"/api/projects/{project_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == project_id
    assert len(body["jobs"]) == 1
    assert body["latest_job"]["type"] == "pipeline"

    assert api_client.get("/api/projects/no-existe").status_code == 404


def test_delete_project_removes_rows_and_directory(
    api_client: TestClient, api_settings: Settings
) -> None:
    project_id = api_client.post("/api/projects", json=PAYLOAD).json()["project"]["id"]
    storage = LocalStorage(api_settings.storage_dir)
    seed_clip(api_client.app.state.engine, storage, project_id)
    assert storage.project_dir(project_id).is_dir()

    response = api_client.delete(f"/api/projects/{project_id}")

    assert response.status_code == 204
    assert not storage.project_dir(project_id).exists()
    with Session(api_client.app.state.engine) as session:
        assert session.get(Project, project_id) is None
        assert session.exec(select(Clip).where(Clip.project_id == project_id)).all() == []
        assert session.exec(select(Job).where(Job.project_id == project_id)).all() == []
    assert api_client.get(f"/api/projects/{project_id}").status_code == 404
    assert api_client.delete("/api/projects/no-existe").status_code == 404


def test_project_paths_are_safe(api_settings: Settings) -> None:
    """La ruta guardada nunca sale de `STORAGE_DIR` (comprobación del helper)."""
    storage = LocalStorage(api_settings.storage_dir)
    assert storage.resolve_safe("projects/p/clips/c/clip.mp4").is_relative_to(storage.root)
    assert Path(storage.root).name == "storage"
