"""Opt-in real SDK/emulator qualification; never contact a cloud project."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from langgraph_system_generator.jobs.firestore_store import FirestoreJobStore
from langgraph_system_generator.jobs.models import GenerationRequestEnvelope, Principal

pytestmark = pytest.mark.skipif(
    os.getenv("LNF_TEST_FIRESTORE_EMULATOR") != "1",
    reason="opt in with LNF_TEST_FIRESTORE_EMULATOR=1 and a local emulator",
)


def test_emulator_acceptance_contention_and_fresh_instance_replay():
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    assert host.startswith(("127.0.0.1:", "localhost:")), "local emulator required"
    firestore = pytest.importorskip("google.cloud.firestore")
    auth = pytest.importorskip("google.auth.credentials")
    client = firestore.Client(
        project="demo-lnf-b1", credentials=auth.AnonymousCredentials()
    )
    store = FirestoreJobStore("demo-lnf-b1", b"e" * 32, client=client)
    owner = Principal(issuer="emulator", subject=uuid.uuid4().hex)
    barrier = Barrier(4)

    def accept(_):
        barrier.wait(timeout=10)
        return store.accept(
            owner, "emulator-key", GenerationRequestEnvelope(prompt="offline stub")
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(accept, range(4)))
    assert sum(item.created for item in results) == 1
    job = results[0].job
    fresh = FirestoreJobStore("demo-lnf-b1", b"e" * 32, client=client)
    assert fresh.get(owner, job.job_id) == job
    lease = fresh.claim(
        job.job_id, job.version, 0, "emulator-worker", job.dispatch.intent_id
    )
    assert lease.fencing_token == 1
    assert len(fresh.replay(owner, job.job_id).events) == 2
