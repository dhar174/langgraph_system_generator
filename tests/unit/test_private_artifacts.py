"""Private object publication is incomplete until the fenced pointer commits."""

import hashlib
import json
from types import SimpleNamespace

import nbformat
import pytest

from langgraph_system_generator.jobs.gcs_artifacts import GCSArtifactStore
from langgraph_system_generator.jobs.models import JobError, JobState
from tests.unit.test_durable_job_contracts import running
from tests.unit.test_durable_job_contracts import store as _store
from tests.unit.test_firestore_job_store import firestore_transport  # noqa: F401

store = _store


class Blob:
    def __init__(self, name, objects, generation=None):
        self.name, self.objects = name, objects
        self.generation = generation
        self.metadata = None

    def upload_from_string(
        self, data, *, content_type, if_generation_match, checksum, retry, timeout
    ):
        assert if_generation_match == 0 and checksum == "crc32c"
        assert retry is None and timeout <= 10
        if self.name in self.objects:
            raise OSError("precondition failed: immutable object collision")
        self.objects[self.name] = (bytes(data), content_type)
        self.generation = 1

    def reload(self, *, if_generation_match, retry, timeout):
        assert str(if_generation_match) == "1" and retry is None
        data, self.content_type = self.objects[self.name]
        self.size = len(data)

    def download_as_bytes(self, *, if_generation_match, retry, timeout):
        assert str(if_generation_match) == "1" and retry is None
        return self.objects[self.name][0]

    def download_to_file(
        self, target, *, if_generation_match, checksum, retry, timeout
    ):
        assert checksum == "crc32c"
        target.write(
            self.download_as_bytes(
                if_generation_match=if_generation_match, retry=retry, timeout=timeout
            )
        )

    def delete(self, *, if_generation_match, retry, timeout):
        assert str(if_generation_match) == "1" and retry is None
        del self.objects[self.name]


class Storage:
    def __init__(self):
        self.objects = {}

    def bucket(self, name):
        assert name == "private-offline-bucket"
        return SimpleNamespace(
            blob=lambda name, generation=None: Blob(name, self.objects, generation)
        )

    def list_blobs(self, bucket, *, prefix, max_results, retry, timeout):
        assert 1 <= max_results <= 100 and retry is None
        return [
            Blob(name, self.objects, 1)
            for name in sorted(self.objects)
            if name.startswith(prefix)
        ][:max_results]


def outputs(root):
    root.mkdir()
    notebook = root / "notebook.ipynb"
    nbformat.write(
        nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("x = 1")]), notebook
    )
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cell_count": 1,
                "cell_count_source": "serialized_notebook",
                "notebook_path": str(notebook),
                "output_dir": str(root),
                "qa_summary": {"scope": "generated-artifact"},
                "qa_reports": [],
                "mode": "stub",
                "architecture_type": "router",
                "generated_cell_spec_count": 1,
                "tool_contract_summary": {},
                "graph_exports": {"schema": {"compiled_graph_variable": "graph"}},
                "artifact_contract": {
                    "standalone_files": [{"path": str(notebook), "exists": True}],
                    "zip_members": [],
                },
            }
        ),
        encoding="utf-8",
    )
    return notebook, manifest


def test_verified_objects_then_one_fenced_completion(store, tmp_path):
    backend, _ = store
    job = running(backend)
    files = outputs(tmp_path / "attempt")
    client = Storage()
    objects = GCSArtifactStore("private-offline-bucket", tmp_path, client=client)
    ref = objects.publish_manifest(job, files, job.fencing_token)
    assert backend.inspect_attempt(job.job_id).state == JobState.RUNNING
    manifest = json.loads(objects.read_manifest(ref))
    assert str(tmp_path) not in json.dumps(manifest)
    assert manifest["cell_count"] == 1
    assert manifest["qa_summary"] == {"scope": "generated-artifact"}
    assert manifest["graph_exports"]["schema"]["compiled_graph_variable"] == "graph"
    assert "sha256" not in manifest  # final manifest receipt is external
    for entry in manifest["objects"]:
        data = client.objects[entry["object_name"]][0]
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["size_bytes"] == len(data)
        assert entry["generation"] == "1"
        assert entry["content_type"]
    backend.finalize(
        job.job_id, job.version, job.fencing_token, "worker-a", JobState.COMPLETED, ref
    )
    assert backend.inspect_attempt(job.job_id).result == ref


