"""Offline integration: independent ASGI apps, real adapters, fake SDK transports.

These tests are explicitly not emulator, deployment, or IAM qualification.
"""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest

from langgraph_system_generator.api import progress_streaming, server
from langgraph_system_generator.api.durable import DurableRuntime
from langgraph_system_generator.jobs.firestore_store import FirestoreJobStore
from langgraph_system_generator.jobs.gcs_artifacts import GCSArtifactStore
from langgraph_system_generator.jobs.models import (
    GenerationRequestEnvelope,
    JobError,
    JobState,
)
from langgraph_system_generator.jobs.retention import RetentionCleaner
from langgraph_system_generator.jobs.service import (
    AdmissionLimits,
    TransactionalJobStore,
)
from tests.unit.test_durable_job_contracts import racing
from tests.unit.test_durable_job_contracts import store as _store
from tests.unit.test_firestore_job_store import firestore_transport  # noqa: F401
from tests.unit.test_job_identity import identity as _identity
from tests.unit.test_private_artifacts import Storage, outputs

store = _store
identity = _identity
BODY = {"prompt": "Build a private support router", "mode": "stub"}


@pytest.fixture
def harness(store, identity, monkeypatch, tmp_path):
    backend, clock = store
    verifier, sign, _, identity_clock, _ = identity
    identity_clock.side_effect = clock
    backend.admission_limits = AdmissionLimits()
    storage = Storage()
    generate = AsyncMock(
        side_effect=AssertionError("durable API may not generate locally")
    )
    monkeypatch.setattr(server, "generate_artifacts", generate)
    monkeypatch.setenv("LNF_JOB_BACKEND", "firestore")
    monkeypatch.setenv("LNF_API_ACCESS_MODE", "iap")

    def headers(subject="stable-user-id", key="one-action"):
        return {
            "X-Goog-IAP-JWT-Assertion": sign(
                {"sub": subject, "iat": clock.now - 10, "exp": clock.now + 500}
            ),
            "Idempotency-Key": key,
        }

    def fresh_store():
        # New adapter, sharing only the external fake database transport.
        if isinstance(backend, FirestoreJobStore):
            return FirestoreJobStore(
                "offline-project",
                b"x" * 32,
                client=backend.db._client,
                clock=clock,
                max_events=4,
                admission_limits=AdmissionLimits(),
            )
        return TransactionalJobStore(
            backend.db,
            b"x" * 32,
            clock=clock,
            max_events=4,
            admission_limits=AdmissionLimits(),
        )

    def fresh_runtime():
        return DurableRuntime(
            fresh_store(),
            GCSArtifactStore("private-offline-bucket", tmp_path, client=storage),
            verifier,
            True,
            clock=clock,
        )

    @asynccontextmanager
    async def client(subject="stable-user-id", runtime=None):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=server.create_api_app(runtime or fresh_runtime())
            ),
            base_url="https://api.test",
            headers=headers(subject),
        ) as value:
            yield value

    def complete(job_id, worker="worker", directory="attempt"):
        job = backend.inspect_attempt(job_id)
        job = backend.claim(
            job_id, job.version, job.fencing_token, worker, job.dispatch.intent_id
        )
        files = outputs(tmp_path / directory)
        objects = fresh_runtime().artifacts
        ref = objects.publish_manifest(job, files, job.fencing_token)
        return backend.finalize(
            job.job_id, job.version, job.fencing_token, worker, JobState.COMPLETED, ref
        )

    return backend, clock, storage, headers, client, fresh_runtime, complete, generate


