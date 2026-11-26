"""Worker independiente de WinClip (`winclip worker`)."""

from __future__ import annotations

from winclip.worker.handlers import (
    HandlerError,
    JobCancelled,
    JobContext,
    PipelineBackends,
    ReservedJobTypeError,
    handle_job,
)
from winclip.worker.queue import (
    JobQueueError,
    backoff_seconds,
    cancel_job,
    claim_next,
    complete_job,
    emit_event,
    enqueue,
    fail_job,
    get_job,
    list_events,
    mark_cancelled,
    purge_events,
    record_event,
    recover_orphans,
    running_counts,
    update_progress,
)
from winclip.worker.runner import WorkerRunner

__all__ = [
    "HandlerError",
    "JobCancelled",
    "JobContext",
    "JobQueueError",
    "PipelineBackends",
    "ReservedJobTypeError",
    "WorkerRunner",
    "backoff_seconds",
    "cancel_job",
    "claim_next",
    "complete_job",
    "emit_event",
    "enqueue",
    "fail_job",
    "get_job",
    "handle_job",
    "list_events",
    "mark_cancelled",
    "purge_events",
    "record_event",
    "recover_orphans",
    "running_counts",
    "update_progress",
]
