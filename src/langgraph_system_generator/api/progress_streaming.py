"""Server-Sent Events for real-time progress and log streaming.

This module provides SSE-based progress tracking for long-running generation tasks.
It uses in-memory queues for simplicity in Phase 1, suitable for single-server deployments.
For production multi-server deployments, consider using Redis pub/sub or similar.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

# In-memory job tracking
# NOTE: This is suitable for development and single-server deployments.
# For production with multiple servers, use Redis pub/sub or similar distributed queue.
_active_jobs: Dict[str, asyncio.Queue] = {}

# Maximum events to buffer per job (prevents memory exhaustion)
_MAX_QUEUE_SIZE = 1000


def create_job() -> str:
    """Create a new job and return its ID.
    
    Returns:
        str: Unique job identifier (UUID)
    """
    job_id = str(uuid4())
    # Use bounded queue to prevent memory exhaustion
    _active_jobs[job_id] = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
    logger.info(f"Created job {job_id}")
    return job_id


async def progress_generator(job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream progress events for a specific job via Server-Sent Events.
    
    Args:
        job_id: Unique identifier for the job
        
    Yields:
        Dict containing SSE event data with 'event' and 'data' keys
    """
    if job_id not in _active_jobs:
        logger.warning(f"Job {job_id} not found")
        yield {
            "event": "error",
            "data": json.dumps({"error": "Job not found or already completed"}),
        }
        return

    queue = _active_jobs[job_id]
    logger.info(f"Starting SSE stream for job {job_id}")

    try:
        while True:
            # Wait for next event with timeout to detect stalled jobs
            try:
                event = await asyncio.wait_for(queue.get(), timeout=300.0)  # 5 min timeout
            except asyncio.TimeoutError:
                logger.warning(f"Job {job_id} timed out waiting for events")
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"error": "Job timed out - no progress in 5 minutes"}
                    ),
                }
                break

            # Emit the event
            event_type = event.get("event", "message")
            event_data = event.get("data", {})

            yield {"event": event_type, "data": json.dumps(event_data)}

            # Stop streaming after completion or error
            if event_type in ("complete", "error"):
                logger.info(f"Job {job_id} finished with event: {event_type}")
                break

    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled for job {job_id}")
        raise
    except Exception as e:
        logger.exception(f"Error in progress generator for job {job_id}")
        yield {
            "event": "error",
            "data": json.dumps({"error": f"Stream error: {str(e)}"}),
        }
    finally:
        # Cleanup job after streaming completes
        cleanup_job(job_id)


def emit_progress(
    job_id: str,
    event_type: str,
    data: Dict[str, Any],
    log: bool = True,
) -> None:
    """Emit a progress event to the job's SSE stream.
    
    Args:
        job_id: Job identifier
        event_type: SSE event type ('progress', 'log', 'complete', 'error')
        data: Event payload dictionary
        log: Whether to log the event (default: True)
    """
    if job_id not in _active_jobs:
        logger.warning(f"Cannot emit to job {job_id}: not found")
        return

    queue = _active_jobs[job_id]

    # Build event
    event = {"event": event_type, "data": data}

    # Non-blocking put with overflow protection
    try:
        queue.put_nowait(event)
        if log:
            logger.debug(
                f"Job {job_id}: {event_type} - {data.get('message', str(data)[:100])}"
            )
    except asyncio.QueueFull:
        logger.error(
            f"Job {job_id} queue full - dropping event. This indicates too many progress updates."
        )


def emit_node_progress(
    job_id: str,
    node: str,
    percentage: int,
    message: str,
    status: str = "running",
) -> None:
    """Emit a progress update for a specific generator node.
    
    Args:
        job_id: Job identifier
        node: Name of the generator node (e.g., 'intake', 'rag_retrieval')
        percentage: Progress percentage (0-100)
        message: Human-readable progress message
        status: Node status ('running', 'complete', 'error')
    """
    emit_progress(
        job_id,
        "progress",
        {
            "node": node,
            "percentage": min(100, max(0, percentage)),  # Clamp to 0-100
            "message": message,
            "status": status,
        },
    )


def emit_log(job_id: str, level: str, message: str) -> None:
    """Emit a log message to the job's SSE stream.
    
    Args:
        job_id: Job identifier
        level: Log level ('debug', 'info', 'warning', 'error')
        message: Log message
    """
    emit_progress(
        job_id,
        "log",
        {
            "level": level,
            "message": message,
        },
        log=False,  # Don't double-log
    )


def emit_complete(job_id: str, result: Dict[str, Any]) -> None:
    """Emit a completion event with final result.
    
    Args:
        job_id: Job identifier
        result: Generation result/artifacts
    """
    emit_progress(job_id, "complete", result)
    logger.info(f"Job {job_id} completed successfully")


def emit_error(job_id: str, error: str, details: Dict[str, Any] | None = None) -> None:
    """Emit an error event.
    
    Args:
        job_id: Job identifier
        error: Error message
        details: Optional additional error details
    """
    data = {"error": error}
    if details:
        data["details"] = details

    emit_progress(job_id, "error", data)
    logger.error(f"Job {job_id} failed: {error}")


def cleanup_job(job_id: str) -> None:
    """Clean up job resources after completion.
    
    Args:
        job_id: Job identifier
    """
    if job_id in _active_jobs:
        del _active_jobs[job_id]
        logger.info(f"Cleaned up job {job_id}")


def get_stream_response(job_id: str) -> EventSourceResponse:
    """Create an SSE EventSourceResponse for a job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        EventSourceResponse: FastAPI SSE response
    """
    return EventSourceResponse(
        progress_generator(job_id),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
