"""Provider policy is current both before execution and before publication."""

import json
from unittest.mock import AsyncMock

import pytest

from langgraph_system_generator.jobs.attempt_process import generate
from langgraph_system_generator.jobs.models import JobError
from tests.unit.test_durable_job_contracts import running
from tests.unit.test_durable_job_contracts import store as _store
from tests.unit.test_firestore_job_store import firestore_transport  # noqa: F401

store = _store


@pytest.mark.parametrize("failure", ["changed_registration", "removed_reference"])
async def test_provider_policy_changes_never_upload(
    store, tmp_path, monkeypatch, failure
):
    import langgraph_system_generator.jobs.gcs_artifacts as gcs
    from langgraph_system_generator import cli

    backend, _ = store
    job = running(backend)
    monkeypatch.setenv("LNF_WORKER_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LNF_JOB_ARTIFACT_BUCKET", "private-offline-bucket")
    monkeypatch.setenv("LNF_JOB_PROVIDER_REFS", '["openai-v1"]')
    monkeypatch.setenv("LNF_JOB_PROVIDER_BINDINGS", '{"openai-v1":"provider"}')
    registry = {
        "provider": {
            "base_url": "https://provider.example/v1",
            "api_key_env": "LNF_LLM_PROVIDER_API_KEY",
        }
    }
    monkeypatch.setenv("LNF_TRUSTED_LLM_ENDPOINTS", json.dumps(registry))

    async def generated(*args, **kwargs):
        assert kwargs["endpoint_policy"] == "hosted"
        assert kwargs["custom_endpoint"] == "https://provider.example/v1"
        if failure == "changed_registration":
            registry["provider"]["base_url"] = "https://changed.example/v1"
            monkeypatch.setenv("LNF_TRUSTED_LLM_ENDPOINTS", json.dumps(registry))
        if failure == "removed_reference":
            monkeypatch.setenv("LNF_JOB_PROVIDER_REFS", "[]")
        return {
            "manifest": {
                "qa_summary": (
                    {"status": "blocking_failed", "artifacts_usable": False}
                    if failure == "blocking_qa"
                    else {}
                )
            }
        }

    monkeypatch.setattr(cli, "generate_artifacts", AsyncMock(side_effect=generated))
    monkeypatch.setattr(
        gcs.GCSArtifactStore,
        "publish_manifest",
        lambda *args: pytest.fail("unsafe publication"),
    )
    with pytest.raises(JobError):
        await generate(
            {
                "job": job.model_dump(mode="json"),
                "directory": str(tmp_path / "attempt"),
            },
            lambda event: None,
        )