def test_local_execution_claim_cannot_enter_durable_publication(store, tmp_path):
    backend, _ = store
    job = running(backend)
    files = outputs(tmp_path / "attempt")
    manifest = json.loads(files[1].read_text())
    manifest["generation_outcome"] = {
        "schema_version": 2,
        "generated_execution": {"result": "passed"},
    }
    files[1].write_text(json.dumps(manifest), encoding="utf-8")
    client = Storage()
    with pytest.raises(JobError, match="execution_qualification_not_supported"):
        GCSArtifactStore(
            "private-offline-bucket", tmp_path, client=client
        ).publish_manifest(job, files, job.fencing_token)
    assert not client.objects
    assert backend.inspect_attempt(job.job_id).state == JobState.RUNNING


@pytest.mark.parametrize(
    "fault",
    [
        "partial",
        "checksum",
        "collision",
        "missing_manifest",
        "missing_notebook",
        "cell_count",
    ],
)
def test_partial_corrupt_or_incomplete_artifacts_never_complete(
    store, tmp_path, monkeypatch, fault
):
    backend, _ = store
    job = running(backend)
    files = outputs(tmp_path / "attempt")
    client = Storage()
    if fault == "partial":
        original = Blob.upload_from_string

        def upload(self, *args, **kwargs):
            if self.name.endswith("manifest.json"):
                raise OSError("storage unavailable")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Blob, "upload_from_string", upload)
    elif fault == "checksum":
        monkeypatch.setattr(Blob, "download_as_bytes", lambda *a, **kw: b"corrupt")
    elif fault == "collision":
        client.objects[
            f"runs/{job.run_id}/attempt-{job.fencing_token}/notebook.ipynb"
        ] = (b"collision", "x")
    elif fault == "missing_manifest":
        files = files[:1]
    elif fault == "missing_notebook":
        files = files[1:]
    else:
        data = json.loads(files[1].read_text())
        data["cell_count"] = 10
        files[1].write_text(json.dumps(data))
    with pytest.raises(JobError):
        GCSArtifactStore(
            "private-offline-bucket", tmp_path, client=client
        ).publish_manifest(job, files, job.fencing_token)
    assert backend.inspect_attempt(job.job_id).result is None


def test_old_upload_cannot_win_after_replacement_or_cancellation(store, tmp_path):
    backend, clock = store
    old = running(backend)
    objects = GCSArtifactStore("private-offline-bucket", tmp_path, client=Storage())
    old_ref = objects.publish_manifest(
        old, outputs(tmp_path / "old"), old.fencing_token
    )
    clock.now = old.lease.expires_at
    backend.reconcile()
    fresh = backend.inspect_attempt(old.job_id)
    replacement = backend.claim(
        fresh.job_id,
        fresh.version,
        fresh.fencing_token,
        "new",
        fresh.dispatch.intent_id,
    )
    new_ref = objects.publish_manifest(
        replacement, outputs(tmp_path / "new"), replacement.fencing_token
    )
    backend.finalize(
        replacement.job_id,
        replacement.version,
        replacement.fencing_token,
        "new",
        JobState.COMPLETED,
        new_ref,
    )
    with pytest.raises(JobError):
        backend.finalize(
            old.job_id,
            old.version,
            old.fencing_token,
            "worker-a",
            JobState.COMPLETED,
            old_ref,
        )
    assert backend.inspect_attempt(old.job_id).result == new_ref
    with pytest.raises(JobError, match="artifact_cleanup_requires_retention"):
        objects.delete(new_ref)


