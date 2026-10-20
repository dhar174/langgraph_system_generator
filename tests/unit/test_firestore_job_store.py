"""Exercise the real adapter with an offline SDK transport, not MemoryDatabase."""

from copy import deepcopy
from threading import RLock
from types import SimpleNamespace

import pytest

from langgraph_system_generator.jobs.firestore_store import (
    FirestoreDatabase,
    FirestoreJobStore,
)
from langgraph_system_generator.jobs.models import GenerationRequestEnvelope, JobError


class FakeClient:
    """SDK-shaped transport enforcing atomic commits and read-before-write."""

    def __init__(self):
        self.documents = {}
        self.lock = RLock()
        self.retry_once = False
        self.callbacks = 0
        self.commits = 0

    def document(self, path):
        class Reference:
            def __init__(self):
                self.path = path

            def get(self, *, transaction, timeout):
                assert timeout == 10
                assert not transaction.writing, "read after write"
                value = deepcopy(transaction.data.get(path))
                return SimpleNamespace(exists=value is not None, to_dict=lambda: value)

        return Reference()

    def transaction(self, *, max_attempts):
        assert max_attempts == 5
        return SimpleNamespace(
            data=None, writing=False, set=self._set, delete=self._delete
        )

    def _set(self, reference, value):
        self.current.writing = True
        self.current.data[reference.path] = deepcopy(value)

    def _delete(self, reference):
        self.current.writing = True
        self.current.data.pop(reference.path, None)

    def execute(self, callback, transaction):
        with self.lock:
            for _ in range(2 if self.retry_once else 1):
                transaction.data = deepcopy(self.documents)
                transaction.writing = False
                self.current = transaction
                self.callbacks += 1
                result = callback(transaction)
            self.documents = transaction.data
            self.commits += 1
            self.retry_once = False
            return result

    def collection(self, name):
        client = self

        class Query:
            def where(self, *, filter):
                self.filter = filter
                return self

            def order_by(self, field):
                assert field == self.filter.field_path
                return self

            def limit(self, limit):
                self.maximum = limit
                return self

            def stream(self, *, timeout):
                assert timeout == 10
                field = self.filter.field_path
                with client.lock:
                    rows = [
                        (data[field], path)
                        for path, data in client.documents.items()
                        if path.count("/") == 1
                        and path.startswith(name + "/")
                        and data.get(field) is not None
                        and data[field] <= self.filter.value
                    ]
                return [
                    SimpleNamespace(reference=SimpleNamespace(path=path))
                    for _, path in sorted(rows)[: self.maximum]
                ]

        return Query()


@pytest.fixture
def firestore_transport(monkeypatch):
    # Install the optional extra to run this qualification. Core suites may skip.
    firestore = pytest.importorskip("google.cloud.firestore")
    monkeypatch.setattr(
        firestore,
        "transactional",
        lambda callback: lambda tx: client.execute(callback, tx),
    )
    client = FakeClient()
    return client


def test_adapter_retried_acceptance_is_atomic(firestore_transport, monkeypatch):
    from langgraph_system_generator.jobs.models import Principal

    client = firestore_transport
    from langgraph_system_generator import cli

    def denied(*args, **kwargs):
        raise AssertionError("transaction may not generate, dispatch or upload")

    monkeypatch.setattr(cli, "generate_artifacts", denied)
    client.retry_once = True
    store = FirestoreJobStore("offline-project", b"x" * 32, client=client)
    accepted = store.accept(
        Principal(issuer="test", subject="a"),
        "secret-user-key",
        GenerationRequestEnvelope(prompt="confidential prompt"),
    )
    assert client.callbacks == 2 and client.commits == 1
    assert len(client.documents) == 4  # job, idempotency, intent, first event
    assert len(store.pending_dispatch()) == 1
    assert all("secret-user-key" not in path for path in client.documents)
    assert all("delete_after" in row for row in client.documents.values())
    assert accepted.job.event_cursor == 1


def test_pending_query_retry_rechecks_clock(firestore_transport):
    from langgraph_system_generator.jobs.models import Principal

    clock = SimpleNamespace(now=1000.0)
    client = firestore_transport
    store = FirestoreJobStore(
        "offline-project", b"x" * 32, client=client, clock=lambda: clock.now
    )
    store.accept(
        Principal(issuer="test", subject="a"),
        "key",
        GenerationRequestEnvelope(prompt="private"),
    )
    original_execute = client.execute

    def execute(callback, tx):
        clock.now = 1900.0
        return original_execute(callback, tx)

    client.execute = execute
    assert store.pending_dispatch() == ()


def test_adapter_rolls_back_partial_write(firestore_transport):
    db = FirestoreDatabase("offline-project", client=firestore_transport)

    def failing(tx):
        tx.set("jobs/example", {"expires_at": 100.0})
        raise JobError("deliberate_failure")

    with pytest.raises(JobError, match="deliberate_failure"):
        db.run(failing)
    assert firestore_transport.documents == {}


def test_adapter_failures_are_structured(monkeypatch):
    firestore = pytest.importorskip("google.cloud.firestore")

    def fail(**kwargs):
        raise RuntimeError("secret ADC path and provider response")

    monkeypatch.setattr(firestore, "Client", fail)
    store = FirestoreJobStore("offline-project", b"x" * 32)
    with pytest.raises(JobError, match="job_backend_unavailable") as error:
        store.pending_dispatch()
    assert error.value.status == 503
    assert "secret" not in str(error.value)
