"""Bucle del worker: pool ligero, un trabajo pesado a la vez y apagado limpio.

El worker corre en su propio proceso (`winclip worker`). Reclama trabajo de forma atómica,
lanza handlers en un pool de hilos, mantiene el latido de los trabajos en curso y
recupera los huérfanos de ejecuciones anteriores.
"""

from __future__ import annotations

import contextlib
import logging
import signal
import threading
import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor, wait
from types import FrameType

from sqlalchemy import Engine

from winclip.core.config import Settings
from winclip.core.ids import new_ulid
from winclip.core.models import HEAVY_JOB_TYPES
from winclip.worker import queue
from winclip.worker.handlers import PipelineBackends, handle_job

logger = logging.getLogger("winclip.worker")

HEARTBEAT_SECONDS = 2.0
PURGE_INTERVAL_SECONDS = 300.0
SHUTDOWN_GRACE_SECONDS = 10.0
POLL_SLICE_SECONDS = 0.1


@contextlib.contextmanager
def signal_handlers(stop_event: threading.Event) -> Iterator[None]:
    """Convierte `SIGINT`/`SIGTERM` en un apagado limpio (solo en el hilo principal)."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous: dict[int, object] = {}

    def _handle(_signum: int, _frame: FrameType | None) -> None:
        logger.info("señal recibida: parando el worker")
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, _handle)
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)  # type: ignore[arg-type]


class WorkerRunner:
    """Consume la cola hasta que se pida parar."""

    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        *,
        worker_id: str | None = None,
        backends: PipelineBackends | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.worker_id = worker_id or f"worker-{new_ulid()}"
        self.backends = backends or PipelineBackends()
        self.light_limit = settings.worker_light_concurrency
        self._executor = ThreadPoolExecutor(
            max_workers=self.light_limit + 1,
            thread_name_prefix="winclip-job",
        )
        self._active: dict[str, tuple[Future[None], bool, threading.Event]] = {}
        self._lock = threading.Lock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ ciclo

    def run(self, stop_event: threading.Event | None = None) -> None:
        """Arranca el bucle; retorna cuando `stop_event` se activa o se llama `stop()`."""
        stop_event = stop_event or threading.Event()
        recovered = queue.recover_orphans(
            self.engine, stale_seconds=self.settings.job_stale_seconds
        )
        if recovered:
            logger.info("recuperados %s trabajo(s) huérfano(s)", recovered)
        logger.info("worker %s listo (ligeros=%s)", self.worker_id, self.light_limit)

        self._start_heartbeat()
        last_purge = time.monotonic()
        try:
            while not stop_event.is_set():
                self._reap_finished()
                self._claim_and_start()
                now = time.monotonic()
                if now - last_purge > PURGE_INTERVAL_SECONDS:
                    queue.purge_events(self.engine)
                    last_purge = now
                self._sleep(stop_event, self.settings.worker_poll_interval)
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Señal de parada usable desde otro hilo (tests y CLI)."""
        self._heartbeat_stop.set()

    def _sleep(self, stop_event: threading.Event, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not stop_event.is_set():
            time.sleep(min(POLL_SLICE_SECONDS, seconds))

    # ---------------------------------------------------------------- reclamo

    def _light_running(self) -> int:
        with self._lock:
            return sum(
                1 for future, light, _ in self._active.values() if light and not future.done()
            )

    def _claim_and_start(self) -> None:
        job = queue.claim_next(
            self.engine,
            worker_id=self.worker_id,
            light_running=self._light_running(),
            light_limit=self.light_limit,
        )
        if job is None:
            return
        light = job.type not in HEAVY_JOB_TYPES
        cancel_event = threading.Event()
        future = self._executor.submit(self._execute, job.id, cancel_event)
        with self._lock:
            self._active[job.id] = (future, light, cancel_event)
        logger.info("reclamado %s (%s)", job.id, job.type)

    def _execute(self, job_id: str, cancel_event: threading.Event) -> None:
        try:
            final = handle_job(
                self.engine,
                job_id,
                settings=self.settings,
                backends=self.backends,
                cancel_event=cancel_event,
            )
            logger.info("trabajo %s terminó en %s", job_id, final.status)
        except Exception:
            logger.exception("el trabajo %s falló fuera del handler", job_id)

    def _reap_finished(self) -> None:
        with self._lock:
            finished = [job_id for job_id, (future, _, _) in self._active.items() if future.done()]
            for job_id in finished:
                self._active.pop(job_id, None)

    # ----------------------------------------------------------------- latido

    def _start_heartbeat(self) -> None:
        self._heartbeat_stop.clear()
        thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="winclip-heartbeat"
        )
        thread.start()
        self._heartbeat_thread = thread

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(HEARTBEAT_SECONDS):
            with self._lock:
                active = list(self._active.items())
            for job_id, (future, _, cancel_event) in active:
                if future.done():
                    continue
                queue.heartbeat(self.engine, job_id, worker_id=self.worker_id)
                if queue.is_cancel_requested(self.engine, job_id):
                    cancel_event.set()

    # --------------------------------------------------------------- apagado

    def _shutdown(self) -> None:
        self._heartbeat_stop.set()
        thread = self._heartbeat_thread
        if thread is not None:
            thread.join(timeout=HEARTBEAT_SECONDS)
        with self._lock:
            pending = dict(self._active)
        if pending:
            logger.info("esperando %s trabajo(s) en curso", len(pending))
            wait([future for future, _, _ in pending.values()], timeout=SHUTDOWN_GRACE_SECONDS)
            with self._lock:
                still_running = [
                    (job_id, cancel_event)
                    for job_id, (future, _, cancel_event) in self._active.items()
                    if not future.done()
                ]
            for job_id, cancel_event in still_running:
                logger.info("cancelando %s al apagar", job_id)
                cancel_event.set()
                with contextlib.suppress(queue.JobQueueError):
                    queue.cancel_job(self.engine, job_id)
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._active.clear()


def run_worker(
    engine: Engine,
    settings: Settings,
    *,
    stop_event: threading.Event | None = None,
    backends: PipelineBackends | None = None,
) -> WorkerRunner:
    """Ejecuta el worker con manejadores de señal y devuelve la instancia usada."""
    stop_event = stop_event or threading.Event()
    runner = WorkerRunner(engine, settings, backends=backends)
    with signal_handlers(stop_event):
        runner.run(stop_event)
    return runner
