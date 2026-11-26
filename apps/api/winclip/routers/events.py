"""`/api/events`: stream SSE de progreso, clips listos y latidos."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from winclip.services.events import EventBroadcaster, Subscription, format_event, format_heartbeat

router = APIRouter(tags=["events"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/api/events", operation_id="streamEvents")
async def stream_events(
    request: Request,
    project_id: str | None = None,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream `text/event-stream` con filtro opcional por proyecto y `Last-Event-ID`."""
    broadcaster: EventBroadcaster = request.app.state.broadcaster
    heartbeat = float(request.app.state.settings.sse_heartbeat_seconds)
    try:
        after_id = int(last_event_id or 0)
    except ValueError:
        after_id = 0

    subscription, backlog = await broadcaster.subscribe(project_id, max(0, after_id))

    async def generate():
        try:
            for envelope in backlog:
                yield format_event(envelope["id"], envelope["event"], envelope["payload"])
            while True:
                try:
                    envelope = await asyncio.wait_for(subscription.queue.get(), timeout=heartbeat)
                except TimeoutError:
                    yield format_heartbeat(datetime.now(UTC).isoformat())
                    continue
                yield format_event(envelope["id"], envelope["event"], envelope["payload"])
        finally:
            broadcaster.unsubscribe(subscription)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def subscription_stream(subscription: Subscription) -> str:  # pragma: no cover - utilidad
    """Representación de depuración de una suscripción."""
    return f"Subscription(project_id={subscription.project_id}, last_id={subscription.last_id})"