async def test_api_a_accepts_api_b_reads_replays_downloads_after_fresh_instances(
    harness, monkeypatch
):
    backend, _, storage, _, client, _, complete, generate = harness
    async with client() as api_a:
        response = await api_a.post("/generate-async", json=BODY)
    assert response.status_code == 200
    accepted = response.json()
    assert accepted["status"] == "started" and accepted["durable"] is True
    job = backend.inspect_attempt(accepted["job_id"])
    assert job.dispatch.pending and backend.pending_dispatch() == (job.dispatch,)
    committed = complete(job.job_id)

    class ForbiddenLocalDict(dict):
        def get(self, *args):
            raise AssertionError("durable read used process-local authority")

    monkeypatch.setattr(server, "_api_runs", ForbiddenLocalDict())
    monkeypatch.setattr(progress_streaming, "_active_jobs", ForbiddenLocalDict())
    async with client() as api_b:
        assert (await api_b.get(f"/jobs/{job.job_id}")).json()["status"] == "completed"
        result = await api_b.get(f"/jobs/{job.job_id}/result")
        assert result.status_code == 200
        manifest = result.json()["manifest"]
        assert manifest["artifact_contract"]["storage_type"] == "gcs_private"
        stream = await api_b.get(accepted["stream_url"])
        assert stream.text.count("event: complete") == 1
        assert f'"result_url":"/jobs/{job.job_id}/result"' in stream.text
        for entry in manifest["artifact_contract"]["standalone_files"]:
            download = await api_b.get(entry["api_download_path"])
            assert download.status_code == 200
            assert len(download.content) == entry["size_bytes"]
            assert download.headers["content-disposition"].startswith("attachment;")
            assert download.headers["x-content-type-options"] == "nosniff"
            if entry.get("manifest_key") == "manifest_path":
                assert download.json() == manifest
        expected = storage.objects[committed.result.object_name][0]
        assert json.loads(expected) == manifest
    generate.assert_not_awaited()


async def test_duplicate_lost_submit_response_conflict_and_distinct_action(harness):
    backend, _, _, headers, client, _, _, _ = harness
    async with client() as api_a:
        first = await api_a.post("/generate-async", json=BODY)
    async with client() as api_b:
        retry = await api_b.post("/generate-async", json=BODY)
        assert retry.json()["job_id"] == first.json()["job_id"]
        assert retry.json()["idempotent_replay"] is True
        assert (
            await api_b.post("/generate-async", json={**BODY, "prompt": "different"})
        ).status_code == 409
        distinct = await api_b.post(
            "/generate-async", json=BODY, headers=headers(key="new-action")
        )
        assert distinct.json()["job_id"] != first.json()["job_id"]
        missing = {**headers(), "Idempotency-Key": ""}
        assert (
            await api_b.post("/generate-async", json=BODY, headers=missing)
        ).status_code == 400
    assert len(backend.pending_dispatch()) == 2


async def test_every_wrong_owner_surface_matches_nonexistent(harness):
    _, _, _, _, client, _, complete, _ = harness
    async with client() as owner:
        job = (await owner.post("/generate-async", json=BODY)).json()
    completed = complete(job["job_id"])
    async with client("other-subject-same-email") as other:
        paths = [
            f'/jobs/{job["job_id"]}',
            f'/jobs/{job["job_id"]}/result',
            job["stream_url"],
            f"/artifacts?run_id={completed.run_id}&artifact=manifest.json",
        ]
        for path in paths:
            response = await other.get(path)
            absent = await other.get(
                path.replace(job["job_id"], "0" * 32).replace(
                    completed.run_id, "0" * 32
                )
            )
            assert response.status_code == absent.status_code == 404
            assert (
                response.json()
                == absent.json()
                == {"detail": {"code": "job_unavailable"}}
            )
            assert BODY["prompt"] not in response.text
        assert (await other.post(f'/jobs/{job["job_id"]}/cancel')).status_code == 404


async def test_sync_rejected_before_side_effects_and_request_options_preserved(harness):
    backend, _, _, _, client, _, _, generate = harness
    async with client() as api:
        sync = await api.post(
            "/generate",
            json={
                **BODY,
                "output_dir": "../../escape",
                "custom_endpoint": "http://169.254.169.254",
            },
        )
        assert (
            sync.status_code == 409
            and sync.json()["detail"]["code"] == "durable_requires_async"
        )
        body = {
            **BODY,
            "temperature": 0.3,
            "max_tokens": 100,
            "formats": ["html", "ipynb"],
            "messages": [{"role": "user", "content": "keep this dialog"}],
        }
        response = await api.post("/generate-async", json=body)
        assert response.status_code == 200
        envelope = backend.inspect_attempt(response.json()["job_id"]).request
        assert envelope.temperature == 0.3 and envelope.max_tokens == 100
        assert (
            envelope.formats == ("html", "ipynb")
            and envelope.messages[0].content == "keep this dialog"
        )
        assert envelope.architecture is None  # preserve generator auto-selection
        assert (
            await api.post("/generate-async", json={**BODY, "output_dir": "custom"})
        ).json()["detail"]["code"] == "durable_output_dir_unsupported"
        assert (
            await api.post("/generate-async", content=b" " * 65537)
        ).status_code == 413
    generate.assert_not_awaited()


