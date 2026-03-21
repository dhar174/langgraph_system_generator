"""Server-Sent Events for real-time progress and log streaming."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    """In-memory state for a single async generation job."""

    created_at: float
    wake_event: asyncio.Event = field(default_factory=asyncio.Event)
    events: list[Dict[str, Any]] = field(default_factory=list)
    next_event_id: int = 0
    update_version: int = 0
    cleanup_scheduled: bool = False
    completed_cleanup_scheduled: bool = False
    completed: bool = False
    completed_at: float | None = None


_active_jobs: Dict[str, JobRecord] = {}

# Job cleanup TTL - jobs are cleaned up after this time regardless of completion
_JOB_TTL_SECONDS = 3600  # 1 hour

# Completed job retention - keep completed jobs for clients that connect late
_COMPLETED_JOB_TTL_SECONDS = 300  # 5 minutes

# Bound retained events to avoid unbounded in-memory growth per job.
_MAX_PROGRESS_EVENTS = max(1, int(os.getenv("LNF_MAX_PROGRESS_EVENTS", "250")))


def create_job() -> str:
    """Create a new job and return its ID."""

    job_id = str(uuid4())
    record = JobRecord(created_at=time.time())
    _active_jobs[job_id] = record
    logger.info("Created job %s", job_id)
    _ensure_job_cleanup(job_id, record)

    return job_id


async def _schedule_job_cleanup(job_id: str) -> None:
    """Schedule cleanup for a job after TTL expires."""

    await asyncio.sleep(_JOB_TTL_SECONDS)
    if job_id in _active_jobs:
        logger.info("Cleaning up job %s after TTL expiration", job_id)
        cleanup_job(job_id)


async def _schedule_completed_job_cleanup(job_id: str) -> None:
    """Schedule cleanup for a completed job after the retention window."""

    await asyncio.sleep(_COMPLETED_JOB_TTL_SECONDS)

    record = _active_jobs.get(job_id)
    if record and record.completed:
        logger.info("Cleaning up completed job %s after retention period", job_id)
        cleanup_job(job_id)


def _parse_last_event_id(last_event_id: str | None) -> int:
    """Convert the SSE Last-Event-ID header to the next event index."""

    if not last_event_id:
        return 0

    try:
        return max(int(last_event_id) + 1, 0)
    except ValueError:
        logger.warning("Ignoring invalid Last-Event-ID value: %s", last_event_id)
        return 0


def _ensure_job_cleanup(job_id: str, record: JobRecord) -> None:
    """Schedule the TTL cleanup task when an event loop is available."""

    if record.cleanup_scheduled:
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_schedule_job_cleanup(job_id))
        record.cleanup_scheduled = True
    except RuntimeError:
        logger.debug(
            "Job %s has no running event loop; automatic TTL cleanup will be retried "
            "when progress is emitted from an async context",
            job_id,
        )


def _ensure_completed_cleanup(job_id: str, record: JobRecord) -> None:
    """Schedule completed-job cleanup when an event loop is available."""

    if record.completed_cleanup_scheduled:
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_schedule_completed_job_cleanup(job_id))
        record.completed_cleanup_scheduled = True
    except RuntimeError:
        logger.debug(
            "Job %s completed without a running event loop; completed-job cleanup "
            "could not be scheduled automatically",
            job_id,
        )


def _trim_retained_events(record: JobRecord) -> None:
    """Drop the oldest retained events once the in-memory cap is exceeded."""

    overflow = len(record.events) - _MAX_PROGRESS_EVENTS
    if overflow > 0:
        del record.events[:overflow]


def _clamp_next_event_id(record: JobRecord, next_event_id: int) -> int:
    """Clamp a replay cursor to the retained event window for a job."""

    if not record.events:
        return max(next_event_id, 0)

    earliest_event_id = record.events[0]["id"]
    latest_next_event_id = record.events[-1]["id"] + 1
    return min(max(next_event_id, earliest_event_id), latest_next_event_id)


def _has_pending_events(record: JobRecord, next_event_id: int) -> bool:
    """Return True when the requested cursor can deliver retained events."""

    return bool(record.events) and next_event_id <= record.events[-1]["id"]


async def progress_generator(
    job_id: str,
    last_event_id: str | None = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream progress events for a specific job via Server-Sent Events."""

    record = _active_jobs.get(job_id)
    if record is None:
        logger.warning("Job %s not found", job_id)
        yield {
            "event": "error",
            "data": json.dumps({"error": "Job not found or already completed"}),
        }
        return

    logger.info("Starting SSE stream for job %s", job_id)
    next_event_id = _parse_last_event_id(last_event_id)

    try:
        while True:
            next_event_id = _clamp_next_event_id(record, next_event_id)

            while _has_pending_events(record, next_event_id):
                first_event_id = record.events[0]["id"]
                event = record.events[next_event_id - first_event_id]
                next_event_id = event["id"] + 1
                yield {
                    "id": str(event["id"]),
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }

            if record.completed:
                logger.info("Job %s stream completed", job_id)
                break

            try:
                current_version = record.update_version
                record.wake_event.clear()
                next_event_id = _clamp_next_event_id(record, next_event_id)
                if (
                    _has_pending_events(record, next_event_id)
                    or record.completed
                    or record.update_version != current_version
                ):
                    continue
                await asyncio.wait_for(record.wake_event.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                logger.warning("Job %s timed out waiting for events", job_id)
                yield {
                    "event": "error",
                    "data": json.dumps({"error": "Job timed out - no progress in 5 minutes"}),
                }
                break

    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for job %s - keeping job for reconnection", job_id)
        raise
    except Exception as exc:
        logger.exception("Error in progress generator for job %s", job_id)
        yield {
            "event": "error",
            "data": json.dumps({"error": f"Stream error: {exc}"}),
        }


def emit_progress(
    job_id: str,
    event_type: str,
    data: Dict[str, Any],
    log: bool = True,
) -> None:
    """Emit a progress event to the job's SSE stream."""

    record = _active_jobs.get(job_id)
    if record is None:
        logger.warning("Cannot emit to job %s: not found", job_id)
        return

    _ensure_job_cleanup(job_id, record)

    event_id = record.next_event_id
    record.next_event_id += 1
    record.events.append({"id": event_id, "event": event_type, "data": data})
    _trim_retained_events(record)
    record.update_version += 1
    record.wake_event.set()

    if event_type in ("complete", "error"):
        record.completed = True
        record.completed_at = time.time()
        _ensure_completed_cleanup(job_id, record)

    if log:
        logger.debug(
            "Job %s: %s - %s",
            job_id,
            event_type,
            data.get("message", str(data)[:100]),
        )


def emit_node_progress(
    job_id: str,
    node: str,
    percentage: int,
    message: str,
    status: str = "running",
) -> None:
    """Emit a progress update for a specific generator node."""

    emit_progress(
        job_id,
        "progress",
        {
            "node": node,
            "percentage": min(100, max(0, percentage)),
            "message": message,
            "status": status,
        },
    )


def emit_log(job_id: str, level: str, message: str) -> None:
    """Emit a log message to the job's SSE stream."""

    emit_progress(
        job_id,
        "log",
        {
            "level": level,
            "message": message,
        },
        log=False,
    )


def emit_complete(job_id: str, result: Dict[str, Any]) -> None:
    """Emit a completion event with final result."""

    emit_progress(job_id, "complete", result)
    logger.info("Job %s completed successfully", job_id)


def emit_error(job_id: str, error: str, details: Dict[str, Any] | None = None) -> None:
    """Emit an error event."""

    payload = {"error": error}
    if details:
        payload["details"] = details

    emit_progress(job_id, "error", payload)
    logger.error("Job %s failed: %s", job_id, error)


def cleanup_job(job_id: str) -> None:
    """Clean up job resources after completion or TTL expiration."""

    if job_id in _active_jobs:
        del _active_jobs[job_id]
    logger.info("Cleaned up job %s", job_id)


def get_stream_response(job_id: str, last_event_id: str | None = None) -> EventSourceResponse:
    """Create an SSE EventSourceResponse for a job."""

    return EventSourceResponse(
        progress_generator(job_id, last_event_id=last_event_id),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
