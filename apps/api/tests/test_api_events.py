"""Tests del stream SSE (`/api/events`)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from api_helpers import seed_project
from fastapi.testclient import TestClient

from winclip.worker import queue


def _events(
    client: TestClient, url: str, *, headers: dict[str, str] | None = None
) -> Iterator[dict]:
    """Itera eventos SSE ya parseados (id, event, data)."""
    with client.stream("GET", url, headers=headers or {}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        current: dict[str, Any] = {}
        for line in response.iter_lines():
            if not line:
                if current:
                    yield current
                    current = {}
                continue
            if line.startswith("id: "):
                current["id"] = int(line[4:])
            elif line.startswith("event: "):
                current["event"] = line[7:]
            elif line.startswith("data: "):
                current["data"] = json.loads(line[6:])
        if current:
            yield current


def _take(iterator: Iterator[dict], count: int, timeout: float = 5.0) -> list[dict]:
    taken: list[dict] = []
    deadline = time.monotonic() + timeout
    for event in iterator:
        taken.append(event)
        if len(taken) >= count or time.monotonic() > deadline:
            break
    return taken


def test_stream_delivers_progress_and_clip_ready(api_client: TestClient) -> None:
    engine = api_client.app.state.engine
    project = seed_project(engine)
    queue.emit_event(
        engine,
        event_type="job.progress",
        project_id=project.id,
        job_id="job-1",
        payload={
            "job_id": "job-1",
            "project_id": project.id,
            "type": "pipeline",
            "status": "running",
            "progress": 42,
            "stage": "transcribe",
        },
    )
    queue.emit_event(
        engine,
        event_type="clip.ready",
        project_id=project.id,
        job_id="job-1",
        payload={
            "project_id": project.id,
            "job_id": "job-1",
            "clip_id": "clip-1",
            "status": "rendered",
            "thumb_url": "/api/clips/clip-1/thumb",
            "video_url": "/api/clips/clip-1/file",
        },
    )

    events = _take(_events(api_client, f"/api/events?project_id={project.id}"), 2)

    assert [event["event"] for event in events] == ["job.progress", "clip.ready"]
    assert events[0]["data"]["stage"] == "transcribe"
    assert events[0]["data"]["progress"] == 42
    assert events[1]["data"]["video_url"] == "/api/clips/clip-1/file"
    assert events[0]["id"] < events[1]["id"]


def test_stream_emits_live_events_while_connected(api_client: TestClient) -> None:
    engine = api_client.app.state.engine
    project = seed_project(engine)

    with api_client.stream("GET", f"/api/events?project_id={project.id}") as response:
        stream = response.iter_lines()
        queue.emit_event(
            engine,
            event_type="job.done",
            project_id=project.id,
            job_id="job-2",
            payload={
                "job_id": "job-2",
                "project_id": project.id,
                "type": "pipeline",
                "status": "done",
                "progress": 100,
                "stage": "done",
            },
        )
        found = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            line = next(stream)
            if line == "event: job.done":
                found = True
                break
        assert found


def test_stream_filters_by_project(api_client: TestClient) -> None:
    engine = api_client.app.state.engine
    ours = seed_project(engine, title="Nuestro")
    other = seed_project(engine, title="Ajeno")
    queue.emit_event(
        engine, event_type="job.progress", project_id=other.id, payload={"progress": 1}
    )
    queue.emit_event(engine, event_type="job.progress", project_id=ours.id, payload={"progress": 2})

    events = _take(_events(api_client, f"/api/events?project_id={ours.id}"), 1)

    assert events[0]["data"]["progress"] == 2


def test_stream_honours_last_event_id(api_client: TestClient) -> None:
    engine = api_client.app.state.engine
    project = seed_project(engine)
    first = queue.emit_event(
        engine, event_type="job.progress", project_id=project.id, payload={"progress": 10}
    )
    queue.emit_event(
        engine, event_type="job.progress", project_id=project.id, payload={"progress": 20}
    )

    events = _take(
        _events(
            api_client,
            f"/api/events?project_id={project.id}",
            headers={"Last-Event-ID": str(first)},
        ),
        1,
    )

    assert events[0]["id"] > first
    assert events[0]["data"]["progress"] == 20


def test_stream_sends_heartbeats_without_events(api_client: TestClient) -> None:
    events = _take(_events(api_client, "/api/events"), 1, timeout=3)

    assert events[0]["event"] == "heartbeat"
    assert "ts" in events[0]["data"]


def test_stream_unsubscribes_on_disconnect(api_client: TestClient) -> None:
    broadcaster = api_client.app.state.broadcaster

    stream = _events(api_client, "/api/events")
    assert next(iter(stream))["event"] == "heartbeat"
    # `_events` cerramos el generador al salir del `with` de su consumidor.
    stream.close()

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and broadcaster._subscribers:
        time.sleep(0.05)
    assert len(broadcaster._subscribers) == 0
