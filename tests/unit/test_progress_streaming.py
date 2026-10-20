"""Tests for SSE progress streaming behavior."""

from __future__ import annotations

import asyncio
import json

import pytest

from langgraph_system_generator.api import progress_streaming


async def _collect_events(job_id: str, last_event_id: str | None = None):
    events = []
    async for event in progress_streaming.progress_generator(
        job_id, last_event_id=last_event_id
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
    progress_streaming.emit_node_progress(
        job_id, "compose", 50, "Composing notebook..."
    )
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
    job_id = "completed-job"
    progress_streaming._active_jobs[job_id] = progress_streaming.JobRecord(
        created_at=100.0,
        status="completed",
        completed_at=200.0,
    )
    ttl = progress_streaming._COMPLETED_JOB_TTL_SECONDS
    progress_streaming._prune_expired_jobs(now=200.0 + ttl - 1)
    assert job_id in progress_streaming._active_jobs
    progress_streaming._prune_expired_jobs(now=200.0 + ttl)
    assert job_id not in progress_streaming._active_jobs


@pytest.mark.asyncio
async def test_progress_streaming_truncates_history_after_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
):
    """Replay history should stay bounded and emit a truncation marker."""
    monkeypatch.setattr(progress_streaming, "_MAX_EVENTS_PER_JOB", 2, raising=False)

    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(job_id, "start", 0, "Starting generation...")
    progress_streaming.emit_node_progress(
        job_id, "compose", 50, "Composing notebook..."
    )
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


@pytest.mark.asyncio
async def test_reconnect_uses_ids_after_an_omitted_event(monkeypatch):
    monkeypatch.setattr(progress_streaming, "_MAX_EVENTS_PER_JOB", 2)
    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(job_id, "start", 0, "Starting")
    progress_streaming.emit_node_progress(job_id, "build", 50, "Building")
    progress_streaming.emit_log(job_id, "info", "Omitted")
    progress_streaming.emit_complete(job_id, {"success": True})
    record = progress_streaming._active_jobs[job_id]
    marker = next(
        event for event in record.events if event["event"] == "events_truncated"
    )
    assert marker["id"] > 2  # The dropped event had its own ID.

    replay = await _collect_events(job_id, "2")
    assert [event["event"] for event in replay] == ["events_truncated", "complete"]
    assert [int(event["id"]) for event in replay] == [marker["id"], marker["id"] + 1]
    replay_after_marker = await _collect_events(job_id, str(marker["id"]))
    assert [event["event"] for event in replay_after_marker] == ["complete"]
    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", ["garbage", "-1", "1.5"])
async def test_malformed_cursors_report_reset_and_replay_terminal(cursor):
    job_id = progress_streaming.create_job()
    progress_streaming.emit_complete(job_id, {"success": True})
    events = await _collect_events(job_id, cursor)
    assert events[0]["data"]["reason"] == "invalid_event_id"
    assert events[-1]["event"] == "complete"
    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_future_cursor_ends_instead_of_waiting_for_unreachable_id():
    job_id = progress_streaming.create_job()
    events = await asyncio.wait_for(_collect_events(job_id, "99999"), timeout=1)
    assert len(events) == 1
    assert events[0]["data"]["reason"] == "future_event_id"
    assert progress_streaming.get_job_status(job_id)["status"] == "accepted"
    progress_streaming.cleanup_job(job_id, force=True)


