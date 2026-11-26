"""Broadcaster SSE sobre la tabla outbox `job_event` (design, decisión 4).

Un único bucle asíncrono lee `job_event` cada pocos cientos de milisegundos y distribuye
cada evento a las suscripciones en memoria. Cada suscripción recuerda su último id para
soportar `Last-Event-ID` en reconexiones y nunca recibe duplicados.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, select
from sqlmodel import Session

from winclip.core.models import JobEvent
from winclip.worker import queue

POLL_INTERVAL_SECONDS = 0.4
EVENTS_PER_POLL = 200


@dataclass(eq=False)
class Subscription:
    """Cola de un cliente SSE conectado."""

    project_id: str | None
    last_id: int
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)


def format_event(event_id: int | None, event_type: str, payload: dict[str, Any]) -> str:
    """Bloque SSE válido (id opcional y `data` JSON en una línea)."""
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def format_heartbeat(timestamp: str) -> str:
    return format_event(None, "heartbeat", {"ts": timestamp})


class EventBroadcaster:
    """Lee el outbox y reparte eventos entre las conexiones SSE vivas."""

    def __init__(
        self,
        engine: Engine,
        *,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self.engine = engine
        self.poll_interval = poll_interval
        self._subscribers: set[Subscription] = set()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._last_id = 0

    # ------------------------------------------------------------- ciclo vida

    async def start(self) -> None:
        if self._task is not None:
            return
        events = await asyncio.to_thread(queue.list_events, self.engine, limit=1)
        if events:
            self._last_id = int(events[-1].id or 0)
        else:
            latest = await asyncio.to_thread(self._latest_event_id)
            self._last_id = latest
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    def _latest_event_id(self) -> int:
        with Session(self.engine) as session:
            value = session.exec(select(JobEvent.id).order_by(JobEvent.id.desc()).limit(1)).first()
        return int(value or 0)

    async def _loop(self) -> None:
        while True:
            try:
                events = await asyncio.to_thread(
                    queue.list_events,
                    self.engine,
                    after_id=self._last_id,
                    limit=EVENTS_PER_POLL,
                )
                if events:
                    async with self._lock:
                        for event in events:
                            self._last_id = max(self._last_id, int(event.id or 0))
                            self._dispatch(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(self.poll_interval)
            await asyncio.sleep(self.poll_interval)

    def _dispatch(self, event: JobEvent) -> None:
        event_id = int(event.id or 0)
        for subscription in list(self._subscribers):
            if event_id <= subscription.last_id:
                continue
            if subscription.project_id is not None and event.project_id != subscription.project_id:
                continue
            subscription.last_id = event_id
            subscription.queue.put_nowait(
                {
                    "id": event_id,
                    "event": event.event_type,
                    "payload": dict(event.payload or {}),
                }
            )

    # ------------------------------------------------------------ suscripción

    async def subscribe(
        self,
        project_id: str | None,
        after_id: int = 0,
    ) -> tuple[Subscription, list[dict[str, Any]]]:
        """Registra la conexión y devuelve el backlog desde `after_id`."""
        subscription = Subscription(project_id=project_id, last_id=max(0, after_id))
        async with self._lock:
            backlog_events = await asyncio.to_thread(
                queue.list_events,
                self.engine,
                after_id=subscription.last_id,
                project_id=project_id,
                limit=EVENTS_PER_POLL,
            )
            backlog = []
            for event in backlog_events:
                event_id = int(event.id or 0)
                subscription.last_id = max(subscription.last_id, event_id)
                backlog.append(
                    {
                        "id": event_id,
                        "event": event.event_type,
                        "payload": dict(event.payload or {}),
                    }
                )
            self._subscribers.add(subscription)
        return subscription, backlog

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscribers.discard(subscription)
