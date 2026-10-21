"""Reject unsafe worker configuration before constructing a durable runtime."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from langgraph_system_generator.api import worker_server

TASKS = "tasks-worker@offline-project.iam.gserviceaccount.com"
SCHEDULER = "scheduler@offline-project.iam.gserviceaccount.com"


@pytest.fixture
def configuration(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BASE_OUTPUT_DIR", raising=False)
    for name, value in {
        "LNF_JOB_TASK_QUEUE": "projects/offline-project/locations/us-central1/queues/jobs",
        "LNF_WORKER_URL": "https://worker.example.run.app",
        "LNF_WORKER_AUDIENCE": "https://worker.example.run.app",
        "LNF_TASK_SERVICE_ACCOUNT": TASKS,
        "LNF_SCHEDULER_SERVICE_ACCOUNT": SCHEDULER,
        "LNF_OUTPUT_BASE": "./allowed",
        "LNF_WORKER_OUTPUT_ROOT": "./allowed/workers",
        "LNF_JOB_ARTIFACT_BUCKET": "offline-artifacts",
    }.items():
        monkeypatch.setenv(name, value)
    select_store = Mock()
    monkeypatch.setattr(worker_server, "select_job_store", select_store)
    return tmp_path, select_store


@pytest.mark.parametrize(
    "root",
    ["./other/workers", "./allowed/../../escaped", "./allowed/../other/workers"],
)
def test_invalid_root_fails_before_store_or_attempt_construction(
    configuration, monkeypatch, root
):
    directory, select_store = configuration
    monkeypatch.setenv("LNF_WORKER_OUTPUT_ROOT", root)
    with TestClient(worker_server.create_worker_app()) as client:
        response = client.post(
            "/internal/execute", headers={"Authorization": "Bearer offline-token"}
        )
    assert response.status_code == 503
    assert response.json() == {"code": "worker_output_root_invalid"}
    select_store.assert_not_called()
    assert list(directory.iterdir()) == []


def test_invalid_output_base_fails_before_store_construction(
    configuration, monkeypatch
):
    _, select_store = configuration
    monkeypatch.setenv("LNF_OUTPUT_BASE", "../outside")
    with pytest.raises(worker_server.JobError) as error:
        worker_server.configured_runtime()
    assert error.value.code == "worker_output_root_invalid"
    select_store.assert_not_called()


@pytest.mark.parametrize("route", ["/internal/execute", "/internal/reconcile"])
def test_identical_service_accounts_fail_closed(configuration, monkeypatch, route):
    _, select_store = configuration
    monkeypatch.setenv("LNF_SCHEDULER_SERVICE_ACCOUNT", TASKS)
    with TestClient(worker_server.create_worker_app()) as client:
        response = client.post(route, headers={"Authorization": "Bearer offline-token"})
    assert response.status_code == 503
    assert response.json() == {"code": "worker_configuration_invalid"}
    select_store.assert_not_called()


def test_valid_runtime_uses_canonical_root_without_creating_directories(
    configuration, monkeypatch
):
    directory, select_store = configuration
    monkeypatch.setenv("LNF_WORKER_OUTPUT_ROOT", "./allowed/workers/../attempts")
    runtime = worker_server.configured_runtime()
    assert runtime.worker.root == directory / "allowed" / "attempts"
    assert runtime.task_accounts == frozenset({TASKS})
    assert runtime.scheduler_accounts == frozenset({SCHEDULER})
    select_store.assert_called_once_with()
    assert list(directory.iterdir()) == []
