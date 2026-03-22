"""Server-Sent Events for real-time progress and log streaming."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import json
import logging
import threading
import time
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    """In-memory state for a single async generation job."""

    created_at: float
    # A threading lock is used here because emit_progress() must remain
    # callable from synchronous code paths, while async stream readers need
    # to inspect the same in-memory state without awaiting an async lock in
    # the producer path.
    # The guarded sections are tiny and only protect in-process bookkeeping.
    state_lock: threading.Lock = field(default_factory=threading.Lock)
    update_signal: asyncio.Event = field(default_factory=asyncio.Event)
    events: deque[Dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=_MAX_RECORDED_EVENTS)
    )
    next_event_id: int = 0
    completed: bool = False
    completed_at: float | None = None


_active_jobs: Dict[str, JobRecord] = {}

# Job cleanup TTL - jobs are cleaned up after this time regardless of
# completion.
_JOB_TTL_SECONDS = 3600  # 1 hour

# Completed job retention - keep completed jobs for clients that connect late
_COMPLETED_JOB_TTL_SECONDS = 300  # 5 minutes
_MAX_RECORDED_EVENTS = 1000
# -1 means "no event has been acknowledged yet".
# Replay should begin from the first retained event.
_MIN_EVENT_ID = -1


def create_job() -> str:
    """Create a new job and return its ID."""

    job_id = str(uuid4())
    _active_jobs[job_id] = JobRecord(created_at=time.time())
    logger.info("Created job %s", job_id)

    try:
        asyncio.create_task(_schedule_job_cleanup(job_id))
    except RuntimeError:
        logger.warning(
            "Job %s created outside event loop; automatic TTL cleanup is "
            "not scheduled for this job",
            job_id,
        )

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
        logger.info(
            "Cleaning up completed job %s after retention period",
            job_id,
        )
        cleanup_job(job_id)


def _parse_last_event_id(last_event_id: str | None) -> int | None:
    """Convert Last-Event-ID to the last acknowledged event ID."""

    if not last_event_id:
        return None

    try:
        return max(int(last_event_id), _MIN_EVENT_ID)
    except ValueError:
        logger.warning(
            "Ignoring invalid Last-Event-ID value: %s",
            last_event_id,
        )
        return None


def _find_next_event_index(
    record: JobRecord,
    last_event_id: str | None,
) -> int:
    """Resolve the next unread event index for a reconnecting subscriber."""

    last_seen_event_id = _parse_last_event_id(last_event_id)
    if last_seen_event_id is None:
        return 0

    with record.state_lock:
        for index, event in enumerate(record.events):
            if event["id"] > last_seen_event_id:
                return index
        return len(record.events)


def _resolve_initial_replay_state(
    record: JobRecord,
    last_event_id: str | None,
) -> tuple[int, int | None]:
    """Resolve the initial replay cursor and last-sent event id."""

    parsed_last_event_id = _parse_last_event_id(last_event_id)
    if parsed_last_event_id is None:
        return 0, None

    with record.state_lock:
        if not record.events:
            return 0, _MIN_EVENT_ID

        latest_retained_event_id = record.events[-1]["id"]
        if parsed_last_event_id > latest_retained_event_id:
            return len(record.events), latest_retained_event_id

    return _find_next_event_index(record, last_event_id), parsed_last_event_id


def _clamp_event_index(next_index: int, event_count: int) -> int:
    """Clamp a replay cursor to the currently available event range."""

    return min(max(next_index, 0), event_count)


def _find_unread_events(
    events_snapshot: list[Dict[str, Any]],
    last_sent_event_id: int | None,
) -> list[Dict[str, Any]]:
    """Return the unread retained events after the last-sent event id."""

    if last_sent_event_id is None:
        return events_snapshot

    for index, event in enumerate(events_snapshot):
        if event["id"] > last_sent_event_id:
            return events_snapshot[index:]
    return []


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
            "data": json.dumps(
                {"error": "Job not found or already completed"}
            ),
        }
        return

    logger.info("Starting SSE stream for job %s", job_id)
    next_index, last_sent_event_id = _resolve_initial_replay_state(
        record,
        last_event_id,
    )

    try:
        while True:
            events_to_yield: list[Dict[str, Any]] = []
            wait_signal: asyncio.Event | None = None

            with record.state_lock:
                events_snapshot = list(record.events)
                if last_sent_event_id is None:
                    next_index = _clamp_event_index(
                        next_index,
                        len(events_snapshot),
                    )
                    if next_index < len(events_snapshot):
                        events_to_yield = events_snapshot[next_index:]
                else:
                    events_to_yield = _find_unread_events(
                        events_snapshot,
                        last_sent_event_id,
                    )

                if not events_to_yield and not record.completed:
                    wait_signal = record.update_signal
                    if wait_signal.is_set():
                        # Create a fresh Event while holding the shared lock
                        # so all subscribers transition to the same new wait
                        # point and future producer wakeups are not lost.
                        wait_signal = asyncio.Event()
                        record.update_signal = wait_signal

            for event in events_to_yield:
                last_sent_event_id = event["id"]
                yield {
                    "id": str(event["id"]),
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }

            if record.completed:
                logger.info("Job %s stream completed", job_id)
                break

            try:
                if wait_signal is None:
                    continue
                await asyncio.wait_for(wait_signal.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                logger.warning("Job %s timed out waiting for events", job_id)
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"error": "Job timed out - no progress in 5 minutes"}
                    ),
                }
                break

    except asyncio.CancelledError:
        logger.info(
            "SSE stream cancelled for job %s - keeping job for reconnection",
            job_id,
        )
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

    should_schedule_completed_cleanup = False
    with record.state_lock:
        event_id = record.next_event_id
        record.next_event_id += 1
        record.events.append(
            {"id": event_id, "event": event_type, "data": data}
        )

        if event_type in ("complete", "error"):
            record.completed = True
            record.completed_at = time.time()
            should_schedule_completed_cleanup = True

        record.update_signal.set()

    if should_schedule_completed_cleanup:
        try:
            asyncio.create_task(_schedule_completed_job_cleanup(job_id))
        except RuntimeError:
            logger.debug(
                "Cannot schedule completed cleanup for %s - no event loop",
                job_id,
            )

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


def emit_error(
    job_id: str,
    error: str,
    details: Dict[str, Any] | None = None,
) -> None:
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


def get_stream_response(
    job_id: str,
    last_event_id: str | None = None,
) -> EventSourceResponse:
    """Create an SSE EventSourceResponse for a job."""

    return EventSourceResponse(
        progress_generator(job_id, last_event_id=last_event_id),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
