"""Real google-auth signature verification and actual HTTP header forwarding."""

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from langgraph_system_generator.api.worker_server import (
    WorkerRuntime,
    create_worker_app,
)
from langgraph_system_generator.jobs.internal_identity import GoogleOIDCVerifier
from langgraph_system_generator.jobs.memory_store import InMemoryJobStore
from langgraph_system_generator.jobs.models import JobError

AUD = "https://worker.example.run.app"
TASKS = "tasks-worker@offline-project.iam.gserviceaccount.com"
SCHEDULER = "scheduler@offline-project.iam.gserviceaccount.com"


@pytest.fixture
def signed():
    pytest.importorskip("google.oauth2.id_token")
    jwt = pytest.importorskip("jwt")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    calls = []

    def request(url, method="GET", **kwargs):
        assert url == "https://www.googleapis.com/oauth2/v1/certs"
        calls.append(url)
        return SimpleNamespace(
            status=200, data=json.dumps({"offline-key": public}).encode()
        )

    def token(**claims):
        now = int(time.time())
        return jwt.encode(
            {
                "iss": "https://accounts.google.com",
                "sub": "123456789",
                "aud": AUD,
                "email": TASKS,
                "email_verified": True,
                "iat": now,
                "exp": now + 300,
            }
            | claims,
            key,
            algorithm="RS256",
            headers={"kid": "offline-key"},
        )

    return token, GoogleOIDCVerifier(AUD, request=request), calls


def test_real_google_verification_rejects_fake_identity_and_stripped_signature(signed):
    token, verifier, _ = signed
    assert verifier.verify("Bearer " + token()).service_account == TASKS
    for bad in [
        token(aud="wrong"),
        token(iss="https://cloud.google.com/iap"),
        token(exp=int(time.time()) - 300),
        token(email_verified=False),
        token().rsplit(".", 1)[0] + ".SIGNATURE_REMOVED_BY_GOOGLE",
        "bad",
    ]:
        with pytest.raises(JobError):
            verifier.verify("Bearer " + bad)


def test_http_forwards_authorization_and_enforces_route_specific_accounts(signed):
    token, verifier, _ = signed
    worker = SimpleNamespace(
        execute=AsyncMock(return_value=(200, {"state": "completed"}))
    )
    runtime = WorkerRuntime(
        InMemoryJobStore(b"x" * 32),
        worker,
        AsyncMock(return_value={"dispatched": 0}),
        verifier,
        AUD,
        frozenset({TASKS}),
        frozenset({SCHEDULER}),
    )
    with TestClient(create_worker_app(runtime)) as client:
        body = {"schema_version": 1, "job_id": "a" * 32, "dispatch_generation": 1}
        assert (
            client.post(
                "/internal/execute",
                json=body,
                headers={"Authorization": "Bearer " + token()},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/internal/execute",
                json=body,
                headers={
                    "X-CloudTasks-TaskName": "fake",
                    "X-Goog-IAP-JWT-Assertion": token(),
                },
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/internal/execute",
                json=body,
                headers={
                    "Authorization": "Bearer "
                    + token(email="fake@offline-project.iam.gserviceaccount.com")
                },
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/internal/reconcile", headers={"Authorization": "Bearer " + token()}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/internal/reconcile",
                headers={"Authorization": "Bearer " + token(email=SCHEDULER)},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/internal/execute",
                json=body | {"owner": "attacker"},
                headers={"Authorization": "Bearer " + token()},
            ).status_code
            == 422
        )
        assert client.get("/health").json() == {
            "status": "ok",
            "public_durable_admission": False,
        }
    assert worker.execute.await_count == 1