@pytest.mark.asyncio
async def test_acknowledged_terminal_is_not_replayed():
    job_id = progress_streaming.create_job()
    progress_streaming.emit_complete(job_id, {"success": True})
    assert await _collect_events(job_id, "0") == []
    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_late_conflicting_terminal_and_progress_cannot_overwrite_completion():
    job_id = progress_streaming.create_job()
    assert progress_streaming.emit_complete(job_id, {"success": True})
    assert not progress_streaming.emit_error(job_id, "late failure")
    assert not progress_streaming.emit_complete(job_id, {"success": False})
    progress_streaming.emit_node_progress(job_id, "late", 50, "late progress")
    events = await _collect_events(job_id)
    assert len(events) == 1
    assert events[0]["data"]["success"] is True
    assert progress_streaming.get_job_status(job_id)["status"] == "completed"
    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_cleanup_never_silently_removes_active_job_after_old_ttl():
    job_id = progress_streaming.create_job()
    progress_streaming._active_jobs[job_id].created_at = 1.0
    progress_streaming._prune_expired_jobs(now=86400.0)
    assert not progress_streaming.cleanup_job(job_id)
    assert progress_streaming.get_job_status(job_id)["status"] == "accepted"
    progress_streaming.emit_error(job_id, "cancelled", status="cancelled")
    events = await _collect_events(job_id)
    assert events[-1]["data"]["status"] == "cancelled"
    assert all(event["event"] != "complete" for event in events)
    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_disconnect_releases_subscriber_without_cancelling_execution():
    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(job_id, "start", 1, "start")
    stream = progress_streaming.progress_generator(job_id)
    first = await anext(stream)
    assert first["event"] == "progress"
    record = progress_streaming._active_jobs[job_id]
    assert len(record.subscribers) == 1
    await stream.aclose()
    assert not record.subscribers
    assert not record.completed
    progress_streaming.emit_complete(job_id, {"success": True})
    assert (await _collect_events(job_id))[-1]["event"] == "complete"
    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_retention_cleanup_while_subscriber_reads_terminal():
    job_id = progress_streaming.create_job()
    progress_streaming.emit_node_progress(job_id, "start", 1, "start")
    stream = progress_streaming.progress_generator(job_id)
    await anext(stream)
    progress_streaming.emit_complete(job_id, {"success": True})
    record = progress_streaming._active_jobs[job_id]
    progress_streaming._prune_expired_jobs(now=record.completed_at + 1000)
    assert job_id not in progress_streaming._active_jobs
    terminal = await anext(stream)
    assert terminal["event"] == "complete"
    await stream.aclose()
    progress_streaming._prune_expired_jobs(now=record.completed_at + 1000)
    assert job_id not in progress_streaming._active_jobs


@pytest.mark.asyncio
async def test_oversized_logs_are_bounded_and_do_not_lose_terminal():
    job_id = progress_streaming.create_job()
    progress_streaming.emit_log(job_id, "info", "x" * 1_000_000)
    progress_streaming.emit_error(job_id, "Generation timed out.", status="expired")
    record = progress_streaming._active_jobs[job_id]
    assert record.event_bytes < progress_streaming._MAX_JOB_EVENT_BYTES
    events = await _collect_events(job_id)
    assert events[0]["event"] == "events_truncated"
    assert events[-1]["data"]["status"] == "expired"
    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_terminal_identifiers_cannot_bypass_payload_byte_bound():
    job_id = progress_streaming.create_job()
    progress_streaming.emit_error(job_id, "failed", code="x" * 100_000)
    record = progress_streaming._active_jobs[job_id]
    assert record.event_bytes < progress_streaming._MAX_EVENT_BYTES
    assert record.status == "failed"
    assert (await _collect_events(job_id))[-1]["event"] == "error"
    progress_streaming.cleanup_job(job_id)


@pytest.mark.asyncio
async def test_pruned_records_cannot_bypass_global_subscriber_capacity(monkeypatch):
    monkeypatch.setattr(progress_streaming, "_MAX_STREAM_SUBSCRIBERS_TOTAL", 1)
    first = progress_streaming.create_job()
    progress_streaming.emit_node_progress(first, "start", 1, "start")
    stream = progress_streaming.progress_generator(first)
    await anext(stream)
    progress_streaming.emit_complete(first, {"success": True})
    record = progress_streaming._active_jobs[first]
    progress_streaming._prune_expired_jobs(now=record.completed_at + 1000)
    assert first not in progress_streaming._active_jobs
    second = progress_streaming.create_job()
    progress_streaming.emit_complete(second, {"success": True})
    denied = await _collect_events(second)
    assert denied[0]["data"]["code"] == "stream_capacity"
    await stream.aclose()
    assert (await _collect_events(second))[-1]["event"] == "complete"
    assert not progress_streaming._stream_subscribers
    progress_streaming.cleanup_job(second)


@pytest.mark.asyncio
async def test_lost_local_state_reports_unavailable_without_false_failure():
    job_id = progress_streaming.create_job()
    progress_streaming.emit_complete(job_id, {"success": True})
    progress_streaming._active_jobs.pop(job_id)
    events = await _collect_events(job_id)
    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["data"]["status"] == "unavailable"
    assert events[0]["data"]["code"] == "job_unavailable"
    assert "success" not in events[0]["data"]
    assert progress_streaming.get_job_status(job_id) is None
