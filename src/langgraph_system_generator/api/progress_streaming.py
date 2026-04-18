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
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    events: list[Dict[str, Any]] = field(default_factory=list)
    next_event_id: int = 0
    completed: bool = False
    completed_at: float | None = None
    events_truncated: bool = False


_active_jobs: Dict[str, JobRecord] = {}

# Job cleanup TTL - jobs are cleaned up after this time regardless of completion
_JOB_TTL_SECONDS = 3600  # 1 hour

# Completed job retention - keep completed jobs for clients that connect late
_COMPLETED_JOB_TTL_SECONDS = 300  # 5 minutes


def _get_max_events_per_job() -> int:
    """Read the per-job event cap from the environment with safe fallback."""
    raw_value = os.getenv("LNF_MAX_EVENTS_PER_JOB", "10000")

    try:
        parsed_value = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid LNF_MAX_EVENTS_PER_JOB value %r; falling back to default %d",
            raw_value,
            10000,
        )
        return 10000

    return max(parsed_value, 1)


# Bound replay history while still allowing one truncation marker and a terminal event.
_MAX_EVENTS_PER_JOB = _get_max_events_per_job()


def create_job() -> str:
    """Create a new job and return its ID."""
    job_id = str(uuid4())
    _active_jobs[job_id] = JobRecord(created_at=time.time())
    logger.info("Created job %s", job_id)

    try:
        asyncio.create_task(_schedule_job_cleanup(job_id))
    except RuntimeError:
        logger.debug("Job %s created outside event loop, cleanup will be scheduled later", job_id)

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


async def _notify_listeners(record: JobRecord) -> None:
    """Wake up streaming subscribers waiting on a job record."""
    async with record.condition:
        record.condition.notify_all()


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
    next_index = _parse_last_event_id(last_event_id)

    try:
        while True:
            while next_index < len(record.events):
                event = record.events[next_index]
                next_index += 1
                yield {
                    "id": str(event["id"]),
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }

            if record.completed:
                logger.info("Job %s stream completed", job_id)
                break

            try:
                async with record.condition:
                    await asyncio.wait_for(record.condition.wait(), timeout=300.0)
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

    is_terminal = event_type in ("complete", "error")
    if not is_terminal and len(record.events) >= _MAX_EVENTS_PER_JOB:
        if not record.events_truncated:
            record.events_truncated = True
            truncation_event_id = record.next_event_id
            record.next_event_id += 1
            record.events.append(
                {
                    "id": truncation_event_id,
                    "event": "events_truncated",
                    "data": {
                        "message": (
                            "Event history truncated after "
                            f"{_MAX_EVENTS_PER_JOB} replayable events. "
                            "Further non-terminal events will not be stored."
                        ),
                        "max_events": _MAX_EVENTS_PER_JOB,
                    },
                }
            )
            logger.warning(
                "Job %s reached the replay history limit (%d); dropping further non-terminal events",
                job_id,
                _MAX_EVENTS_PER_JOB,
            )
            try:
                asyncio.create_task(_notify_listeners(record))
            except RuntimeError:
                logger.debug("Cannot notify listeners for %s - no event loop", job_id)
        return

    event_id = record.next_event_id
    record.next_event_id += 1
    record.events.append({"id": event_id, "event": event_type, "data": data})

    if event_type in ("complete", "error"):
        record.completed = True
        record.completed_at = time.time()
        try:
            asyncio.create_task(_schedule_completed_job_cleanup(job_id))
        except RuntimeError:
            logger.debug("Cannot schedule completed cleanup for %s - no event loop", job_id)

    try:
        asyncio.create_task(_notify_listeners(record))
    except RuntimeError:
        logger.debug("Cannot notify listeners for %s - no event loop", job_id)

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
