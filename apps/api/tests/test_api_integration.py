"""Prueba integrada de extremo a extremo: API real + worker con pipeline mockeado."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fake_pipeline import FakePipeline
from fastapi.testclient import TestClient
from test_api_events import _events

from winclip.core.storage import LocalStorage
from winclip.worker.runner import WorkerRunner


def _wait_job(client: TestClient, job_id: str, status: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = client.get(f"/api/jobs/{job_id}").json()
        if last.get("status") == status:
            return last
        if last.get("status") in {"failed", "cancelled"}:
            raise AssertionError(
                f"trabajo {job_id} terminó en {last['status']}: {last.get('error')}"
            )
        time.sleep(0.05)
    raise AssertionError(f"el trabajo {job_id} no llegó a {status}: {last}")


def test_end_to_end_pipeline_edit_rerender_range_and_delete(
    api_client: TestClient, api_settings
) -> None:
    storage = LocalStorage(api_settings.storage_dir)
    created = api_client.post(
        "/api/projects",
        json={
            "source_url": "https://example.com/directo",
            "requested_clips": 2,
            "language": "es",
            "subtitle_preset": "mrbeast",
            "reframe_mode": "center",
        },
    )
    assert created.status_code == 201
    project = created.json()["project"]
    pipeline_job = created.json()["job"]

    settings = api_client.app.state.settings.model_copy(update={"worker_poll_interval": 0.05})
    runner = WorkerRunner(
        api_client.app.state.engine,
        settings,
        backends=FakePipeline(storage, candidate_count=2).backends(),
    )
    stop = threading.Event()
    thread = threading.Thread(target=runner.run, args=(stop,), daemon=True)
    thread.start()
    try:
        # 1. El pipeline termina y el proyecto queda listo.
        assert _wait_job(api_client, pipeline_job["id"], "done")["progress"] == 100
        detail = api_client.get(f"/api/projects/{project['id']}").json()
        assert detail["status"] == "ready"
        assert detail["clips_count"] == 2

        # 2. SSE entrega el backlog con los clips listos y el job.done.
        received: list[dict] = []
        for event in _events(api_client, f"/api/events?project_id={project['id']}"):
            received.append(event)
            if event["event"] == "job.done":
                break
        assert sum(event["event"] == "clip.ready" for event in received) == 2
        assert received[-1]["data"]["status"] == "done"

        # 3. Los clips se listan con URLs de media.
        clips = api_client.get(f"/api/projects/{project['id']}/clips").json()
        assert len(clips) == 2
        assert all(clip["status"] == "rendered" for clip in clips)
        clip = clips[0]
        assert clip["video_url"] == f"/api/clips/{clip['id']}/file"

        # 4. Edición de metadatos y tiempos.
        edited = api_client.patch(
            f"/api/clips/{clip['id']}",
            json={"title": "Editado en la UI", "hashtags": ["#winclip"], "start_sec": 5.0},
        )
        assert edited.status_code == 200
        assert edited.json()["title"] == "Editado en la UI"
        assert edited.json()["hashtags"] == ["#winclip"]

        # 5. Re-render con los tiempos editados.
        rerender = api_client.post(f"/api/clips/{clip['id']}/rerender")
        assert rerender.status_code == 202
        _wait_job(api_client, rerender.json()["id"], "done")
        document = storage.read_json(storage.selection_path(project["id"]))
        assert any(item["start"] == 5.0 for item in document["candidates"])

        # 6. Entrega con Range.
        media = api_client.get(f"/api/clips/{clip['id']}/file", headers={"Range": "bytes=0-99"})
        assert media.status_code == 206
        assert media.headers["content-range"].startswith("bytes 0-99/")
        assert len(media.content) == 100

        # 7. Borrado completo.
        assert api_client.delete(f"/api/projects/{project['id']}").status_code == 204
        assert not storage.project_dir(project["id"]).exists()
        assert api_client.get(f"/api/projects/{project['id']}").status_code == 404
        assert api_client.get(f"/api/clips/{clip['id']}/file").status_code == 404
    finally:
        stop.set()
        thread.join(timeout=10)

    assert not thread.is_alive()
    assert isinstance(api_settings.storage_dir, Path)