async def test_real_generator_stub_outputs_publish_without_local_paths(
    store, tmp_path, monkeypatch
):
    import langgraph_system_generator.jobs.gcs_artifacts as gcs
    from langgraph_system_generator.jobs.attempt_process import generate

    backend, _ = store
    job = running(backend)
    directory = tmp_path / "real-output"
    directory.mkdir()
    monkeypatch.setenv("LNF_WORKER_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("LNF_JOB_ARTIFACT_BUCKET", "private-offline-bucket")
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("LNF_JOB_PROVIDER_BINDINGS", raising=False)
    client = Storage()
    real_class = gcs.GCSArtifactStore
    monkeypatch.setattr(
        gcs,
        "GCSArtifactStore",
        lambda bucket, root: real_class(bucket, root, client=client),
    )
    events = []
    await generate(
        {"job": job.model_dump(mode="json"), "directory": str(directory)}, events.append
    )
    receipt = events[-1]["ref"]
    data = client.objects[receipt["object_name"]][0]
    manifest = json.loads(data)
    assert str(tmp_path) not in data.decode()
    assert (
        manifest["cell_count"] > 0
        and manifest["cell_count_source"] == "serialized_notebook"
    )
    assert manifest["qa_summary"] and manifest["tool_contract_summary"]
    assert manifest["artifact_contract"]["zip_members"]


def test_nbformat_three_is_rejected_without_silent_conversion(store, tmp_path):
    backend, _ = store
    job = running(backend)
    files = outputs(tmp_path / "attempt")
    notebook = nbformat.v3.new_notebook(
        worksheets=[nbformat.v3.new_worksheet(cells=[nbformat.v3.new_code_cell("x=1")])]
    )
    nbformat.write(notebook, files[0], version=3)
    with pytest.raises(JobError):
        GCSArtifactStore(
            "private-offline-bucket", tmp_path, client=Storage()
        ).publish_manifest(job, files, job.fencing_token)


async def test_outcome_candidate_mismatch_is_rejected_before_any_upload(
    store, tmp_path, monkeypatch
):
    from pathlib import Path

    from langgraph_system_generator.cli import generate_artifacts

    backend, _ = store
    job = running(backend)
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    artifacts = await generate_artifacts(
        "Create a router", output_dir=tmp_path / "candidate", formats=["ipynb"]
    )
    manifest_path = Path(artifacts["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["generation_outcome"]["candidate"]["sha256"] = "b" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    client = Storage()
    files = tuple(manifest_path.parent.iterdir())
    with pytest.raises(JobError, match="artifact_outcome_mismatch"):
        GCSArtifactStore(
            "private-offline-bucket", tmp_path, client=client
        ).publish_manifest(job, files, job.fencing_token)
    assert client.objects == {}


@pytest.mark.parametrize(
    "field",
    [
        "artifact_contract",
        "qa_summary",
        "qa_reports",
        "graph_exports",
        "tool_contract_summary",
    ],
)
def test_missing_required_generator_manifest_contract_rejected(store, tmp_path, field):
    backend, _ = store
    job = running(backend)
    files = outputs(tmp_path / "attempt")
    data = json.loads(files[1].read_text())
    del data[field]
    files[1].write_text(json.dumps(data))
    with pytest.raises(JobError):
        GCSArtifactStore(
            "private-offline-bucket", tmp_path, client=Storage()
        ).publish_manifest(job, files, job.fencing_token)


def test_orphan_cleanup_checks_retention_ownership_and_exact_generations(
    store, tmp_path
):
    backend, clock = store
    old = running(backend)
    client = Storage()
    objects = GCSArtifactStore("private-offline-bucket", tmp_path, client=client)
    old_ref = objects.publish_manifest(
        old, outputs(tmp_path / "old"), old.fencing_token
    )
    with pytest.raises(JobError):
        objects.cleanup_orphan(backend, old.job_id, old.fencing_token, now=clock.now)
    clock.now = old.lease.expires_at
    backend.reconcile()
    current = backend.inspect_attempt(old.job_id)
    replacement = backend.claim(
        current.job_id,
        current.version,
        current.fencing_token,
        "new",
        current.dispatch.intent_id,
    )
    new_ref = objects.publish_manifest(
        replacement, outputs(tmp_path / "new"), replacement.fencing_token
    )
    backend.finalize(
        replacement.job_id,
        replacement.version,
        replacement.fencing_token,
        "new",
        JobState.COMPLETED,
        new_ref,
    )
    clock.now = old.deadline_at + 86400
    assert (
        objects.cleanup_orphan(backend, old.job_id, old.fencing_token, now=clock.now)
        == 2
    )
    assert old_ref.object_name not in client.objects
    assert new_ref.object_name in client.objects
    with pytest.raises(JobError):
        objects.cleanup_orphan(
            backend, old.job_id, replacement.fencing_token, now=clock.now
        )


def test_malformed_zip_is_permanent_validation_failure(store, tmp_path):
    backend, _ = store
    job = running(backend)
    files = outputs(tmp_path / "attempt")
    bundle = files[0].parent / "notebook_bundle.zip"
    bundle.write_bytes(b"not a zip")
    manifest = json.loads(files[1].read_text())
    manifest["artifact_contract"]["standalone_files"].append(
        {"path": str(bundle), "exists": True}
    )
    files[1].write_text(json.dumps(manifest))
    with pytest.raises(JobError) as error:
        GCSArtifactStore(
            "private-offline-bucket", tmp_path, client=Storage()
        ).publish_manifest(job, (*files, bundle), job.fencing_token)
    assert error.value.status == 422


def test_per_file_limit_stays_within_single_multipart_upload_budget(tmp_path):
    with pytest.raises(JobError):
        GCSArtifactStore(
            "private-offline-bucket", tmp_path, max_file_bytes=8 * 1024 * 1024 + 1
        )
