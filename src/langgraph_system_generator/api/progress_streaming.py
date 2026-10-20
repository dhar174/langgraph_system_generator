"""Process-local, bounded job records and Server-Sent Event replay."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from sse_starlette.sse import EventSourceResponse

from langgraph_system_generator.utils.credential_redaction import (
    sanitize_generation_payload,
)

logger = logging.getLogger(__name__)


def _positive_int_env(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s; using default %d", name, default)
        return default
    return min(max(value, 1), maximum)


_COMPLETED_JOB_TTL_SECONDS = _positive_int_env(
    "LNF_COMPLETED_JOB_TTL_SECONDS", 300, 86_400
)
_MAX_TRACKED_JOBS = _positive_int_env("LNF_MAX_TRACKED_JOBS", 100, 10_000)
_MAX_JOB_EVENT_BYTES = _positive_int_env(
    "LNF_MAX_JOB_EVENT_BYTES", 256 * 1024, 4 * 1024 * 1024
)
_MAX_EVENT_BYTES = 16 * 1024
_MAX_EVENTS_PER_JOB = _positive_int_env("LNF_MAX_EVENTS_PER_JOB", 1000, 10000)


@dataclass
class JobRecord:
    """Ephemeral status and retained event history for one generation."""

    created_at: float
    events: list[dict[str, Any]] = field(default_factory=list)
    next_event_id: int = 0
    status: str = "accepted"
    completed_at: float | None = None
    events_truncated: bool = False
    event_bytes: int = 0
    subscribers: set[asyncio.Event] = field(default_factory=set)

    @property
    def completed(self) -> bool:
        """Backward-compatible terminal-state flag."""
        return self.status in {"completed", "failed", "cancelled", "expired"}


class JobCapacityError(RuntimeError):
    """Raised when retained in-memory job state reaches its configured bound."""


_active_jobs: dict[str, JobRecord] = {}
_owned_tasks: dict[str, asyncio.Task[Any]] = {}
_stream_subscribers: set[asyncio.Event] = set()
_MAX_STREAM_SUBSCRIBERS_PER_JOB = 50
_MAX_STREAM_SUBSCRIBERS_TOTAL = 500


def _prune_expired_jobs(now: float | None = None) -> list[str]:
    """Remove terminal records after retention; active execution is never pruned."""
    current = time.time() if now is None else now
    expired = [
        job_id
        for job_id, record in _active_jobs.items()
        if record.completed
        and record.completed_at is not None
        and current - record.completed_at >= _COMPLETED_JOB_TTL_SECONDS
    ]
    for job_id in expired:
        record = _active_jobs.pop(job_id, None)
        if record is not None:
            _notify_subscribers(record)
        logger.info("Expired retained job record %s", job_id)
    return expired


def create_job() -> str:
    """Create an accepted job record without scheduling unowned timers."""
    _prune_expired_jobs()
    if len(_active_jobs) >= _MAX_TRACKED_JOBS:
        raise JobCapacityError("The server has reached its retained job limit.")
    job_id = uuid4().hex
    _active_jobs[job_id] = JobRecord(created_at=time.time())
    logger.info("Accepted ephemeral job %s", job_id)
    return job_id


def discard_job(job_id: str) -> None:
    """Roll back a job that was never accepted by a running task."""
    if job_id not in _owned_tasks:
        _active_jobs.pop(job_id, None)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    """Return a bounded public status snapshot, or None after local-state loss."""
    _prune_expired_jobs()
    record = _active_jobs.get(job_id)
    if record is None:
        return None
    return {
        "job_id": job_id,
        "status": record.status,
        "execution_mode": "ephemeral_process_local",
        "durable": False,
        "created_at": record.created_at,
        "completed_at": record.completed_at,
        "latest_event_id": record.next_event_id - 1,
        "events_truncated": record.events_truncated,
    }


def mark_job_running(job_id: str) -> bool:
    """Move an accepted job to running once."""
    record = _active_jobs.get(job_id)
    if record is None or record.completed or record.status != "accepted":
        return False
    record.status = "running"
    for subscriber in tuple(record.subscribers):
        subscriber.set()
    return True


def _event_size(event: dict[str, Any]) -> int:
    return len(
        json.dumps(event, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )


def _compact_event_data(data: dict[str, Any]) -> dict[str, Any]:
    """Keep terminal identity and result references when trimming a large payload."""
    cleaned = sanitize_generation_payload(data)
    compact: dict[str, Any] = {
        "message": "Event details omitted because the payload exceeded the retention limit."
    }
    for key in ("success", "status", "run_id", "result_url", "code"):
        if key in cleaned:
            value = cleaned[key]
            if isinstance(value, str):
                compact[key] = value[:512]
            elif value is None or isinstance(value, (bool, int, float)):
                compact[key] = value
    for key in ("error", "message"):
        value = cleaned.get(key)
        if isinstance(value, str):
            compact[key] = value[:512]
    return compact


def _store_event(record: JobRecord, event: dict[str, Any], size: int) -> int:
    """Store a sanitized, sized event without repeating serialization."""
    record.next_event_id += 1
    record.events.append(event)
    record.event_bytes += size
    return int(event["id"])


def _append_event(
    record: JobRecord, event_type: str, data: dict[str, Any], *, terminal: bool = False
) -> int:
    event_id = record.next_event_id
    cleaned = sanitize_generation_payload(data)
    event = {"id": event_id, "event": event_type, "data": cleaned}
    if _event_size(event) > _MAX_EVENT_BYTES:
        event = {
            "id": event_id,
            "event": event_type,
            "data": _compact_event_data(cleaned),
        }
    size = _event_size(event)
    if terminal and size + record.event_bytes > _MAX_JOB_EVENT_BYTES:
        event["data"] = _compact_event_data(data)
        size = _event_size(event)
    return _store_event(record, event, size)


def _notify_subscribers(record: JobRecord) -> None:
    for subscriber in tuple(record.subscribers):
        subscriber.set()


def _truncate_history(record: JobRecord) -> None:
    if record.events_truncated:
        return
    record.events_truncated = True
    marker = {
        "message": "Progress history was truncated because the bounded replay history was full.",
        "max_events": _MAX_EVENTS_PER_JOB,
    }
    _append_event(record, "events_truncated", marker)


def emit_progress(
    job_id: str,
    event_type: str,
    data: dict[str, Any],
    log: bool = True,
) -> bool:
    """Append progress or commit a single terminal event."""
    record = _active_jobs.get(job_id)
    if record is None:
        logger.warning("Cannot emit to job %s: not found", job_id)
        return False

    if event_type in {"complete", "error"}:
        if record.completed:
            return False
        status = str(
            data.get("status")
            or ("completed" if event_type == "complete" else "failed")
        )
        if status not in {"completed", "failed", "cancelled", "expired"}:
            status = "failed"
        record.status = status
        record.completed_at = time.time()
        _append_event(record, event_type, data, terminal=True)
        _notify_subscribers(record)
        if log:
            logger.debug("Job %s reached terminal status %s", job_id, status)
        return True

    if record.completed:
        return False

    if record.status == "accepted":
        record.status = "running"

    if record.events_truncated:
        return False

    event = {
        "id": record.next_event_id,
        "event": event_type,
        "data": sanitize_generation_payload(data),
    }
    size = _event_size(event)
    if (
        len([item for item in record.events if item["event"] != "events_truncated"])
        >= _MAX_EVENTS_PER_JOB
        or size > _MAX_EVENT_BYTES
        or record.event_bytes + size > _MAX_JOB_EVENT_BYTES
    ):
        # Allocate an ID to the omitted event so replay cursors remain IDs, not list offsets.
        record.next_event_id += 1
        _truncate_history(record)
        _notify_subscribers(record)
        return False

    _store_event(record, event, size)
    _notify_subscribers(record)
    if log:
        logger.debug("Job %s: %s", job_id, event_type)
    return True


def emit_node_progress(
    job_id: str,
    node: str,
    percentage: int,
    message: str,
    status: str = "running",
) -> None:
    """Emit a progress update for a generator node."""
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


def emit_log(
    job_id: str,
    level: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Emit a bounded, sanitized generation log event."""
    payload: dict[str, Any] = {"level": level, "message": message}
    if details:
        payload["details"] = details
    emit_progress(job_id, "log", payload, log=False)


