"""Opt-in real SDK/emulator qualification; never contact a cloud project."""

import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from langgraph_system_generator.jobs.firestore_store import FirestoreJobStore
from langgraph_system_generator.jobs.models import (
    ArtifactRef,
    GenerationRequestEnvelope,
    JobError,
    JobState,
    Principal,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LNF_TEST_FIRESTORE_EMULATOR") != "1",
    reason="opt in with LNF_TEST_FIRESTORE_EMULATOR=1 and a local emulator",
)


def project_id():
    project = os.environ.get("LNF_TEST_PROJECT") or "demo-lnf-" + uuid.uuid4().hex[:16]
    assert project.startswith("demo-lnf-"), "non-production test project required"
    return project


def test_emulator_acceptance_contention_and_fresh_instance_replay(record_property):
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    assert host.startswith(("127.0.0.1:", "localhost:")), "local emulator required"
    firestore = pytest.importorskip("google.cloud.firestore")
    auth = pytest.importorskip("google.auth.credentials")
    project = project_id()
    client = firestore.Client(project=project, credentials=auth.AnonymousCredentials())
    store = FirestoreJobStore(project, b"e" * 32, client=client)
    owner = Principal(issuer="emulator", subject=uuid.uuid4().hex)
    barrier = Barrier(4)
    retries = [0] * 4

    def accept(index):
        barrier.wait(timeout=10)
        for attempt in range(3):
            try:
                return store.accept(
                    owner,
                    "emulator-key",
                    GenerationRequestEnvelope(prompt="offline stub"),
                )
            except JobError as error:
                if (
                    error.code != "job_backend_unavailable"
                    or error.status != 503
                    or attempt == 2
                ):
                    raise
                # The emulator can exhaust SDK retries on lock timeout. Replay
                # the SAME caller request, never change server retry policy.
                retries[index] += 1
                time.sleep(0.25 * (index + 1) * (attempt + 1))

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(accept, range(4)))
    assert sum(item.created for item in results) == 1
    record_property("acceptance_transient_503_replays", json.dumps(retries))
    print("acceptance transient 503 replays:", retries)
    job = results[0].job
    assert len({item.job.job_id for item in results}) == 1
    fresh_client = firestore.Client(
        project=project, credentials=auth.AnonymousCredentials()
    )
    fresh = FirestoreJobStore(project, b"e" * 32, client=fresh_client)
    assert fresh.get(owner, job.job_id) == job
    with pytest.raises(JobError, match="idempotency_conflict"):
        fresh.accept(
            owner, "emulator-key", GenerationRequestEnvelope(prompt="conflict")
        )
    lease = fresh.claim(
        job.job_id, job.version, 0, "emulator-worker", job.dispatch.intent_id
    )
    assert lease.fencing_token == 1
    assert len(fresh.replay(owner, job.job_id).events) == 2
    client.close()
    fresh_client.close()


