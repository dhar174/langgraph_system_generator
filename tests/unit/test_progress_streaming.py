"""Tests for SSE progress streaming behavior."""

from __future__ import annotations

import json

import pytest

from langgraph_system_generator.api import progress_streaming


async def _collect_events(job_id: str, last_event_id: str | None = None):
    events = []
    async for event in progress_streaming.progress_generator(job_id, last_event_id=last_event_id):
        payload = json.loads(event["data"])
        events.append(
            {
                "id": event.get("id"),
                "event": event["event"],
                "data": payload,
            }
        )
    return events


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_event_log():
    """Each subscriber should get the full event stream independently."""
    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(job_id, "start", 0, "Starting generation...")
    progress_streaming.emit_complete(job_id, {"success": True})

    first = await _collect_events(job_id)
    second = await _collect_events(job_id)

    assert [event["event"] for event in first] == ["progress", "complete"]
    assert [event["event"] for event in second] == ["progress", "complete"]
    assert first[0]["data"]["message"] == "Starting generation..."
    assert second[1]["data"]["success"] is True

    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_progress_streaming_resumes_after_last_event_id():
    """A reconnecting client should resume after the last acknowledged event."""
    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(job_id, "start", 0, "Starting generation...")
    progress_streaming.emit_node_progress(job_id, "compose", 50, "Composing notebook...")
    progress_streaming.emit_complete(job_id, {"success": True})

    resumed = await _collect_events(job_id, last_event_id="0")

    assert [event["event"] for event in resumed] == ["progress", "complete"]
    assert resumed[0]["data"]["message"] == "Composing notebook..."
    assert resumed[1]["data"]["success"] is True

    progress_streaming.cleanup_job(job_id)