async def test_cancel_idempotence_and_completion_race(harness):
    backend, _, _, _, client, _, _, _ = harness
    async with client() as api:
        job_id = (await api.post("/generate-async", json=BODY)).json()["job_id"]
        first = await api.post(f"/jobs/{job_id}/cancel")
        second = await api.post(f"/jobs/{job_id}/cancel")
        assert first.json() == second.json()
        assert first.json()["status"] == "cancelled"
        assert (await api.get(f"/jobs/{job_id}/result")).status_code == 409
        assert (await api.get(f"/stream/{job_id}")).text.count(
            "generation_cancelled"
        ) == 1
    assert backend.inspect_attempt(job_id).cancellation_requested


async def test_worker_loss_reconciliation_rejects_old_publication(harness):
    backend, clock, _, _, client, _, complete, _ = harness
    async with client() as api_a:
        job_id = (await api_a.post("/generate-async", json=BODY)).json()["job_id"]
    job = backend.inspect_attempt(job_id)
    old = backend.claim(job_id, job.version, 0, "lost-worker", job.dispatch.intent_id)
    clock.now = old.lease.expires_at
    backend.reconcile()
    completed = complete(job_id, "replacement", "replacement")
    with pytest.raises(JobError):
        backend.finalize(
            job_id,
            old.version,
            old.fencing_token,
            "lost-worker",
            JobState.COMPLETED,
            completed.result,
        )
    async with client() as restarted:
        assert (await restarted.get(f"/jobs/{job_id}/result")).status_code == 200
    assert completed.attempt_count == 2


@pytest.mark.parametrize("cursor", ["bogus", "99999999", "0"])
async def test_sse_cursors_and_terminal_survive_history_pruning(harness, cursor):
    _, clock, _, _, client, _, complete, _ = harness
    async with client() as api:
        accepted = (await api.post("/generate-async", json=BODY)).json()
    job = complete(accepted["job_id"])
    clock.now = job.event_expires_at
    async with client() as api_b:
        response = await api_b.get(
            accepted["stream_url"], headers={"Last-Event-ID": cursor}
        )
        assert (
            response.status_code == 200 and "event: events_truncated" in response.text
        )
        assert response.text.count("event: complete") == (
            0 if cursor == "99999999" else 1
        )
        replay = await api_b.get(
            accepted["stream_url"], headers={"Last-Event-ID": str(job.event_cursor)}
        )
        assert "event: complete" not in replay.text
        assert (await api_b.get(f"/jobs/{job.job_id}/result")).status_code == 200


async def test_logical_expiry_blocks_all_access_before_deletion(harness):
    _, clock, storage, _, client, _, complete, _ = harness
    async with client() as api:
        job = complete((await api.post("/generate-async", json=BODY)).json()["job_id"])
    clock.now = job.expires_at
    assert storage.objects  # asynchronous physical deletion has not run
    async with client() as api:
        for path in [
            f"/jobs/{job.job_id}",
            f"/jobs/{job.job_id}/result",
            f"/stream/{job.job_id}",
            f"/artifacts?run_id={job.run_id}&artifact=notebook.ipynb",
        ]:
            assert (await api.get(path)).status_code == 404
        assert (await api.post(f"/jobs/{job.job_id}/cancel")).status_code == 404


async def test_deleted_and_corrupt_object_is_honest_failure(harness):
    _, _, storage, _, client, _, complete, _ = harness
    async with client() as api:
        job = complete((await api.post("/generate-async", json=BODY)).json()["job_id"])
        manifest = (await api.get(f"/jobs/{job.job_id}/result")).json()["manifest"]
        reference = manifest["objects"][0]["object_name"]
        storage.objects[reference] = (b"corrupt", "text/html")
        download = await api.get(
            f"/artifacts?run_id={job.run_id}&artifact=notebook.ipynb"
        )
        assert download.status_code == 503
        del storage.objects[job.result.object_name]
        assert (await api.get(f"/jobs/{job.job_id}/result")).status_code == 503
        assert (
            await api.get(f"/artifacts?run_id={job.run_id}&artifact=../../secret")
        ).status_code == 404