def test_emulator_new_process_recovers_lost_worker_and_rejects_old_fence():
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    assert host.startswith(("127.0.0.1:", "localhost:")), "local emulator required"
    firestore = pytest.importorskip("google.cloud.firestore")
    auth = pytest.importorskip("google.auth.credentials")
    project = project_id()
    client = firestore.Client(project=project, credentials=auth.AnonymousCredentials())
    store = FirestoreJobStore(project, b"e" * 32, client=client, clock=lambda: 1000.0)
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
c=firestore.Client(project=sys.argv[2],credentials=AnonymousCredentials())
s=FirestoreJobStore(sys.argv[2],b"e"*32,client=c,clock=lambda:1240.0)
s.reconcile(limit=100)
j=s.inspect_attempt(sys.argv[1])
j=s.claim(j.job_id,j.version,j.fencing_token,"replacement",j.dispatch.intent_id)
print(json.dumps({"job_id":j.job_id,"attempt_count":j.attempt_count,"fence":j.fencing_token}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, job.job_id, project],
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
    with pytest.raises(JobError):
        store.renew(old.job_id, old.version, old.fencing_token, "lost")
    with pytest.raises(JobError):
        store.finalize(
            old.job_id,
            old.version,
            old.fencing_token,
            "lost",
            JobState.COMPLETED,
            ArtifactRef(
                bucket="emulator-double",
                object_name=f"runs/{old.run_id}/attempt-1/manifest.json",
                generation="1",
                sha256="a" * 64,
                size_bytes=1,
            ),
        )
    assert store.get(owner, old.job_id).fencing_token == recovered["fence"]
    client.close()


def test_emulator_independent_processes_cannot_both_claim(tmp_path, record_property):
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    assert host.startswith(("127.0.0.1:", "localhost:")), "local emulator required"
    firestore = pytest.importorskip("google.cloud.firestore")
    auth = pytest.importorskip("google.auth.credentials")
    project = project_id()
    client = firestore.Client(project=project, credentials=auth.AnonymousCredentials())
    store = FirestoreJobStore(project, b"e" * 32, client=client, clock=lambda: 1000.0)
    owner = Principal(issuer="emulator", subject=uuid.uuid4().hex)
    job = store.accept(
        owner, "claim-race", GenerationRequestEnvelope(prompt="offline stub")
    ).job
    code = """
import json,sys,time
from pathlib import Path
from google.cloud import firestore
from google.auth.credentials import AnonymousCredentials
from langgraph_system_generator.jobs.firestore_store import FirestoreJobStore
from langgraph_system_generator.jobs.models import JobError
project,job_id,worker,root=sys.argv[1:]
c=firestore.Client(project=project,credentials=AnonymousCredentials())
s=FirestoreJobStore(project,b'e'*32,client=c,clock=lambda:1000.0)
j=s.inspect_attempt(job_id)
Path(root,worker).write_text('ready')
deadline=time.monotonic()+30
while not Path(root,'go').exists():
    if time.monotonic()>deadline: raise RuntimeError('claim barrier timed out')
    time.sleep(.02)
for attempt in range(3):
    try:
        # Preserve this process's ORIGINAL version/fence on every request replay.
        won=s.claim(j.job_id,j.version,j.fencing_token,worker,j.dispatch.intent_id)
        print(json.dumps({'worker':worker,'fence':won.fencing_token,'replays':attempt}))
        break
    except JobError as error:
        if error.code=='job_backend_unavailable' and error.status==503:
            if attempt==2: raise
            time.sleep(.25*(1 if worker=='worker-a' else 2)*(attempt+1))
            continue
        print(json.dumps({'worker':worker,'error':error.code,'replays':attempt}))
        break
c.close()
"""
    workers = ["worker-a", "worker-b"]
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, project, job.job_id, worker, str(tmp_path)],
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for worker in workers
    ]
    try:
        deadline = time.monotonic() + 30
        while not all((tmp_path / worker).is_file() for worker in workers):
            assert all(
                process.poll() is None for process in processes
            ), "claim process failed before barrier"
            assert time.monotonic() < deadline, "claim processes did not become ready"
            time.sleep(0.02)
        (tmp_path / "go").write_text("go", encoding="utf-8")
        assert (tmp_path / "go").read_text(encoding="utf-8") == "go"
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=120)
            assert process.returncode == 0, stdout + stderr
            results.append(json.loads(stdout.strip().splitlines()[-1]))
        winners = [result for result in results if "fence" in result]
        assert len(winners) == 1, results
        assert [result["error"] for result in results if "error" in result] == [
            "job_conflict"
        ]
        record_property(
            "claim_transient_503_replays",
            json.dumps([result["replays"] for result in results]),
        )
        print("claim transient 503 replays:", [result["replays"] for result in results])
        current = store.get(owner, job.job_id)
        assert current.attempt_count == current.fencing_token == 1
        assert current.lease.worker_id == winners[0]["worker"]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
        client.close()
