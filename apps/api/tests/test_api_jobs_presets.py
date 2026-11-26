"""Tests de `/api/jobs`, `/api/presets` y del contrato OpenAPI."""

from __future__ import annotations

from api_helpers import seed_project
from fastapi.testclient import TestClient

from winclip.core.models import Project
from winclip.pipeline.subtitles.presets import list_presets, load_preset
from winclip.worker import queue

EXPECTED_OPERATION_IDS = {
    ("/api/health", "get"): "getHealth",
    ("/api/projects", "post"): "createProject",
    ("/api/projects", "get"): "listProjects",
    ("/api/projects/{project_id}", "get"): "getProject",
    ("/api/projects/{project_id}", "delete"): "deleteProject",
    ("/api/projects/{project_id}/clips", "get"): "listProjectClips",
    ("/api/clips/{clip_id}", "patch"): "updateClip",
    ("/api/clips/{clip_id}", "delete"): "deleteClip",
    ("/api/clips/{clip_id}/rerender", "post"): "rerenderClip",
    ("/api/clips/{clip_id}/file", "get"): "getClipFile",
    ("/api/clips/{clip_id}/thumb", "get"): "getClipThumb",
    ("/api/presets", "get"): "listSubtitlePresets",
    ("/api/jobs/{job_id}", "get"): "getJob",
    ("/api/jobs/{job_id}/cancel", "post"): "cancelJob",
    ("/api/events", "get"): "streamEvents",
}


def test_get_job_returns_full_state(api_client: TestClient) -> None:
    project = seed_project(api_client.app.state.engine)
    job = queue.enqueue(api_client.app.state.engine, job_type="pipeline", project_id=project.id)

    response = api_client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job.id
    assert body["project_id"] == project.id
    assert body["type"] == "pipeline"
    assert body["status"] == "queued"
    assert body["progress"] == 0
    assert body["stage"] == "queued"
    assert body["attempts"] == 0
    assert body["max_attempts"] == 3
    assert body["error"] is None
    assert body["created_at"] and body["updated_at"]
    assert api_client.get("/api/jobs/no-existe").status_code == 404


def test_cancel_queued_job_returns_updated_job(api_client: TestClient) -> None:
    project = seed_project(api_client.app.state.engine)
    job = queue.enqueue(api_client.app.state.engine, job_type="ingest", project_id=project.id)

    response = api_client.post(f"/api/jobs/{job.id}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["finished_at"] is not None


def test_cancel_running_job_requests_stop(api_client: TestClient) -> None:
    project = seed_project(api_client.app.state.engine)
    job = queue.enqueue(api_client.app.state.engine, job_type="render", project_id=project.id)
    claimed = queue.claim_next(
        api_client.app.state.engine, worker_id="w", light_running=0, light_limit=2
    )
    assert claimed is not None

    response = api_client.post(f"/api/jobs/{job.id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert queue.is_cancel_requested(api_client.app.state.engine, job.id) is True


def test_cancel_terminal_job_returns_conflict(api_client: TestClient) -> None:
    project = seed_project(api_client.app.state.engine)
    job = queue.enqueue(api_client.app.state.engine, job_type="ingest", project_id=project.id)
    queue.complete_job(api_client.app.state.engine, job.id)

    response = api_client.post(f"/api/jobs/{job.id}/cancel")

    assert response.status_code == 409
    assert "finalizó" in response.json()["detail"]
    assert api_client.post("/api/jobs/no-existe/cancel").status_code == 404


def test_presets_catalog_matches_assets(api_client: TestClient) -> None:
    response = api_client.get("/api/presets")

    assert response.status_code == 200
    body = response.json()
    assert [preset["id"] for preset in body] == list_presets()
    assert set(preset["id"] for preset in body) == {
        "bold-yellow",
        "hormozi",
        "clean-white",
        "mrbeast",
    }
    by_id = {preset["id"]: preset for preset in body}
    for preset_id in list_presets():
        source = load_preset(preset_id)
        assert by_id[preset_id]["font"] == source.font
        assert by_id[preset_id]["primary_color"] == source.primary_color
        assert by_id[preset_id]["highlight_color"] == source.highlight_color
        assert by_id[preset_id]["font_size"] == source.font_size
        assert 0.62 <= by_id[preset_id]["y_pct"] <= 0.70


def test_openapi_has_stable_unique_operation_ids(api_client: TestClient) -> None:
    spec = api_client.get("/openapi.json").json()

    found: dict[tuple[str, str], str | None] = {}
    for path, operations in spec["paths"].items():
        if not path.startswith("/api"):
            continue
        for method, operation in operations.items():
            if method in {"parameters", "summary", "description"}:
                continue
            found[(path, method)] = operation.get("operationId")

    assert found == EXPECTED_OPERATION_IDS
    ids = list(found.values())
    assert len(ids) == len(set(ids))
    for operation_id in ids:
        assert operation_id
        assert "_api_" not in operation_id
        assert "_projects_", "_clips_" not in operation_id


def test_openapi_documents_both_create_project_content_types(api_client: TestClient) -> None:
    spec = api_client.get("/openapi.json").json()

    content = spec["paths"]["/api/projects"]["post"]["requestBody"]["content"]

    assert "application/json" in content
    assert "multipart/form-data" in content
    assert content["multipart/form-data"]["schema"]["properties"]["file"]["format"] == "binary"
    enum = content["application/json"]["schema"]["properties"]["reframe_mode"]["enum"]
    assert enum == ["face", "center", "blur", "passthrough"]


def test_project_reframe_mode_roundtrip(api_client: TestClient) -> None:
    for mode in ("face", "center", "blur", "passthrough"):
        response = api_client.post(
            "/api/projects",
            json={"source_url": f"https://example.com/{mode}", "reframe_mode": mode},
        )
        assert response.status_code == 201, mode
        project_id = response.json()["project"]["id"]
        assert api_client.get(f"/api/projects/{project_id}").json()["reframe_mode"] == mode

    with api_client.app.state.engine.connect() as connection:
        assert connection.execute(Project.__table__.select()).rowcount != 0