def test_global_owner_admission_and_active_limits_are_atomic(store):
    backend, _ = store
    backend.admission_limits = AdmissionLimits(
        pending=3, active=1, owner_pending=2, owner_active=1
    )
    from tests.unit.test_durable_job_contracts import OTHER, OWNER

    outcomes = racing(
        *[
            lambda index=index: backend.accept(
                OWNER, f"action-{index}", GenerationRequestEnvelope(prompt="same")
            )
            for index in range(4)
        ]
    )
    admitted = [value.job for value in outcomes if not isinstance(value, JobError)]
    assert len(admitted) == 2
    assert [value.status for value in outcomes if isinstance(value, JobError)] == [
        429,
        429,
    ]
    third = backend.accept(OTHER, "other", GenerationRequestEnvelope(prompt="same")).job
    with pytest.raises(JobError, match="job_global_capacity"):
        backend.accept(OTHER, "other-2", GenerationRequestEnvelope(prompt="same"))
    first = admitted[0]
    first = backend.claim(
        first.job_id, first.version, first.fencing_token, "w1", first.dispatch.intent_id
    )
    with pytest.raises(JobError, match="job_global_capacity"):
        backend.claim(
            third.job_id,
            third.version,
            third.fencing_token,
            "w2",
            third.dispatch.intent_id,
        )
    backend.cancel(OWNER, first.job_id, first.version, first.fencing_token)
    assert (
        backend.claim(
            third.job_id,
            third.version,
            third.fencing_token,
            "w2",
            third.dispatch.intent_id,
        ).state
        == JobState.RUNNING
    )


async def test_bounded_cleanup_preserves_winner_then_removes_events_before_parent(
    harness,
):
    backend, clock, storage, _, client, runtime, complete, _ = harness
    async with client() as api:
        job = complete((await api.post("/generate-async", json=BODY)).json()["job_id"])
    storage.objects[f"runs/{job.run_id}/attempt-0/notebook.html"] = (
        b"orphan",
        "text/html",
    )
    cleaner = RetentionCleaner(backend, runtime().artifacts, clock=clock)
    clock.now = job.deadline_at + 86400
    receipt = cleaner.sweep(limit=1)
    assert receipt["cleanup_completed"] == 1
    assert job.result.object_name in storage.objects
    assert not any("attempt-0" in key for key in storage.objects)
    assert backend.replay(job.owner, job.job_id).events == ()
    assert backend.get(job.owner, job.job_id).result == job.result
    clock.now = job.expires_at
    assert cleaner.sweep(limit=1)["cleanup_completed"] == 1
    assert not storage.objects
    assert not any(
        path.startswith(f"jobs/{job.job_id}")
        for path in (
            backend.db.documents
            if hasattr(backend.db, "documents")
            else backend.db._client.documents
        )
    )


async def test_capabilities_readback_drain_and_fail_closed(harness, monkeypatch):
    _, _, _, _, client, runtime, _, generate = harness
    readback = runtime()
    readback.submissions = False
    async with client(runtime=readback) as api:
        capabilities = (await api.get("/health")).json()
        assert capabilities["ready"] and capabilities["sync_generation"] is False
        assert capabilities["generation_enabled"] is False
        assert (await api.post("/generate-async", json=BODY)).status_code == 503
        assert (await api.get("/ready")).status_code == 200
    monkeypatch.setenv("LNF_API_ACCESS_MODE", "single-operator")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.create_api_app()),
        base_url="https://api.test",
    ) as api:
        health = (await api.get("/health")).json()
        assert not health["ready"] and not health["generation_enabled"]
        assert (await api.get("/ready")).status_code == 503
        assert (await api.post("/generate-async", json=BODY)).status_code == 503
    generate.assert_not_awaited()


async def test_stream_rechecks_identity_and_releases_capacity(harness):
    from fastapi import Request

    from langgraph_system_generator.api import durable

    _, clock, _, headers, client, fresh_runtime, _, _ = harness
    async with client() as api:
        job_id = (await api.post("/generate-async", json=BODY)).json()["job_id"]
    runtime = fresh_runtime()
    runtime.poll_seconds = 0
    app = server.create_api_app(runtime)
    scope = {
        "type": "http",
        "method": "GET",
        "path": f"/stream/{job_id}",
        "headers": [
            (key.lower().encode(), value.encode()) for key, value in headers().items()
        ],
        "app": app,
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    response = await durable.stream(Request(scope, receive), job_id)
    assert "event: progress" in await anext(response.body_iterator)
    clock.now += 600  # original signed assertion now expired
    assert await anext(response.body_iterator) == ": keepalive\n\n"
    assert "identity_invalid" in await anext(response.body_iterator)
    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)
    assert not runtime.owner_streams
    assert runtime.streams.acquire(blocking=False)
    runtime.streams.release()


