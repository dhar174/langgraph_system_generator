"""Server-Sent Events for real-time progress and log streaming.

This module provides SSE-based progress tracking for long-running generation tasks.
It uses in-memory queues for simplicity in Phase 1, suitable for single-server deployments.
For production multi-server deployments, consider using Redis pub/sub or similar.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

# In-memory job tracking
# NOTE: This is suitable for development and single-server deployments.
# For production with multiple servers, use Redis pub/sub or similar distributed queue.
_active_jobs: Dict[str, asyncio.Queue] = {}
_job_metadata: Dict[str, Dict[str, Any]] = {}

# Maximum events to buffer per job (prevents memory exhaustion)
_MAX_QUEUE_SIZE = 1000

# Job cleanup TTL - jobs are cleaned up after this time regardless of completion
_JOB_TTL_SECONDS = 3600  # 1 hour

# Completed job retention - keep completed jobs for clients that connect late
_COMPLETED_JOB_TTL_SECONDS = 300  # 5 minutes


def create_job() -> str:
    """Create a new job and return its ID.
    
    Returns:
        str: Unique job identifier (UUID)
    """
    job_id = str(uuid4())
    # Use bounded queue to prevent memory exhaustion
    _active_jobs[job_id] = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
    _job_metadata[job_id] = {
        "created_at": time.time(),
        "completed": False,
        "completed_at": None,
    }
    logger.info(f"Created job {job_id}")
    
    # Schedule cleanup even if client never connects
    # Only schedule if we're in an async context (event loop running)
    try:
        asyncio.create_task(_schedule_job_cleanup(job_id))
    except RuntimeError:
        # No event loop running - schedule will happen when server starts
        logger.debug(f"Job {job_id} created outside event loop, cleanup will be scheduled later")
    
    return job_id


async def _schedule_job_cleanup(job_id: str) -> None:
    """Schedule cleanup for a job after TTL expires.
    
    This ensures jobs are cleaned up even if:
    - Client never connects to stream
    - Job completes but client doesn't consume all events
    - Stream connection is interrupted
    
    Args:
        job_id: Job identifier to clean up
    """
    await asyncio.sleep(_JOB_TTL_SECONDS)
    
    if job_id in _job_metadata:
        logger.info(f"Cleaning up job {job_id} after TTL expiration")
        cleanup_job(job_id)


async def progress_generator(job_id: str) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream progress events for a specific job via Server-Sent Events.
    
    Note: This does NOT clean up the job on disconnect. Jobs are kept until
    completion and cleaned up via TTL to allow:
    - Late-connecting clients to receive events
    - Reconnection without losing progress
    - Multiple clients to stream the same job
    
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
                # Mark job as completed but don't clean up yet
                if job_id in _job_metadata:
                    _job_metadata[job_id]["completed"] = True
                    _job_metadata[job_id]["completed_at"] = time.time()
                    # Schedule cleanup after completed job TTL
                    try:
                        asyncio.create_task(_schedule_completed_job_cleanup(job_id))
                    except RuntimeError:
                        logger.debug(f"Cannot schedule cleanup for {job_id} - no event loop")
                break

    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled for job {job_id} - keeping job for reconnection")
        raise
    except Exception as e:
        logger.exception(f"Error in progress generator for job {job_id}")
        yield {
            "event": "error",
            "data": json.dumps({"error": f"Stream error: {str(e)}"}),
        }


async def _schedule_completed_job_cleanup(job_id: str) -> None:
    """Schedule cleanup for a completed job after shorter TTL.
    
    Args:
        job_id: Job identifier to clean up
    """
    await asyncio.sleep(_COMPLETED_JOB_TTL_SECONDS)
    
    if job_id in _job_metadata and _job_metadata[job_id]["completed"]:
        logger.info(f"Cleaning up completed job {job_id} after retention period")
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
    """Clean up job resources after completion or TTL expiration.
    
    Args:
        job_id: Job identifier
    """
    if job_id in _active_jobs:
        del _active_jobs[job_id]
    if job_id in _job_metadata:
        del _job_metadata[job_id]
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