def emit_complete(job_id: str, result: dict[str, Any]) -> bool:
    """Commit successful completion once."""
    return emit_progress(job_id, "complete", {**result, "status": "completed"})


def emit_error(
    job_id: str,
    error: str,
    details: dict[str, Any] | None = None,
    *,
    status: str = "failed",
    code: str | None = None,
) -> bool:
    """Commit failure, cancellation, or timeout once using the compatible error event."""
    payload: dict[str, Any] = {"error": error, "status": status}
    if code:
        payload["code"] = code
    if details:
        payload["details"] = details
    return emit_progress(job_id, "error", payload)


def cleanup_job(job_id: str, *, force: bool = False) -> bool:
    """Remove terminal history, or cancel an active job when forced.

    Forced cancellation retains its terminal record for the normal retention
    window so subscribers can observe the outcome. It does not immediately evict
    that newly cancelled record.
    """
    record = _active_jobs.get(job_id)
    if record is None:
        return False
    if not record.completed:
        if not force:
            return False
        task = _owned_tasks.get(job_id)
        if task is not None:
            task.cancel()
        return emit_error(
            job_id,
            "Job was cancelled during cleanup.",
            status="cancelled",
            code="generation_cancelled",
        )
    _active_jobs.pop(job_id, None)
    _notify_subscribers(record)
    return True