async def test_html_is_attachment_and_manifest_size_matches_committed_bytes(
    harness, tmp_path
):
    backend, _, _, _, client, runtime, _, _ = harness
    async with client() as api:
        job_id = (await api.post("/generate-async", json=BODY)).json()["job_id"]
        job = backend.inspect_attempt(job_id)
        job = backend.claim(job_id, job.version, 0, "worker", job.dispatch.intent_id)
        notebook, manifest = outputs(tmp_path / "html")
        html = notebook.parent / "notebook.html"
        html.write_text("<script>unsafeOrigin()</script>", encoding="utf-8")
        metadata = json.loads(manifest.read_text())
        metadata["artifact_contract"]["standalone_files"].append(
            {"path": str(html), "exists": True}
        )
        manifest.write_text(json.dumps(metadata), encoding="utf-8")
        assert html.read_text(encoding="utf-8").startswith("<script>")
        assert (
            len(
                json.loads(manifest.read_text())["artifact_contract"][
                    "standalone_files"
                ]
            )
            == 2
        )
        ref = runtime().artifacts.publish_manifest(
            job, (notebook, manifest, html), job.fencing_token
        )
        backend.finalize(
            job_id, job.version, job.fencing_token, "worker", JobState.COMPLETED, ref
        )
        response = await api.get(
            f"/artifacts?run_id={job.run_id}&artifact=notebook.html"
        )
        assert response.status_code == 200 and response.text.startswith("<script>")
        assert (
            response.headers["content-disposition"]
            == 'attachment; filename="notebook.html"'
        )
        assert response.headers["content-security-policy"].startswith("sandbox;")


def test_cleanup_cannot_remove_current_attempt_or_unexpired_winner(harness, tmp_path):
    backend, clock, storage, _, _, runtime, _, _ = harness
    from tests.unit.test_durable_job_contracts import OWNER

    job = backend.accept(
        OWNER, "cleanup-active", GenerationRequestEnvelope(prompt="active")
    ).job
    job = backend.claim(job.job_id, job.version, 0, "worker", job.dispatch.intent_id)
    files = outputs(tmp_path / "uncommitted")
    ref = runtime().artifacts.publish_manifest(job, files, job.fencing_token)
    before = dict(storage.objects)
    clock.now = job.deadline_at + 86400
    with pytest.raises(JobError, match="artifact_cleanup_requires_retention"):
        runtime().artifacts.cleanup_run(job, now=clock.now)
    assert storage.objects == before and ref.object_name in storage.objects


@pytest.mark.parametrize("crossing", ["before_headers", "first_chunk"])
async def test_download_expiry_boundary_never_returns_short_success(
    harness, monkeypatch, crossing
):
    _, clock, _, _, client, runtime, complete, _ = harness
    selected = runtime()
    async with client(runtime=selected) as api:
        job = complete((await api.post("/generate-async", json=BODY)).json()["job_id"])
        original = selected.artifacts.open_verified

        def open_object(ref):
            source = original(ref)
            if not ref.object_name.endswith("notebook.ipynb"):
                return source
            if crossing == "before_headers":
                clock.now = job.expires_at
                return source

            class CrossOnRead:
                def read(self, size):
                    clock.now = job.expires_at
                    return source.read(size)

                def close(self):
                    source.close()

            return CrossOnRead()

        monkeypatch.setattr(selected.artifacts, "open_verified", open_object)
        response = await api.get(
            f"/artifacts?run_id={job.run_id}&artifact=notebook.ipynb"
        )
        if crossing == "before_headers":
            assert response.status_code == 404
        else:
            assert response.status_code == 200
            assert len(response.content) == int(response.headers["content-length"]) > 0


async def test_cleanup_clock_crossing_preserves_inventory_until_expired_object_sweep(
    harness, monkeypatch
):
    backend, clock, storage, _, client, runtime, complete, _ = harness
    async with client() as api:
        job = complete((await api.post("/generate-async", json=BODY)).json()["job_id"])
    artifacts = runtime().artifacts
    original = artifacts.cleanup_run
    clock.now = job.expires_at - 1

    def crossing(snapshot, *, now, limit):
        outcome = original(snapshot, now=now, limit=limit)
        clock.now = job.expires_at
        return outcome

    monkeypatch.setattr(artifacts, "cleanup_run", crossing)
    cleaner = RetentionCleaner(backend, artifacts, clock=clock)
    receipt = cleaner.sweep(limit=1)
    assert receipt["cleanup_completed"] == 0 and receipt["cleanup_deferred"] == 1
    assert job.result.object_name in storage.objects
    assert backend.cleanup_candidates()[0].job_id == job.job_id
    assert cleaner.sweep(limit=1)["cleanup_completed"] == 1
    assert not storage.objects and backend.cleanup_candidates() == ()


