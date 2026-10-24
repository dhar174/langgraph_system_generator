"""Real durable attempt/export/publication with a fake semantic reviewer."""

import json

import pytest

from langgraph_system_generator import cli
from langgraph_system_generator.generator import nodes
from langgraph_system_generator.generator.state import QAReport
from langgraph_system_generator.jobs import gcs_artifacts as gcs
from langgraph_system_generator.jobs.attempt_process import generate as real_attempt
from langgraph_system_generator.jobs.models import ArtifactRef, JobState
from langgraph_system_generator.jobs.worker import ManagedWorker
from langgraph_system_generator.qa.outcomes import candidate_id
from langgraph_system_generator.qa.specialist_models import SemanticReviewPolicy
from tests.unit import test_durable_api as durable_fixtures
from tests.unit.test_managed_worker import payload, service
from tests.unit.test_semantic_review_pipeline import install_reviewer

BODY = durable_fixtures.BODY
harness = durable_fixtures.harness
store = durable_fixtures.store
identity = durable_fixtures.identity
firestore_transport = durable_fixtures.firestore_transport


@pytest.mark.parametrize("unavailable", [False, True])
async def test_review_advice_or_unavailable_commits_once_without_retry(
    harness, monkeypatch, tmp_path, unavailable
):
    backend, _, storage, _, client, _, _, forbidden = harness
    calls, _ = install_reviewer(monkeypatch, unavailable=unavailable)
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("LNF_WORKER_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LNF_JOB_ARTIFACT_BUCKET", "private-offline-bucket")
    monkeypatch.setattr(cli.settings, "lnf_specialist_qa_mode", "advisory")
    seed = cli._build_stub_result(BODY["prompt"])
    seed["user_prompt"] = BODY["prompt"]
    seed["generation_mode"] = "live"
    seed["semantic_review_policy"] = SemanticReviewPolicy(mode="advisory")
    seed["qa_reports"] = [
        QAReport(
            check_name="Static fixture",
            rule_id="fixture_static",
            passed=True,
            stage="static",
            message="OK",
            evidence={"candidate_id": candidate_id(seed["generated_cells"])},
        )
    ]

    class Graph:
        async def ainvoke(self, *args, **kwargs):
            seed.update(await nodes.semantic_review_node(seed))
            seed.update(await nodes.package_outputs_node(seed))
            return seed

    monkeypatch.setattr(cli, "_load_generator_graph", lambda: lambda: Graph())
    real_store = gcs.GCSArtifactStore
    monkeypatch.setattr(
        gcs,
        "GCSArtifactStore",
        lambda bucket, root: real_store(bucket, root, client=storage),
    )

    errors = []

    class Runner:
        attempts = 0

        async def run(self, job, directory, progress):
            self.attempts += 1
            events = []
            try:
                await real_attempt(
                    {"job": job.model_dump(mode="json"), "directory": str(directory)},
                    events.append,
                )
            except Exception as error:
                errors.append(
                    (type(error).__name__, getattr(error, "code", None), str(error))
                )
                raise
            return ArtifactRef.model_validate(events[-1]["ref"])

    async with client() as api:
        accepted = await api.post(
            "/generate-async",
            json={**BODY, "mode": "live", "formats": ["ipynb", "html", "zip"]},
        )
        assert accepted.status_code == 200
        job = backend.inspect_attempt(accepted.json()["job_id"])
        assert "semantic" not in job.request.model_dump_json()
        runner = Runner()
        worker = ManagedWorker(backend, runner, tmp_path)
        assert (await worker.execute(service(backend), payload(job)))[0] == 200, errors
        committed = backend.inspect_attempt(job.job_id)
        assert committed.state == JobState.COMPLETED and committed.attempt_count == 1
        assert runner.attempts == len(calls) == 1
        response = await api.get(f"/jobs/{job.job_id}/result")
        assert response.status_code == 200
        manifest = response.json()["manifest"]
        feedback = manifest["qa_summary"]["semantic_review"]
        assert feedback["status"] == ("unavailable" if unavailable else "reviewed")
        assert manifest["generation_outcome"]["status"] == (
            "completed" if unavailable else "advisories"
        )
        assert (
            manifest["generation_outcome"]["generated_execution"]["result"] == "not_run"
        )
        assert manifest["generation_outcome"] == response.json()["generation_outcome"]
        notebook = next(
            data[0]
            for name, data in storage.objects.items()
            if name.endswith("/notebook.ipynb")
        )
        assert "Semantic review (advisory only)" in json.dumps(json.loads(notebook))
        before = dict(storage.objects)
        assert (await worker.execute(service(backend), payload(job)))[0] == 200
        assert runner.attempts == len(calls) == 1 and storage.objects == before
        assert backend.inspect_attempt(job.job_id) == committed
    forbidden.assert_not_awaited()
