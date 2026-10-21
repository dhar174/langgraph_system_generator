"""Opt-in separate-process API/worker recovery against the real Firestore emulator.

Object bytes use a disk-backed GCS transport double, explicitly not a GCS emulator
or IAM proof. Each subprocess starts new API/worker/store objects without inherited
Python dictionaries. The crashed worker exits after private upload, before commit.
"""

import hashlib
import json
import os
import subprocess
import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("LNF_TEST_FIRESTORE_EMULATOR") != "1",
    reason="opt in with a local Firestore emulator",
)


PROBE = r"""
import asyncio,base64,hashlib,json,os,sys
from pathlib import Path
from types import SimpleNamespace
from google.cloud import firestore
from google.auth.credentials import AnonymousCredentials
import httpx,jwt
from langgraph_system_generator.api.identity import IAPVerifier,TrustedIAPKeys
from langgraph_system_generator.api.durable import DurableRuntime
from langgraph_system_generator.api.server import create_api_app
from langgraph_system_generator.jobs.firestore_store import FirestoreJobStore
from langgraph_system_generator.jobs.gcs_artifacts import GCSArtifactStore
from langgraph_system_generator.jobs.models import DurableJob,ArtifactRef,JobError,JobState
from tests.unit.test_private_artifacts import outputs
root=Path(os.environ['LNF_PROBE_ROOT'])
clock=lambda:float(sys.argv[2])
store=FirestoreJobStore(os.environ['LNF_PROBE_PROJECT'],b'e'*32,client=firestore.Client(project=os.environ['LNF_PROBE_PROJECT'],credentials=AnonymousCredentials()),clock=clock)
class Blob:
    def __init__(self,name,generation=None):
        self.name,self.generation=name,generation
        self.path=root/'objects'/base64.urlsafe_b64encode(name.encode()).decode()
    def upload_from_string(self,data,*,content_type,if_generation_match,**kw):
        assert if_generation_match==0
        self.path.parent.mkdir(exist_ok=True)
        with self.path.open('xb') as out: out.write(data)
        self.generation=1
        self.content_type=content_type
    def reload(self,**kw): self.size=self.path.stat().st_size
    def download_as_bytes(self,**kw): return self.path.read_bytes()
    def download_to_file(self,target,**kw): target.write(self.path.read_bytes())
class Storage:
    def bucket(self,name): return SimpleNamespace(blob=lambda name,generation=None:Blob(name,generation))
artifacts=GCSArtifactStore('private-emulator-double',root,client=Storage())
aud='/projects/123456/locations/us-central1/services/test-api'
public=(root/'public.pem').read_text()
verifier=IAPVerifier(aud,TrustedIAPKeys(lambda:{'trusted':public},clock=clock),clock=clock)
subject=sys.argv[4] if len(sys.argv)>4 else 'owner'
token=jwt.encode({'iss':'https://cloud.google.com/iap','sub':subject,'aud':aud,'iat':clock()-1,'exp':clock()+500},(root/'private.pem').read_text(),algorithm='ES256',headers={'kid':'trusted'})
job_id=sys.argv[3]
action=sys.argv[1]
async def main():
    if action=='stale':
        old=json.loads((root/'lost-attempt.json').read_text())
        j=DurableJob.model_validate(old['job'])
        try: store.finalize(j.job_id,j.version,j.fencing_token,'process-worker',JobState.COMPLETED,ArtifactRef.model_validate(old['ref']))
        except JobError as error: print(json.dumps({'error':error.code}),flush=True)
        else: raise AssertionError('superseded worker committed')
        return
    if action in ('crash','recover'):
        if action=='recover': store.reconcile()
        j=store.inspect_attempt(job_id)
        j=store.claim(j.job_id,j.version,j.fencing_token,'process-worker',j.dispatch.intent_id)
        ref=artifacts.publish_manifest(j,outputs(root/('attempt-'+str(j.fencing_token))),j.fencing_token)
        if action=='crash':
            payload=json.dumps({'job':j.model_dump(mode='json'),'ref':ref.model_dump(mode='json')})
            (root/'lost-attempt.json').write_text(payload)
            assert (root/'lost-attempt.json').read_text()==payload
            print(json.dumps({'fence':j.fencing_token}),flush=True)
            os._exit(23)
        j=store.finalize(j.job_id,j.version,j.fencing_token,'process-worker',JobState.COMPLETED,ref)
        print(json.dumps({'fence':j.fencing_token,'run_id':j.run_id,'ref':j.result.model_dump(mode='json')}),flush=True)
        return
    runtime=DurableRuntime(store,artifacts,verifier,True,clock=clock)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_api_app(runtime)),base_url='https://api.test',headers={'X-Goog-IAP-JWT-Assertion':token,'Idempotency-Key':'same-action'}) as c:
        if action in ('submit','conflict'): response=await c.post('/generate-async',json={'prompt':'different' if action=='conflict' else 'offline process recovery'})
        else: response=await c.get(job_id)
        print(json.dumps({'status':response.status_code,'body':response.text,'type':response.headers.get('content-type'),'sha256':hashlib.sha256(response.content).hexdigest(),'size':len(response.content)}),flush=True)
asyncio.run(main())
"""


