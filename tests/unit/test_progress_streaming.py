"""Tests for SSE progress streaming behavior."""

from __future__ import annotations

import asyncio
import json
import time

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


@pytest.mark.asyncio
async def test_completed_job_cleanup_waits_for_retention_window(
    monkeypatch: pytest.MonkeyPatch,
):
    """Completed jobs should not be removed before the retention window expires."""
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    job_id = "completed-job"
    progress_streaming._active_jobs[job_id] = progress_streaming.JobRecord(
        created_at=time.time(),
        completed=True,
    )
    monkeypatch.setattr(progress_streaming.asyncio, "sleep", fake_sleep)

    await progress_streaming._schedule_completed_job_cleanup(job_id)

    assert sleep_calls == [progress_streaming._COMPLETED_JOB_TTL_SECONDS]
    assert job_id not in progress_streaming._active_jobs
@pytest.mark.asyncio
async def test_progress_streaming_truncates_history_after_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
):
    """Replay history should stay bounded and emit a truncation marker."""
    monkeypatch.setattr(progress_streaming, "_MAX_EVENTS_PER_JOB", 2, raising=False)

    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(job_id, "start", 0, "Starting generation...")
    progress_streaming.emit_node_progress(job_id, "compose", 50, "Composing notebook...")
    progress_streaming.emit_log(job_id, "info", "This event should be dropped")
    progress_streaming.emit_complete(job_id, {"success": True})

    events = await _collect_events(job_id)

    assert [event["event"] for event in events] == [
        "progress",
        "progress",
        "events_truncated",
        "complete",
    ]
    assert events[2]["data"]["max_events"] == 2
    assert "truncated" in events[2]["data"]["message"].lower()
    assert events[3]["data"]["success"] is True

    progress_streaming.cleanup_job(job_id)
