"""Request-bound worker failure policy and hard subprocess deadline checks."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from langgraph_system_generator.jobs.execution import ExecutionLimits, SubprocessAttempt
from langgraph_system_generator.jobs.models import (
    ArtifactRef,
    JobError,
    JobState,
    ServiceIdentity,
)
from langgraph_system_generator.jobs.service import WorkerJobService
from langgraph_system_generator.jobs.worker import ManagedWorker, TaskPayload
from tests.unit.test_durable_job_contracts import accepted
from tests.unit.test_durable_job_contracts import store as _store
from tests.unit.test_firestore_job_store import firestore_transport  # noqa: F401

store = _store


def service(backend):
    return WorkerJobService(
        backend,
        ServiceIdentity(service_account="worker", audience="aud"),
        audience="aud",
        allowed_accounts=frozenset({"worker"}),
    )


def payload(job):
    return TaskPayload(job_id=job.job_id, dispatch_generation=job.dispatch.generation)


def result(job):
    return ArtifactRef(
        bucket="private-bucket",
        object_name=f"runs/{job.run_id}/attempt-{job.fencing_token}/manifest.json",
        generation="1",
        sha256="a" * 64,
        size_bytes=1,
    )


async def test_worker_completion_ack_and_redelivery_do_not_regenerate(store, tmp_path):
    backend, _ = store
    job = accepted(backend)
    runner = AsyncMock()
    runner.run.side_effect = lambda claimed, directory, progress: result(claimed)
    worker = ManagedWorker(backend, runner, tmp_path)
    assert (await worker.execute(service(backend), payload(job)))[0] == 200
    assert (await worker.execute(service(backend), payload(job)))[0] == 200
    assert runner.run.await_count == 1
    assert backend.inspect_attempt(job.job_id).state == JobState.COMPLETED


async def test_active_duplicate_is_retryable_then_loss_recovers(store, tmp_path):
    backend, clock = store
    job = accepted(backend)
    running = service(backend).claim(job.job_id, job.dispatch.intent_id, "dead")
    runner = AsyncMock()
    runner.run.side_effect = lambda claimed, directory, progress: result(claimed)
    worker = ManagedWorker(backend, runner, tmp_path)
    assert (await worker.execute(service(backend), payload(job)))[0] == 503
    clock.now = running.lease.expires_at
    backend.reconcile()
    fresh = backend.inspect_attempt(job.job_id)
    assert (await worker.execute(service(backend), payload(job)))[0] == 204
    assert (await worker.execute(service(backend), payload(fresh)))[0] == 200
    assert runner.run.await_count == 1


async def test_cancellation_against_final_uploads_cannot_publish(store, tmp_path):
    backend, _ = store
    job = accepted(backend)
    runner = AsyncMock()

    def cancel(claimed, directory, progress):
        backend.cancel(
            claimed.owner, claimed.job_id, claimed.version, claimed.fencing_token
        )
        return result(claimed)

    runner.run.side_effect = cancel
    await ManagedWorker(backend, runner, tmp_path).execute(
        service(backend), payload(job)
    )
    saved = backend.inspect_attempt(job.job_id)
    assert saved.state == JobState.CANCELLED and saved.result is None


async def test_failure_persists_retry_before_ack_and_never_grows_attempt_cap(
    store, tmp_path
):
    backend, clock = store
    job = accepted(backend)
    runner = AsyncMock()
    runner.run.side_effect = JobError("attempt_infrastructure_failure", 503)
    worker = ManagedWorker(backend, runner, tmp_path)
    for _ in range(3):
        current = backend.inspect_attempt(job.job_id)
        clock.now = max(clock.now, current.dispatch.available_at)
        status, _ = await worker.execute(service(backend), payload(current))
        assert status == 200
    saved = backend.inspect_attempt(job.job_id)
    assert saved.state == JobState.FAILED and saved.attempt_count == 3


async def test_heartbeat_outage_stops_attempt_without_publication(
    store, tmp_path, monkeypatch
):
    backend, _ = store
    job = accepted(backend)
    stopped = asyncio.Event()
    runner = AsyncMock()

    async def run(*args):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    runner.run.side_effect = run
    monkeypatch.setattr(
        backend,
        "renew",
        lambda *args: (_ for _ in ()).throw(JobError("job_backend_unavailable", 503)),
    )
    worker = ManagedWorker(backend, runner, tmp_path, heartbeat_seconds=0.01)
    assert (await worker.execute(service(backend), payload(job)))[0] == 503
    assert stopped.is_set() and backend.inspect_attempt(job.job_id).result is None


async def test_noncooperative_process_is_reaped_at_deadline(tmp_path):
    # A real second process ignores cooperative asyncio cancellation entirely.
    runner = SubprocessAttempt(
        ExecutionLimits(
            generation_seconds=1,
            publication_margin=1,
            attempt_seconds=2,
            http_timeout=4,
            dispatch_deadline=5,
        ),
        command=(
            sys.executable,
            "-c",
            'import sys,time; sys.stdin.readline(); print(\'{"kind":"ready"}\',flush=True); time.sleep(60)',
        ),
    )
    with pytest.raises(JobError, match="attempt_deadline"):
        await runner.run(None, tmp_path, lambda value: None)
    assert runner.last_process.returncode is not None


@pytest.mark.parametrize(
    "values",
    [
        {"generation_seconds": 241},
        {"attempt_seconds": 240},
        {"http_timeout": 299},
        {"dispatch_deadline": 1801},
    ],
)
def test_deadline_configuration_fails_closed(values):
    with pytest.raises(JobError):
        ExecutionLimits(**values)


async def test_publication_phase_deadline_is_measured_from_marker(
    monkeypatch, tmp_path
):
    from langgraph_system_generator.jobs import execution

    ticks = iter([1000, 1005, 1010, 1011])
    monkeypatch.setattr(
        execution, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )
    process = SimpleNamespace(
        stdin=SimpleNamespace(write=Mock(), drain=AsyncMock(), close=Mock()),
        stdout=SimpleNamespace(
            readline=AsyncMock(
                side_effect=[b'{"kind":"publishing"}\n', JobError("injected_exit", 503)]
            )
        ),
        returncode=None,
        kill=Mock(),
        wait=AsyncMock(return_value=-9),
    )
    monkeypatch.setattr(
        execution.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    waits = []

    async def observed_wait(awaitable, timeout):
        waits.append(timeout)
        return await awaitable

    monkeypatch.setattr(execution.asyncio, "wait_for", observed_wait)
    with pytest.raises(JobError, match="injected_exit"):
        await SubprocessAttempt().run(None, tmp_path, lambda value: None)
    assert waits[-1] == 44


async def test_completion_commit_response_loss_redelivery_returns_same_result(
    store, tmp_path, monkeypatch
):
    backend, _ = store
    job = accepted(backend)
    original = backend.finalize

    def committed_then_lost(*args, **kwargs):
        original(*args, **kwargs)
        raise JobError("job_backend_unavailable", 503)

    monkeypatch.setattr(backend, "finalize", committed_then_lost)
    runner = AsyncMock()
    runner.run.side_effect = lambda claimed, directory, progress: result(claimed)
    worker = ManagedWorker(backend, runner, tmp_path)
    assert (await worker.execute(service(backend), payload(job)))[0] == 503
    saved = backend.inspect_attempt(job.job_id)
    assert saved.state == JobState.COMPLETED
    assert (
        await ManagedWorker(backend, runner, tmp_path).execute(
            service(backend), payload(job)
        )
    )[0] == 200
    assert runner.run.await_count == 1


async def test_persisted_cancellation_during_generation_stops_execution(
    store, tmp_path
):
    backend, _ = store
    job = accepted(backend)
    ready, stopped = asyncio.Event(), asyncio.Event()
    runner = AsyncMock()

    async def run(*args):
        ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    runner.run.side_effect = run
    worker = ManagedWorker(backend, runner, tmp_path, heartbeat_seconds=0.01)
    delivery = asyncio.create_task(worker.execute(service(backend), payload(job)))
    await ready.wait()
    current = backend.inspect_attempt(job.job_id)
    backend.cancel(
        current.owner, current.job_id, current.version, current.fencing_token
    )
    assert (await delivery)[0] == 503
    assert (
        stopped.is_set()
        and backend.inspect_attempt(job.job_id).state == JobState.CANCELLED
    )


async def test_noncooperative_process_holds_capacity_until_reaped(store, tmp_path):
    backend, clock = store
    job = accepted(backend)
    ready = asyncio.Event()
    limits = ExecutionLimits(
        generation_seconds=1,
        publication_margin=1,
        attempt_seconds=2,
        http_timeout=4,
        dispatch_deadline=5,
    )

    class Runner(SubprocessAttempt):
        async def run(self, job, directory, progress):
            def observed(value):
                ready.set()
                progress(value)

            return await super().run(job, directory, observed)

    runner = Runner(
        limits,
        clock=clock,
        command=(
            sys.executable,
            "-S",  # Trusted progress/sleep fixture, independent of SDK startup.
            "-c",
            'import sys,time; sys.stdin.readline(); print(\'{"kind":"progress","value":1}\',flush=True); time.sleep(60)',
        ),
    )
    worker = ManagedWorker(backend, runner, tmp_path, limits=limits)
    delivery = asyncio.create_task(worker.execute(service(backend), payload(job)))
    progress_seen = asyncio.create_task(ready.wait())
    try:
        done, _ = await asyncio.wait(
            {progress_seen, delivery}, timeout=10, return_when=asyncio.FIRST_COMPLETED
        )
        assert progress_seen in done, (
            delivery.result() if delivery.done() else "progress readiness timed out"
        )
        assert (await worker.execute(service(backend), payload(job)))[0] == 503
        assert not delivery.done() and runner.last_process.returncode is None
        assert (await delivery)[0] == 200  # retry intent recorded after kill/reap
        assert runner.last_process.returncode is not None
    finally:
        for task in (progress_seen, delivery):
            if not task.done():
                task.cancel()
        await asyncio.gather(progress_seen, delivery, return_exceptions=True)


async def test_same_job_after_all_api_and_worker_dictionaries_are_discarded(
    store, tmp_path
):
    from langgraph_system_generator.jobs.firestore_store import FirestoreJobStore
    from langgraph_system_generator.jobs.memory_store import InMemoryJobStore

    backend, clock = store
    job = accepted(backend)
    old = service(backend).claim(job.job_id, job.dispatch.intent_id, "lost-process")
    clock.now = old.lease.expires_at
    if isinstance(backend, FirestoreJobStore):
        replacement = FirestoreJobStore(
            "offline-project", b"x" * 32, client=backend.db._client, clock=clock
        )
    else:
        replacement = InMemoryJobStore(b"x" * 32, clock=clock)
        replacement.db.documents = backend.db.documents
    replacement.reconcile()
    runner = AsyncMock()
    runner.run.side_effect = lambda claimed, directory, progress: result(claimed)
    fresh = replacement.inspect_attempt(job.job_id)
    assert (
        await ManagedWorker(replacement, runner, tmp_path).execute(
            service(replacement), payload(fresh)
        )
    )[0] == 200
    assert replacement.inspect_attempt(job.job_id).job_id == job.job_id
    assert not replacement.accept(job.owner, "same-key", job.request).created
