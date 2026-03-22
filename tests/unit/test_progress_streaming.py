"""Tests for SSE progress streaming behavior."""

from __future__ import annotations

import asyncio
import json

import pytest

from langgraph_system_generator.api import progress_streaming


async def _collect_events(job_id: str, last_event_id: str | None = None):
    events = []
    async for event in progress_streaming.progress_generator(
        job_id,
        last_event_id=last_event_id,
    ):
        payload = json.loads(event["data"])
        events.append(
            {
                "id": event.get("id"),
                "event": event["event"],
                "data": payload,
            }
        )
    return events


async def _collect_n_events(job_id: str, count: int):
    events = []
    async for event in progress_streaming.progress_generator(job_id):
        payload = json.loads(event["data"])
        events.append(
            {
                "id": event.get("id"),
                "event": event["event"],
                "data": payload,
            }
        )
        if len(events) == count:
            break
    return events


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_event_log():
    """Each subscriber should get the full event stream independently."""

    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(
        job_id,
        "start",
        0,
        "Starting generation...",
    )
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
    """A reconnecting client should resume after the acknowledged event."""

    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(
        job_id,
        "start",
        0,
        "Starting generation...",
    )
    progress_streaming.emit_node_progress(
        job_id,
        "compose",
        50,
        "Composing notebook...",
    )
    progress_streaming.emit_complete(job_id, {"success": True})

    resumed = await _collect_events(job_id, last_event_id="0")

    assert [event["event"] for event in resumed] == ["progress", "complete"]
    assert resumed[0]["data"]["message"] == "Composing notebook..."
    assert resumed[1]["data"]["success"] is True

    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_progress_streaming_resumes_when_last_event_id_is_ahead_of_log():
    """A future Last-Event-ID should still allow later events through."""

    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(
        job_id,
        "start",
        0,
        "Starting generation...",
    )

    collector = asyncio.create_task(
        _collect_events(job_id, last_event_id="999")
    )
    await asyncio.sleep(0)
    progress_streaming.emit_complete(job_id, {"success": True})

    resumed = await collector

    assert [event["event"] for event in resumed] == ["complete"]
    assert resumed[0]["data"]["success"] is True

    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_progress_streaming_caps_retained_event_log(monkeypatch):
    """The in-memory replay log should not grow without bound."""

    monkeypatch.setattr(progress_streaming, "_MAX_RECORDED_EVENTS", 3)
    job_id = progress_streaming.create_job()

    progress_streaming.emit_node_progress(job_id, "step-1", 10, "Step 1")
    progress_streaming.emit_node_progress(job_id, "step-2", 20, "Step 2")
    progress_streaming.emit_node_progress(job_id, "step-3", 30, "Step 3")
    progress_streaming.emit_complete(job_id, {"success": True})

    retained = await _collect_events(job_id)

    assert [event["event"] for event in retained] == [
        "progress",
        "progress",
        "complete",
    ]
    assert retained[0]["data"]["message"] == "Step 2"
    assert retained[1]["data"]["message"] == "Step 3"
    assert retained[2]["data"]["success"] is True

    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_progress_streaming_continues_after_retention_rollover(
    monkeypatch,
):
    """A live subscriber should keep later events flowing after rollover."""

    monkeypatch.setattr(progress_streaming, "_MAX_RECORDED_EVENTS", 2)
    job_id = progress_streaming.create_job()

    collector = asyncio.create_task(_collect_n_events(job_id, 2))
    await asyncio.sleep(0)

    progress_streaming.emit_node_progress(job_id, "step-1", 10, "Step 1")
    progress_streaming.emit_node_progress(job_id, "step-2", 20, "Step 2")

    first_batch = await collector

    progress_streaming.emit_node_progress(job_id, "step-3", 30, "Step 3")
    progress_streaming.emit_complete(job_id, {"success": True})

    retained = await _collect_events(
        job_id,
        last_event_id=first_batch[-1]["id"],
    )

    assert [event["data"]["message"] for event in first_batch] == [
        "Step 1",
        "Step 2",
    ]
    assert [event["event"] for event in retained] == ["progress", "complete"]
    assert retained[0]["data"]["message"] == "Step 3"
    assert retained[-1]["data"]["success"] is True

    progress_streaming.cleanup_job(job_id)
