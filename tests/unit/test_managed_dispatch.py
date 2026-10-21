"""Offline failure injection at the outbox/managed queue boundary."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest

from langgraph_system_generator.jobs.cloud_tasks_dispatcher import (
    CloudTasksConfig,
    CloudTasksDispatcher,
)
from langgraph_system_generator.jobs.models import JobError, JobState
from langgraph_system_generator.jobs.reconciliation import Reconciler
from tests.unit.test_durable_job_contracts import accepted
from tests.unit.test_durable_job_contracts import store as _store
from tests.unit.test_firestore_job_store import firestore_transport  # noqa: F401

store = _store
google_errors = pytest.importorskip("google.api_core.exceptions")
AlreadyExists = google_errors.AlreadyExists
DeadlineExceeded = google_errors.DeadlineExceeded
NotFound = google_errors.NotFound

CONFIG = CloudTasksConfig(
    queue="projects/offline-project/locations/us-central1/queues/generation",
    worker_url="https://worker.example.run.app/internal/execute",
    audience="https://worker.example.run.app",
    service_account="tasks-worker@offline-project.iam.gserviceaccount.com",
)


class Queue:
    """Protocol-faithful RPC shape, including reserved-name tombstones."""

    def __init__(self):
        self.tasks = {}
        self.reserved = set()
        self.lose_response = False
        self.calls = []

    def create_task(self, *, request, retry, timeout):
        assert retry is None and 0 < timeout <= 10
        tasks = pytest.importorskip("google.cloud.tasks_v2")
        wire = tasks.CreateTaskRequest(request)
        name = wire.task.name
        self.calls.append(wire)
        if name in self.reserved:
            raise AlreadyExists("reserved")
        self.reserved.add(name)
        self.tasks[name] = SimpleNamespace(name=name)
        if self.lose_response:
            self.lose_response = False
            raise DeadlineExceeded("response lost")
        return self.tasks[name]

    def get_task(self, *, request, retry, timeout):
        assert retry is None and 0 < timeout <= 10
        if request["name"] not in self.tasks:
            raise NotFound("tombstone")
        return self.tasks[request["name"]]


def test_acceptance_crash_is_repaired_and_payload_has_only_references(store):
    backend, _ = store
    job = accepted(backend)
    queue = Queue()
    result = Reconciler(
        backend, CloudTasksDispatcher(CONFIG, client=queue)
    ).reconcile_once()
    assert result["dispatched"] == 1
    saved = backend.inspect_attempt(job.job_id)
    assert not saved.dispatch.pending
    request = queue.calls[0].task.http_request
    assert json.loads(request.body) == {
        "schema_version": 1,
        "job_id": job.job_id,
        "dispatch_generation": 1,
    }
    assert request.oidc_token.audience == CONFIG.audience
    assert request.oidc_token.service_account_email == CONFIG.service_account
    assert request.url == CONFIG.worker_url


def test_create_response_and_mark_update_loss_reuses_one_task(store):
    backend, _ = store
    job = accepted(backend)
    queue = Queue()
    queue.lose_response = True
    dispatcher = CloudTasksDispatcher(CONFIG, client=queue)
    first = dispatcher.dispatch(job.dispatch)  # process dies before mark_dispatched
    second = dispatcher.dispatch(job.dispatch)
    assert first == second and len(queue.tasks) == 1
    Reconciler(backend, dispatcher).reconcile_once()
    assert backend.inspect_attempt(job.job_id).dispatch.task_ref == first


def test_tombstone_is_not_pending_and_new_identity_is_bounded(store):
    backend, clock = store
    job = accepted(backend)
    queue = Queue()
    dispatcher = CloudTasksDispatcher(CONFIG, client=queue)
    name = dispatcher.dispatch(job.dispatch)
    del queue.tasks[name]
    with pytest.raises(JobError, match="dispatch_tombstone"):
        dispatcher.dispatch(job.dispatch)
    reconciler = Reconciler(backend, dispatcher)
    reconciler.reconcile_once()
    fresh = backend.inspect_attempt(job.job_id)
    assert fresh.dispatch.generation == 2
    assert fresh.dispatch.available_at > clock.now
    clock.now = fresh.dispatch.available_at
    reconciler.reconcile_once()
    assert len(queue.tasks) == 1 and name not in queue.tasks
    assert backend.inspect_attempt(job.job_id).attempt_count == 0


def test_lost_delivery_after_mark_and_worker_loss_reconcile_without_api_state(store):
    backend, clock = store
    job = accepted(backend)
    dispatcher = CloudTasksDispatcher(CONFIG, client=Queue())
    Reconciler(backend, dispatcher).reconcile_once()
    marked = backend.inspect_attempt(job.job_id)
    clock.now = marked.next_action_at
    Reconciler(backend, dispatcher).reconcile_once()
    fresh = backend.inspect_attempt(job.job_id)
    assert fresh.dispatch.generation == 2
    claimed = backend.claim(
        job.job_id, fresh.version, fresh.fencing_token, "dead", fresh.dispatch.intent_id
    )
    clock.now = claimed.lease.expires_at
    Reconciler(backend, dispatcher).reconcile_once()
    recovered = backend.inspect_attempt(job.job_id)
    assert recovered.state == JobState.ACCEPTED
    assert recovered.dispatch.generation == 3


def test_overlapping_reconcilers_only_enqueue_one_identity(store):
    backend, _ = store
    job = accepted(backend)
    queue = Queue()
    dispatcher = CloudTasksDispatcher(CONFIG, client=queue)
    barrier = Barrier(2)

    def run():
        barrier.wait(timeout=5)
        return Reconciler(backend, dispatcher).reconcile_once(page_size=1, pages=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sum(r["dispatched"] for r in results) == 1
    assert len(queue.tasks) == 1
    assert not backend.inspect_attempt(job.job_id).dispatch.pending


def test_cancel_before_dispatch_and_deadline_are_not_enqueued(store):
    backend, _ = store
    job = accepted(backend)
    backend.cancel(job.owner, job.job_id, job.version, job.fencing_token)
    queue = Queue()
    Reconciler(backend, CloudTasksDispatcher(CONFIG, client=queue)).reconcile_once()
    assert not queue.tasks


@pytest.mark.parametrize(
    "change",
    [
        {"worker_url": "http://127.0.0.1/internal/execute"},
        {"worker_url": "https://worker.example.run.app/other"},
        {"dispatch_deadline": 1801},
        {"service_account": "evil@example.test"},
        {"service_account": "tasks-worker@another-project.iam.gserviceaccount.com"},
    ],
)
def test_unauthorized_dispatch_configuration(change):
    from dataclasses import asdict

    with pytest.raises(JobError):
        CloudTasksConfig(**(asdict(CONFIG) | change))


def test_repeated_queue_outage_has_finite_persisted_dispatch_budget(store):
    backend, clock = store
    job = accepted(backend)
    queue = Queue()

    def unavailable(**kwargs):
        raise OSError("unavailable")

    queue.create_task = unavailable
    reconciler = Reconciler(backend, CloudTasksDispatcher(CONFIG, client=queue))
    for _ in range(20):
        current = backend.inspect_attempt(job.job_id)
        clock.now = max(clock.now, current.dispatch.available_at)
        reconciler.reconcile_once()
        if backend.inspect_attempt(job.job_id).state == JobState.FAILED:
            break
    saved = backend.inspect_attempt(job.job_id)
    assert saved.state == JobState.FAILED
    assert saved.dispatch.generation == saved.dispatch_limit == 12
    assert saved.attempt_count == 0


def test_reconcile_pages_and_runtime_budget_are_bounded(store):
    backend, _ = store
    job = accepted(backend)
    queue = Queue()
    ticks = iter([0, 0, 31])
    outcome = Reconciler(
        backend, CloudTasksDispatcher(CONFIG, client=queue), clock=lambda: next(ticks)
    ).reconcile_once()
    assert outcome["dispatched"] == 0 and not queue.tasks
    assert backend.inspect_attempt(job.job_id).dispatch.pending