def test_separate_api_worker_processes_survive_loss_and_read_same_committed_result(
    tmp_path,
):
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    assert host.startswith(("127.0.0.1:", "localhost:")), "local emulator required"
    pytest.importorskip("google.cloud.firestore")
    ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    key = ec.generate_private_key(ec.SECP256R1())
    (tmp_path / "private.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (tmp_path / "public.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    assert (tmp_path / "private.pem").read_bytes().startswith(b"-----BEGIN PRIVATE KEY")
    assert (tmp_path / "public.pem").read_bytes().startswith(b"-----BEGIN PUBLIC KEY")
    env = dict(
        os.environ,
        LNF_JOB_BACKEND="firestore",
        LNF_API_ACCESS_MODE="iap",
        LNF_PROBE_ROOT=str(tmp_path),
        LNF_PROBE_PROJECT=os.environ.get("LNF_PROBE_PROJECT")
        or "demo-lnf-" + uuid.uuid4().hex[:16],
    )
    assert env["LNF_PROBE_PROJECT"].startswith("demo-lnf-")

    def run(action, now, path, subject="owner", expected=0):
        receipt = subprocess.run(
            [sys.executable, "-c", PROBE, action, str(now), path, subject],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert receipt.returncode == expected, receipt.stdout + receipt.stderr
        return json.loads(receipt.stdout.strip().splitlines()[-1])

    submitted = run("submit", 1000, "")
    assert submitted["status"] == 200
    job = json.loads(submitted["body"])
    duplicate = run("submit", 1000, "")
    assert duplicate["status"] == 200
    assert json.loads(duplicate["body"])["job_id"] == job["job_id"]
    assert run("conflict", 1000, "")["status"] == 409
    assert (
        json.loads(run("get", 1000, f'/jobs/{job["job_id"]}')["body"])["status"]
        == "accepted"
    )
    old = run("crash", 1000, job["job_id"], expected=23)
    recovered = run("recover", 1240, job["job_id"])
    assert recovered["fence"] > old["fence"]
    assert run("stale", 1240, job["job_id"])["error"] in {
        "job_terminal",
        "job_conflict",
        "job_lease_lost",
    }
    status = run("get", 1240, f'/jobs/{job["job_id"]}')
    assert (
        status["status"] == 200 and json.loads(status["body"])["status"] == "completed"
    )
    result = run("get", 1240, f'/jobs/{job["job_id"]}/result')
    assert result["status"] == 200 and json.loads(result["body"])["success"]
    stream = run("get", 1240, f'/stream/{job["job_id"]}')
    assert stream["status"] == 200 and stream["body"].count("event: complete") == 1
    event_ids = [
        int(line.removeprefix("id: "))
        for line in stream["body"].splitlines()
        if line.startswith("id: ")
    ]
    assert event_ids == sorted(set(event_ids)) and len(event_ids) >= 5
    assert "event: progress" in stream["body"]
    assert f'/jobs/{job["job_id"]}/result' in stream["body"]
    download = run(
        "get", 1240, f'/artifacts?run_id={recovered["run_id"]}&artifact=notebook.ipynb'
    )
    assert download["status"] == 200 and json.loads(download["body"])["nbformat"] == 4
    manifest = json.loads(result["body"])["manifest"]
    entry = next(
        item
        for item in manifest["objects"]
        if item["object_name"].endswith("/notebook.ipynb")
    )
    assert download["size"] == entry["size_bytes"]
    assert download["sha256"] == entry["sha256"]
    # Compare the exact committed manifest bytes against the winning ArtifactRef.
    committed = run(
        "get", 1240, f'/artifacts?run_id={recovered["run_id"]}&artifact=manifest.json'
    )
    assert json.loads(committed["body"]) == manifest
    assert committed["sha256"] == recovered["ref"]["sha256"]
    assert committed["size"] == recovered["ref"]["size_bytes"]
    assert hashlib.sha256(download["body"].encode()).hexdigest() == download["sha256"]
    paths = [
        f'/jobs/{job["job_id"]}',
        f'/jobs/{job["job_id"]}/result',
        f'/stream/{job["job_id"]}',
        f'/artifacts?run_id={recovered["run_id"]}&artifact=notebook.ipynb',
    ]
    for path in paths:
        assert run("get", 1240, path, "other")["status"] == 404
        assert run("get", 1000 + 7 * 86400, path)["status"] == 404