async def test_worker_log_is_bounded_redacted_owner_scoped_and_replayable(
    harness, tmp_path
):
    from langgraph_system_generator.jobs.worker import ManagedWorker, TaskPayload
    from tests.unit.test_managed_worker import service

    backend, _, _, _, client, runtime, _, _ = harness
    async with client() as api:
        job_id = (await api.post("/generate-async", json=BODY)).json()["job_id"]
    job = backend.inspect_attempt(job_id)

    async def run(claimed, directory, progress):
        progress(("warning", "api_key=private-synthetic-value " + "a" * 900))
        return runtime().artifacts.publish_manifest(
            claimed, outputs(tmp_path / "logged"), claimed.fencing_token
        )

    runner = AsyncMock()
    runner.run.side_effect = run
    worker = ManagedWorker(backend, runner, tmp_path / "worker")
    assert (
        await worker.execute(
            service(backend), TaskPayload(job_id=job_id, dispatch_generation=1)
        )
    )[0] == 200
    events = backend.replay(job.owner, job_id).events
    logs = [event for event in events if event.kind == "log"]
    assert len(logs) == 1 and logs[0].log_level == "warning"
    assert len(logs[0].log_message) <= 512
    assert "private-synthetic-value" not in logs[0].log_message
    async with client() as api:
        response = await api.get(f"/stream/{job_id}")
        assert "event: log" in response.text and '"level":"warning"' in response.text
        assert response.text.count("event: complete") == 1
    async with client("other") as other:
        assert (await other.get(f"/stream/{job_id}")).status_code == 404


async def test_cancelled_object_read_retains_capacity_until_thread_settles(harness):
    import asyncio
    from threading import BoundedSemaphore, Event

    from langgraph_system_generator.api.durable import _bounded_read

    selected = harness[5]()
    selected.downloads = BoundedSemaphore(1)
    entered, release = Event(), Event()
    disposed = asyncio.Event()

    def read():
        entered.set()
        assert release.wait(timeout=10)
        return "late-file"

    pending = asyncio.create_task(
        _bounded_read(selected, read, lambda value: disposed.set())
    )
    assert await asyncio.to_thread(entered.wait, 10)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    with pytest.raises(JobError, match="artifact_read_capacity"):
        await _bounded_read(selected, lambda: "must not run")
    release.set()
    await asyncio.wait_for(disposed.wait(), 10)
    assert selected.downloads.acquire(blocking=False)
    selected.downloads.release()


@pytest.mark.parametrize("expired", ["identity", "retention"])
async def test_pruned_terminal_frame_cannot_bypass_fresh_access_check(harness, expired):
    from fastapi import Request

    from langgraph_system_generator.api import durable

    backend, clock, _, headers, client, runtime, complete, _ = harness
    async with client() as api:
        job = complete((await api.post("/generate-async", json=BODY)).json()["job_id"])
    clock.now = job.event_expires_at
    if expired == "retention":

        def shorten_test_retention(tx):
            row = tx.get(f"jobs/{job.job_id}")
            row["expires_at"] = clock.now + 1
            tx.set(f"jobs/{job.job_id}", row)

        backend.db.run(shorten_test_retention)
    selected = runtime()
    app = server.create_api_app(selected)
    scope = {
        "type": "http",
        "method": "GET",
        "path": f"/stream/{job.job_id}",
        "headers": [
            (key.lower().encode(), value.encode()) for key, value in headers().items()
        ],
        "app": app,
    }
    response = await durable.stream(Request(scope), job.job_id)
    assert "event: events_truncated" in await anext(response.body_iterator)
    clock.now += 600 if expired == "identity" else 1
    frame = await anext(response.body_iterator)
    assert "event: complete" not in frame
    assert "event: error" in frame
    assert ("identity_invalid" if expired == "identity" else "job_unavailable") in frame
    with pytest.raises(StopAsyncIteration):
        await anext(response.body_iterator)
    assert not selected.owner_streams
