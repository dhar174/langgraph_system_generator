"""Opt-in real SDK/emulator qualification; never contact a cloud project."""

import json
import os
import subprocess
import sys
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


def test_emulator_new_process_recovers_lost_worker_and_rejects_old_fence():
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    assert host.startswith(("127.0.0.1:", "localhost:")), "local emulator required"
    firestore = pytest.importorskip("google.cloud.firestore")
    auth = pytest.importorskip("google.auth.credentials")
    client = firestore.Client(
        project="demo-lnf-b1", credentials=auth.AnonymousCredentials()
    )
    store = FirestoreJobStore(
        "demo-lnf-b1", b"e" * 32, client=client, clock=lambda: 1000.0
    )
    owner = Principal(issuer="emulator", subject=uuid.uuid4().hex)
    job = store.accept(
        owner, "process-key", GenerationRequestEnvelope(prompt="offline stub")
    ).job
    old = store.claim(job.job_id, job.version, 0, "lost", job.dispatch.intent_id)
    code = """
import sys,json
from google.cloud import firestore
from google.auth.credentials import AnonymousCredentials
from langgraph_system_generator.jobs.firestore_store import FirestoreJobStore
c=firestore.Client(project="demo-lnf-b1",credentials=AnonymousCredentials())
s=FirestoreJobStore("demo-lnf-b1",b"e"*32,client=c,clock=lambda:1240.0)
s.reconcile(limit=100)
j=s.inspect_attempt(sys.argv[1])
j=s.claim(j.job_id,j.version,j.fencing_token,"replacement",j.dispatch.intent_id)
print(json.dumps({"job_id":j.job_id,"attempt_count":j.attempt_count,"fence":j.fencing_token}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, job.job_id],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    recovered = json.loads(result.stdout)
    assert recovered["job_id"] == old.job_id and recovered["attempt_count"] == 2
    assert recovered["fence"] > old.fencing_token
    from langgraph_system_generator.jobs.models import JobError

    with pytest.raises(JobError):
        store.renew(old.job_id, old.version, old.fencing_token, "lost")
