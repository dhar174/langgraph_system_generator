"""The same state-machine contract runs against both storage adapters."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from langgraph_system_generator.jobs.firestore_store import FirestoreJobStore
from langgraph_system_generator.jobs.memory_store import InMemoryJobStore
from langgraph_system_generator.jobs.models import (
    ArtifactRef,
    GenerationRequestEnvelope,
    JobError,
    JobState,
    Principal,
)
from langgraph_system_generator.jobs.registry import select_job_store
from tests.unit.test_firestore_job_store import firestore_transport  # noqa: F401

OWNER = Principal(issuer="test", subject="alice", email="alice@example.test")
OTHER = Principal(issuer="test", subject="bob", email="alice@example.test")
REQUEST = GenerationRequestEnvelope(prompt="private prompt")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(params=["memory", "firestore"])
def store(request):
    clock = Clock()
    if request.param == "memory":
        result = InMemoryJobStore(b"x" * 32, clock=clock, max_events=4)
    else:
        client = request.getfixturevalue("firestore_transport")
        result = FirestoreJobStore(
            "offline-project", b"x" * 32, client=client, clock=clock, max_events=4
        )
    return result, clock


def racing(*calls):
    barrier = Barrier(len(calls))

    def run(call):
        barrier.wait(timeout=10)
        try:
            return call()
        except JobError as error:
            return error

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


def accepted(store):
    return store.accept(OWNER, "same-key", REQUEST).job


def running(store):
    job = accepted(store)
    return store.claim(
        job.job_id, job.version, job.fencing_token, "worker-a", job.dispatch.intent_id
    )


def result_for(job):
    return ArtifactRef(
        bucket="private-artifacts",
        object_name=f"runs/{job.run_id}/attempt-1/manifest.json",
        generation="100",
        sha256="a" * 64,
        size_bytes=42,
    )


def test_concurrent_idempotent_acceptance(store):
    backend, _ = store
    results = racing(*[lambda: backend.accept(OWNER, "same-key", REQUEST)] * 8)
    assert sum(result.created for result in results) == 1
    assert len({result.job.job_id for result in results}) == 1
    assert len(backend.pending_dispatch()) == 1


def test_conflicting_replay_and_owner_isolation(store):
    backend, _ = store
    job = accepted(backend)
    with pytest.raises(JobError, match="idempotency_conflict") as error:
        backend.accept(OWNER, "same-key", GenerationRequestEnvelope(prompt="different"))
    assert error.value.status == 409
    other = backend.accept(OTHER, "same-key", REQUEST).job
    assert other.job_id != job.job_id
    with pytest.raises(JobError, match="job_unavailable"):
        backend.get(OTHER, job.job_id)
    with pytest.raises(JobError):
        backend.replay(OTHER, job.job_id)
    with pytest.raises(JobError):
        backend.cancel(OTHER, job.job_id, job.version, job.fencing_token)
    renamed = OWNER.model_copy(update={"email": "changed@example.test"})
    assert backend.get(renamed, job.job_id) == job


def test_two_workers_only_one_claim(store):
    backend, _ = store
    job = accepted(backend)
    results = racing(
        lambda: backend.claim(
            job.job_id, job.version, 0, "worker-a", job.dispatch.intent_id
        ),
        lambda: backend.claim(
            job.job_id, job.version, 0, "worker-b", job.dispatch.intent_id
        ),
    )
    assert sum(isinstance(result, JobError) for result in results) == 1
    assert backend.get(OWNER, job.job_id).attempt_count == 1


@pytest.mark.parametrize("takeover", [False, True])
def test_expired_and_replaced_authority_cannot_write(store, takeover):
    backend, clock = store
    job = running(backend)
    clock.now = job.lease.expires_at
    if takeover:
        replacement = backend.claim(
            job.job_id,
            job.version,
            job.fencing_token,
            "worker-b",
            job.dispatch.intent_id,
        )
        assert replacement.fencing_token > job.fencing_token
    for operation in (
        lambda: backend.renew(job.job_id, job.version, job.fencing_token, "worker-a"),
        lambda: backend.append_event(
            job.job_id, job.version, job.fencing_token, "worker-a", 50
        ),
        lambda: backend.relinquish(
            job.job_id, job.version, job.fencing_token, "worker-a"
        ),
        lambda: backend.finalize(
            job.job_id,
            job.version,
            job.fencing_token,
            "worker-a",
            JobState.COMPLETED,
            result_for(job),
        ),
    ):
        with pytest.raises(JobError):
            operation()
    with pytest.raises(JobError):
        backend.cancel(OWNER, job.job_id, job.version, job.fencing_token)


def test_completion_cancellation_race_and_terminal_immutability(store):
    backend, _ = store
    job = running(backend)
    results = racing(
        lambda: backend.cancel(OWNER, job.job_id, job.version, job.fencing_token),
        lambda: backend.finalize(
            job.job_id,
            job.version,
            job.fencing_token,
            "worker-a",
            JobState.COMPLETED,
            result_for(job),
        ),
    )
    assert sum(isinstance(result, JobError) for result in results) == 1
    final = backend.get(OWNER, job.job_id)
    assert final.state in {JobState.COMPLETED, JobState.CANCELLED}
    assert (final.result is not None) == (final.state == JobState.COMPLETED)
    with pytest.raises(JobError, match="job_terminal"):
        backend.cancel(OWNER, job.job_id, final.version, final.fencing_token)
    assert backend.get(OWNER, job.job_id) == final


@pytest.mark.parametrize("winner", ["cancel", "complete"])
def test_both_terminal_orderings(store, winner):
    backend, _ = store
    job = running(backend)
    if winner == "cancel":
        final = backend.cancel(OWNER, job.job_id, job.version, job.fencing_token)
        with pytest.raises(JobError):
            backend.finalize(
                job.job_id,
                job.version,
                job.fencing_token,
                "worker-a",
                JobState.COMPLETED,
                result_for(job),
            )
    else:
        final = backend.finalize(
            job.job_id,
            job.version,
            job.fencing_token,
            "worker-a",
            JobState.COMPLETED,
            result_for(job),
        )
        with pytest.raises(JobError):
            backend.cancel(OWNER, job.job_id, job.version, job.fencing_token)
    assert backend.get(OWNER, job.job_id) == final


def test_fence_independent_of_version(store):
    backend, clock = store
    old = running(backend)
    clock.now = old.lease.expires_at
    current = backend.claim(
        old.job_id, old.version, old.fencing_token, "worker-b", old.dispatch.intent_id
    )
    for operation in (
        lambda: backend.renew(
            old.job_id, current.version, old.fencing_token, "worker-b"
        ),
        lambda: backend.append_event(
            old.job_id, current.version, old.fencing_token, "worker-b", 50
        ),
        lambda: backend.finalize(
            old.job_id,
            current.version,
            old.fencing_token,
            "worker-b",
            JobState.COMPLETED,
            result_for(old),
        ),
        lambda: backend.cancel(OWNER, old.job_id, current.version, old.fencing_token),
        lambda: backend.relinquish(
            old.job_id, current.version, old.fencing_token, "worker-b"
        ),
    ):
        with pytest.raises(JobError, match="job_conflict"):
            operation()


def test_replaced_dispatch_and_future_cursor(store):
    backend, _ = store
    job = running(backend)
    previous_intent = job.dispatch.intent_id
    job = backend.relinquish(job.job_id, job.version, job.fencing_token, "worker-a")
    with pytest.raises(JobError, match="dispatch_conflict"):
        backend.claim(
            job.job_id, job.version, job.fencing_token, "worker-b", previous_intent
        )
    with pytest.raises(JobError, match="job_cursor_future"):
        backend.replay(OWNER, job.job_id, after=job.event_cursor + 1)


def test_internal_identity_boundary(store):
    from langgraph_system_generator.jobs.models import ServiceIdentity
    from langgraph_system_generator.jobs.service import WorkerJobService

    backend, _ = store
    options = {
        "audience": "https://worker.run.app",
        "allowed_accounts": frozenset({"worker@example.test"}),
    }
    for identity in (
        OWNER,
        ServiceIdentity(
            service_account="attacker@example.test", audience=options["audience"]
        ),
        ServiceIdentity(service_account="worker@example.test", audience="wrong"),
    ):
        with pytest.raises(JobError, match="worker_identity_forbidden"):
            WorkerJobService(backend, identity, **options)
    worker = WorkerJobService(
        backend,
        ServiceIdentity(
            service_account="worker@example.test", audience=options["audience"]
        ),
        **options,
    )
    job = accepted(backend)
    job = worker.claim(job.job_id, job.dispatch.intent_id, "worker-a")
    job = worker.append_event(job, "worker-a", 10)
    assert job.state == JobState.RUNNING
    from unittest.mock import Mock

    verifier = Mock()
    verifier.verify.return_value = worker.identity
    verified_worker = WorkerJobService.from_authorization(
        backend, verifier, "fake-internal-oidc", **options
    )
    verifier.verify.assert_called_once_with("fake-internal-oidc")
    assert verified_worker.identity == worker.identity


def test_invalid_progress_rollback_and_wrong_worker(store):
    from pydantic import ValidationError

    backend, _ = store
    job = running(backend)
    with pytest.raises((JobError, ValidationError)):
        backend.append_event(
            job.job_id, job.version, job.fencing_token, "worker-a", 101
        )
    assert backend.get(OWNER, job.job_id) == job
    with pytest.raises(JobError, match="job_lease_lost"):
        backend.renew(job.job_id, job.version, job.fencing_token, "worker-b")


def test_events_bounded_paginated_across_attempts(store):
    backend, _ = store
    job = running(backend)
    for progress in range(10):
        job = backend.append_event(
            job.job_id, job.version, job.fencing_token, "worker-a", progress
        )
    job = backend.relinquish(job.job_id, job.version, job.fencing_token, "worker-a")
    job = backend.claim(
        job.job_id, job.version, job.fencing_token, "worker-b", job.dispatch.intent_id
    )
    first = backend.replay(OWNER, job.job_id, limit=2)
    second = backend.replay(OWNER, job.job_id, after=first.next_cursor, limit=2)
    events = first.events + second.events
    assert len(events) == 4 and first.truncated and not second.truncated
    assert [event.event_id for event in events] == list(
        range(job.event_cursor - 3, job.event_cursor + 1)
    )
    assert events[-1].fencing_token > events[0].fencing_token
    assert "private prompt" not in str(events)
    documents = (
        backend.db.documents
        if hasattr(backend.db, "documents")
        else backend.db._client.documents
    )
    retained = [row for path, row in documents.items() if "/events/" in path]
    assert len(retained) == 4
    assert all(len(str(row).encode("utf-8")) < 512 for row in retained)


def test_access_expiry_before_physical_ttl_and_idempotency_window(store):
    backend, clock = store
    job = running(backend)
    final = backend.finalize(
        job.job_id,
        job.version,
        job.fencing_token,
        "worker-a",
        JobState.COMPLETED,
        result_for(job),
    )
    clock.now = final.event_expires_at
    assert backend.replay(OWNER, job.job_id).events == ()
    assert backend.get(OWNER, job.job_id).result == final.result
    # Same key may start new work at the explicit 24-hour boundary.
    assert backend.accept(OWNER, "same-key", REQUEST).job.job_id != job.job_id
    clock.now = final.expires_at
    with pytest.raises(JobError, match="job_unavailable"):
        backend.get(OWNER, job.job_id)
    with pytest.raises(JobError):
        backend.replay(OWNER, job.job_id)


def test_renew_retry_dispatch_and_reconciliation(store):
    backend, clock = store
    job = accepted(backend)
    intent = backend.pending_dispatch()[0]
    job = backend.mark_dispatched(
        job.job_id, job.version, 0, intent.intent_id, "projects/p/queues/q/tasks/t"
    )
    assert backend.pending_dispatch() == ()
    job = backend.claim(job.job_id, job.version, 0, "worker-a", job.dispatch.intent_id)
    clock.now += 10
    job = backend.renew(job.job_id, job.version, job.fencing_token, "worker-a")
    for _ in range(3):
        clock.now = job.lease.expires_at
        assert backend.reconcile(limit=1).changed == (job.job_id,)
        job = backend.get(OWNER, job.job_id)
        if job.state == JobState.FAILED:
            break
        assert backend.pending_dispatch()[0].generation == job.dispatch.generation
        job = backend.claim(
            job.job_id,
            job.version,
            job.fencing_token,
            "worker-a",
            job.dispatch.intent_id,
        )
    assert job.state == JobState.FAILED and job.attempt_count == 3
    assert backend.reconcile().changed == ()


def test_overall_deadline(store):
    backend, clock = store
    job = accepted(backend)
    clock.now = job.deadline_at
    assert backend.pending_dispatch() == ()
    assert backend.reconcile().changed == (job.job_id,)
    assert backend.get(OWNER, job.job_id).state == JobState.EXPIRED


def test_unapproved_provider_and_forged_generator_version(store):
    backend, _ = store
    with pytest.raises(JobError, match="job_provider_not_approved"):
        backend.accept(
            OWNER, "provider", REQUEST.model_copy(update={"provider_ref": "unknown"})
        )
    with pytest.raises(JobError, match="job_generator_version_invalid"):
        backend.accept(
            OWNER, "version", REQUEST.model_copy(update={"generator_version": "forged"})
        )
    assert backend.pending_dispatch() == ()


def test_backend_selection_and_fail_closed_api(monkeypatch):
    from fastapi.testclient import TestClient

    from langgraph_system_generator.api import server

    assert select_job_store({}) is None
    with pytest.raises(JobError, match="job_backend_invalid"):
        select_job_store({"LNF_JOB_BACKEND": "typo"})
    with pytest.raises(JobError, match="job_configuration_invalid"):
        select_job_store({"LNF_JOB_BACKEND": "firestore"})
    monkeypatch.setenv("LNF_JOB_BACKEND", "firestore")
    with TestClient(server.app) as client:
        assert client.get("/health").json()["generation_enabled"] is False
        for route in ("/generate", "/generate-async"):
            response = client.post(route, json={"prompt": "test", "mode": "stub"})
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "durable_admission_disabled"


def test_imports_without_cloud_credentials_or_network(tmp_path):
    root = Path(__file__).resolve().parents[2] / "src"
    code = """