async def progress_generator(
    job_id: str,
    last_event_id: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Replay stored events by their actual IDs, then await new events."""
    _prune_expired_jobs()
    record = _active_jobs.get(job_id)
    if record is None:
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "error": "Job not found or unavailable in this process.",
                    "status": "unavailable",
                    "code": "job_unavailable",
                }
            ),
        }
        return

    if (
        len(record.subscribers) >= _MAX_STREAM_SUBSCRIBERS_PER_JOB
        or len(_stream_subscribers) >= _MAX_STREAM_SUBSCRIBERS_TOTAL
    ):
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "error": "The server has reached its stream subscriber limit.",
                    "code": "stream_capacity",
                }
            ),
        }
        return

    cursor: int | None = None
    malformed_cursor = False
    if last_event_id is not None and last_event_id != "":
        try:
            cursor = int(last_event_id)
            if cursor < 0:
                raise ValueError
        except ValueError:
            malformed_cursor = True

    if malformed_cursor:
        yield {
            "event": "events_truncated",
            "data": json.dumps(
                {
                    "message": "Invalid Last-Event-ID; replaying retained history.",
                    "reason": "invalid_event_id",
                }
            ),
        }
        cursor = None

    latest_id = record.next_event_id - 1
    if cursor is not None and cursor > latest_id:
        yield {
            "event": "events_truncated",
            "data": json.dumps(
                {
                    "message": "Last-Event-ID is ahead of this process-local job history; reconnect with a retained event ID.",
                    "reason": "future_event_id",
                    "latest_event_id": latest_id,
                }
            ),
        }
        return

    subscriber = asyncio.Event()
    record.subscribers.add(subscriber)
    _stream_subscribers.add(subscriber)
    try:
        while True:
            retained_truncation_marker = any(
                event["event"] == "events_truncated" for event in record.events
            )
            pending = [
                event
                for event in record.events
                if cursor is None or event["id"] > cursor
            ]
            for event in pending:
                expected_id = 0 if cursor is None else cursor + 1
                if event["id"] > expected_id and not retained_truncation_marker:
                    yield {
                        "event": "events_truncated",
                        "data": json.dumps(
                            {
                                "message": "Some earlier events are no longer retained; progress history was truncated.",
                                "reason": "replay_gap",
                                "missing_from_event_id": expected_id,
                                "missing_through_event_id": event["id"] - 1,
                            }
                        ),
                    }
                cursor = event["id"]
                yield {
                    "id": str(event["id"]),
                    "event": event["event"],
                    "data": json.dumps(event["data"]),
                }
            # Re-snapshot after every yield: generation can commit its terminal
            # event while this generator is suspended on an earlier event.
            if record.completed:
                if not any(
                    event["id"] > (cursor if cursor is not None else -1)
                    for event in record.events
                ):
                    return
                continue

            subscriber.clear()
            # No await occurs between the replay check and wait; synchronous emitters
            # either set this event before the check or while wait() is suspended.
            pending = [
                event
                for event in record.events
                if cursor is None or event["id"] > cursor
            ]
            if pending or record.completed:
                continue
            await subscriber.wait()
    except asyncio.CancelledError:
        logger.debug("SSE subscriber disconnected for job %s", job_id)
        raise
    finally:
        record.subscribers.discard(subscriber)
        _stream_subscribers.discard(subscriber)


def get_stream_response(
    job_id: str, last_event_id: str | None = None
) -> EventSourceResponse:
    """Create a process-local SSE response for a job."""
    return EventSourceResponse(
        progress_generator(job_id, last_event_id=last_event_id),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def register_owned_task(
    job_id: str,
    task: asyncio.Task[Any],
    on_done: Callable[[asyncio.Task[Any]], None] | None = None,
) -> None:
    """Retain an accepted job's one owner task until it reaches a terminal state."""
    record = _active_jobs.get(job_id)
    if record is None:
        raise KeyError("Cannot register a task for a missing job.")
    if job_id in _owned_tasks:
        raise RuntimeError("The job already has an owner task.")
    _owned_tasks[job_id] = task

    def finished(done: asyncio.Task[Any]) -> None:
        if _owned_tasks.get(job_id) is done:
            _owned_tasks.pop(job_id, None)
        current = _active_jobs.get(job_id)
        exception = None if done.cancelled() else done.exception()
        if current is not None and not current.completed:
            if done.cancelled():
                emit_error(
                    job_id,
                    "Generation was cancelled.",
                    status="cancelled",
                    code="generation_cancelled",
                )
            else:
                emit_error(
                    job_id,
                    (
                        "Generation failed unexpectedly."
                        if exception
                        else "Generation stopped without a terminal outcome."
                    ),
                    {"error_type": type(exception).__name__} if exception else {},
                    status="failed",
                    code="generation_task_failed",
                )
        if on_done is not None:
            try:
                on_done(done)
            except Exception:
                logger.exception(
                    "Job completion cleanup callback failed for %s", job_id
                )

    task.add_done_callback(finished)


async def shutdown_owned_tasks(timeout: float = 5.0) -> int:
    """Cancel owned tasks and wait at most ``timeout`` seconds for their cleanup."""
    tasks = tuple(_owned_tasks.values())
    for task in tasks:
        task.cancel()
    if not tasks:
        return 0
    _, pending = await asyncio.wait(tasks, timeout=max(timeout, 0))
    # Done callbacks record cancellation and release owners as each task exits.
    return len(pending)


def owned_task_ids() -> set[str]:
    """Expose a copy for status checks and deterministic lifecycle tests."""
    return set(_owned_tasks)