import importlib.abc, sys, socket
class DenyCloud(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("google", "jwt")):
            raise ImportError("cloud disabled")
sys.meta_path.insert(0, DenyCloud())
def denied(*args, **kwargs):
    raise AssertionError("network disabled")
socket.socket.connect = denied
socket.create_connection = denied
socket.getaddrinfo = denied
import langgraph_system_generator as package
from langgraph_system_generator.api import server
from langgraph_system_generator.jobs.registry import select_job_store
from langgraph_system_generator.api.identity import IAPVerifier
from langgraph_system_generator.jobs.models import JobError, Principal, GenerationRequestEnvelope
assert select_job_store({}) is None
store = select_job_store({"LNF_JOB_BACKEND":"firestore", "LNF_JOB_GCP_PROJECT":"offline-project", "LNF_JOB_IDEMPOTENCY_SECRET":"x"*32})
try:
    store.accept(Principal(issuer="t", subject="u"), "k", GenerationRequestEnvelope(prompt="p"))
except JobError as error:
    assert error.code == "job_backend_unavailable"
else:
    raise AssertionError("unexpected fallback")
print(package.__file__)
"""
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(word in key for word in ("KEY", "TOKEN", "CREDENTIAL", "SECRET"))
    }
    env["PYTHONPATH"] = str(root)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert str(root) in result.stdout
