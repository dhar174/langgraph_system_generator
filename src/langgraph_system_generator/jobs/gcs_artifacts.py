"""Immutable private attempt objects; Firestore's winning pointer publishes them."""

import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any, BinaryIO, cast

from .models import ArtifactRef, DurableJob, JobError
from .protocols import JobStore

TYPES = {
    "manifest.json": "application/json",
    "generated_cells.json": "application/json",
    "notebook_plan.json": "application/json",
    "notebook.ipynb": "application/x-ipynb+json",
    "notebook.html": "text/html",
    "notebook.md": "text/markdown",
    "notebook.pdf": "application/pdf",
    "notebook.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "notebook_bundle.zip": "application/zip",
}


class GCSArtifactStore:
    def __init__(
        self,
        bucket: str,
        root: Path,
        *,
        client: Any = None,
        max_file_bytes: int = 8 * 1024 * 1024,
        max_total_bytes: int = 64 * 1024 * 1024,
    ):
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,221}[a-z0-9]", bucket)
            or not 1 <= max_file_bytes <= 8 * 1024 * 1024
            or not max_file_bytes <= max_total_bytes <= 64 * 1024 * 1024
        ):
            raise JobError("artifact_configuration_invalid", 503)
        self.bucket, self.root, self._client = bucket, root.absolute(), client
        self.max_file_bytes, self.max_total_bytes = max_file_bytes, max_total_bytes

    def _connect(self) -> Any:
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client

    def _bytes(self, path: Path) -> bytes:
        absolute = path.absolute()
        try:
            parts = absolute.relative_to(self.root).parts
            current = self.root
            for part in parts:
                current = current / part
                if current.is_symlink():
                    raise ValueError("symlink")
            if (
                any(
                    p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
                    for p in (self.root, *self.root.parents)
                )
                or not absolute.is_file()
                or absolute.name not in TYPES
            ):
                raise ValueError("invalid artifact")
            absolute.resolve(strict=True).relative_to(self.root.resolve(strict=True))
            with absolute.open("rb") as source:
                data = source.read(self.max_file_bytes + 1)
            if len(data) > self.max_file_bytes:
                raise ValueError("artifact too large")
            return data
        except (OSError, ValueError):
            raise JobError("artifact_file_invalid", 422) from None

    def _upload(self, name: str, data: bytes, content_type: str) -> dict[str, Any]:
        blob = self._connect().bucket(self.bucket).blob(name)
        blob.upload_from_string(
            data,
            content_type=content_type,
            if_generation_match=0,
            checksum="crc32c",
            retry=None,
            timeout=1,
        )
        generation = int(blob.generation)
        blob.reload(if_generation_match=generation, retry=None, timeout=1)
        # Verify immutable bytes, not caller-controlled metadata. SDK CRC32C also
        # verifies transport; the external receipt binds finalized SHA256 bytes.
        received = blob.download_as_bytes(
            if_generation_match=generation, retry=None, timeout=1
        )
        digest = hashlib.sha256(data).hexdigest()
        if (
            blob.size != len(data)
            or blob.content_type != content_type
            or hashlib.sha256(received).hexdigest() != digest
        ):
            raise JobError("artifact_checksum_mismatch", 503)
        return {
            "object_name": name,
            "generation": str(generation),
            "sha256": digest,
            "size_bytes": len(data),
            "content_type": content_type,
        }

    def publish_manifest(
        self, job: DurableJob, files: tuple[Path, ...], fence: int
    ) -> ArtifactRef:
        if (
            fence != job.fencing_token
            or job.lease is None
            or job.cancellation_requested
        ):
            raise JobError("job_lease_lost")
        try:
            if not 2 <= len(files) <= len(TYPES) or len({p.parent for p in files}) != 1:
                raise JobError("artifact_set_invalid", 422)
            content = {p.name: self._bytes(p) for p in files}
            if (
                len(content) != len(files)
                or "manifest.json" not in content
                or "notebook.ipynb" not in content
            ):
                raise JobError("artifact_manifest_incomplete", 422)
            if sum(map(len, content.values())) > self.max_total_bytes:
                raise JobError("artifact_set_too_large", 422)
            manifest = json.loads(content.pop("manifest.json"))
            required = {
                "cell_count",
                "cell_count_source",
                "generated_cell_spec_count",
                "mode",
                "architecture_type",
                "qa_summary",
                "qa_reports",
                "graph_exports",
                "tool_contract_summary",
                "artifact_contract",
            }
            if (
                not isinstance(manifest, dict)
                or not required.issubset(manifest)
                or any(
                    not isinstance(manifest[key], dict)
                    for key in (
                        "qa_summary",
                        "graph_exports",
                        "tool_contract_summary",
                        "artifact_contract",
                    )
                )
                or not isinstance(manifest["qa_reports"], list)
                or manifest["cell_count_source"] != "serialized_notebook"
            ):
                raise JobError("artifact_manifest_incomplete", 422)
            import nbformat

            notebook = nbformat.reads(
                content["notebook.ipynb"].decode("utf-8"),
                as_version=nbformat.NO_CONVERT,
            )
            nbformat.validate(notebook)
            if notebook.nbformat != 4 or manifest.get("cell_count") != len(
                notebook.cells
            ):
                raise JobError("artifact_notebook_mismatch", 422)
            if "generation_outcome" in manifest:
                from langgraph_system_generator.qa.outcomes import (
                    GenerationOutcome,
                    derive_generation_outcome,
                    notebook_candidate_id,
                )

                outcome = GenerationOutcome.model_validate(
                    manifest["generation_outcome"]
                )
                expected = derive_generation_outcome(
                    manifest["qa_reports"],
                    candidate_sha256=notebook_candidate_id(notebook),
                    pipeline=outcome.pipeline,
                    has_cells=bool(notebook.cells),
                    artifacts_present=True,
                    artifacts_available=True,
                    repair_attempts=outcome.repair.attempts,
                    max_repair_attempts=outcome.repair.limit,
                    rollback_used=outcome.repair.rollback_used,
                )
                if outcome != expected:
                    raise JobError("artifact_outcome_mismatch", 422)
            entries = manifest.get("artifact_contract", {}).get("standalone_files", [])
            if not isinstance(entries, list) or {
                Path(entry.get("path", "")).name
                for entry in entries
                if entry.get("exists")
            } != set(content):
                raise JobError("artifact_manifest_incomplete", 422)
            for entry in entries:
                if (
                    entry.get("exists")
                    and Path(entry.get("path", "")).name not in content
                ):
                    raise JobError("artifact_manifest_incomplete", 422)
            prefix = f"runs/{job.run_id}/attempt-{fence}/"
            refs = {
                name: {"job_id": job.job_id, "run_id": job.run_id, "artifact": name}
                for name in content
            }

            def stable(value: Any, key: str = "") -> Any:
                if isinstance(value, dict):
                    return {
                        k: stable(v, k)
                        for k, v in value.items()
                        if k != "api_download_path"
                    }
                if isinstance(value, list):
                    return [stable(v) for v in value]
                if key == "output_dir":
                    return {"job_id": job.job_id, "run_id": job.run_id}
                if key == "path_type":
                    return "durable_reference"
                if key == "path_semantics":
                    return "Private artifacts selected through authorized job/run/artifact references."
                if isinstance(value, str) and (key == "path" or key.endswith("_path")):
                    return refs.get(Path(value).name)
                return value

            manifest = stable(manifest)
            downloads = {
                name: f"/artifacts?run_id={job.run_id}&artifact={name}"
                for name in (*content, "manifest.json")
            }
            contract = manifest["artifact_contract"]
            contract.update(
                storage_type="gcs_private",
                access_scope="verified_owner",
                run_id=job.run_id,
                expires_at=job.expires_at,
                api_downloads=downloads,
            )
            # Refresh standalone sizes against serialized bytes, preserving graph,
            # tooling, QA and other generator metadata rather than rebuilding it.
            for entry in manifest.get("artifact_contract", {}).get(
                "standalone_files", []
            ):
                ref = entry.get("path")
                if isinstance(ref, dict):
                    entry["size_bytes"] = len(content[ref["artifact"]])
                    entry["api_download_path"] = downloads[ref["artifact"]]
            manifest_entry = {
                "name": "manifest",
                "manifest_key": "manifest_path",
                "format": "json",
                "path_type": "durable_reference",
                "path": {
                    "job_id": job.job_id,
                    "run_id": job.run_id,
                    "artifact": "manifest.json",
                },
                "exists": True,
                "size_bytes": 0,
                "api_download_path": downloads["manifest.json"],
            }
            contract["standalone_files"].append(manifest_entry)
            if "notebook_bundle.zip" in content:
                import io

                with zipfile.ZipFile(
                    io.BytesIO(content["notebook_bundle.zip"])
                ) as bundle:
                    members = bundle.infolist()
                    if (
                        len(members) > 32
                        or sum(m.file_size for m in members) > self.max_total_bytes
                    ):
                        raise JobError("artifact_bundle_invalid", 422)
                    if len({m.filename for m in members}) != len(members) or any(
                        m.filename not in TYPES or m.filename == "manifest.json"
                        for m in members
                    ):
                        raise JobError("artifact_bundle_invalid", 422)
                    declared = {
                        m["name"]: m
                        for m in manifest.get("artifact_contract", {}).get(
                            "zip_members", []
                        )
                    }
                    if set(declared) != {m.filename for m in members}:
                        raise JobError("artifact_bundle_manifest_incomplete", 422)
                    actual_members = []
                    for member in members:
                        member_bytes = bundle.read(member)
                        if member.filename in content:
                            if member.filename == "notebook.ipynb":
                                # Windows standalone text uses CRLF while ZIP
                                # StringIO uses LF; preserve both actual hashes.
                                matches = (
                                    nbformat.reads(
                                        member_bytes.decode(), nbformat.NO_CONVERT
                                    )
                                    == notebook
                                )
                            else:
                                matches = member_bytes == content[member.filename]
                            if not matches:
                                raise JobError("artifact_bundle_mismatch", 422)
                        actual_members.append(
                            {
                                **declared.get(member.filename, {}),
                                "name": member.filename,
                                "size_bytes": member.file_size,
                                "sha256": hashlib.sha256(member_bytes).hexdigest(),
                                "availability": (
                                    "standalone_and_bundle"
                                    if member.filename in content
                                    else "bundle_only"
                                ),
                            }
                        )
                    manifest["artifact_contract"]["zip_members"] = actual_members
            objects = [
                self._upload(prefix + name, data, TYPES[name])
                for name, data in sorted(content.items())
            ]
            manifest.update(
                schema_version=1,
                job_id=job.job_id,
                run_id=job.run_id,
                fencing_token=fence,
                objects=objects,
            )
            for _ in range(8):
                data = json.dumps(
                    manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
                if manifest_entry["size_bytes"] == len(data):
                    break
                manifest_entry["size_bytes"] = len(data)
            else:
                raise JobError("artifact_manifest_invalid", 422)
            if (
                len(data) > min(self.max_file_bytes, 1024 * 1024)
                or sum(map(len, content.values())) + len(data) > self.max_total_bytes
            ):
                raise JobError("artifact_set_too_large", 422)
            receipt = self._upload(
                prefix + "manifest.json", data, TYPES["manifest.json"]
            )
            receipt.pop("content_type")
            return ArtifactRef(bucket=self.bucket, **receipt)
        except JobError:
            raise
        except (ValueError, KeyError, TypeError, zipfile.BadZipFile):
            raise JobError("artifact_manifest_invalid", 422) from None
        except Exception:  # noqa: BLE001 - sanitize SDK failures
            raise JobError("artifact_storage_unavailable", 503) from None

    def read_manifest(self, ref: ArtifactRef) -> bytes:
        if ref.size_bytes > 1024 * 1024:
            raise JobError("artifact_reference_invalid", 404)
        with self.open_verified(ref) as source:
            return source.read()

    def open_verified(self, ref: ArtifactRef) -> BinaryIO:
        """Stage one bounded exact-generation object before sending HTTP headers.

        Disk spooling bounds memory and verifies corruption/missing data before a
        successful download response. The caller closes the returned file.
        """
        if ref.bucket != self.bucket or ref.size_bytes > self.max_file_bytes:
            raise JobError("artifact_reference_invalid", 404)
        # Ownership transfers to the HTTP stream after verification.
        target = tempfile.TemporaryFile()  # noqa: SIM115
        try:
            digest = hashlib.sha256()
            size = 0

            class Sink:
                def write(self, data: bytes) -> int:
                    nonlocal size
                    size += len(data)
                    if size > ref.size_bytes:
                        raise ValueError("object too large")
                    digest.update(data)
                    return target.write(data)

            blob = (
                self._connect()
                .bucket(self.bucket)
                .blob(ref.object_name, generation=int(ref.generation))
            )
            blob.download_to_file(
                Sink(),
                if_generation_match=int(ref.generation),
                checksum="crc32c",
                retry=None,
                timeout=10,
            )
            if size != ref.size_bytes or digest.hexdigest() != ref.sha256:
                raise ValueError("checksum")
            target.seek(0)
            return cast(BinaryIO, target)
        except Exception:  # noqa: BLE001 - sanitize SDK failures
            target.close()
            raise JobError("artifact_storage_unavailable", 503) from None

    def committed_manifest(self, job: DurableJob) -> dict[str, Any]:
        if job.result is None:
            raise JobError("job_result_not_ready", 409)
        prefix = f"runs/{job.run_id}/attempt-{job.fencing_token}/"
        if job.result.object_name != prefix + "manifest.json":
            raise JobError("artifact_reference_invalid", 503)
        try:
            manifest = json.loads(self.read_manifest(job.result))
            if (
                manifest["job_id"] != job.job_id
                or manifest["run_id"] != job.run_id
                or manifest["fencing_token"] != job.fencing_token
            ):
                raise ValueError("wrong committed manifest")
            objects = manifest["objects"]
            if not isinstance(objects, list) or not 1 <= len(objects) < len(TYPES):
                raise ValueError("invalid object set")
            names = set()
            for entry in objects:
                name = entry["object_name"].removeprefix(prefix)
                if (
                    name not in TYPES
                    or name == "manifest.json"
                    or name in names
                    or entry["content_type"] != TYPES[name]
                ):
                    raise ValueError("invalid object")
                names.add(name)
                ref = ArtifactRef(
                    bucket=self.bucket,
                    **{
                        key: entry[key]
                        for key in ("object_name", "generation", "sha256", "size_bytes")
                    },
                )
                if ref.size_bytes > self.max_file_bytes:
                    raise ValueError("oversized object")
            return manifest
        except JobError:
            raise
        except Exception:  # noqa: BLE001 - sanitize malformed private receipts
            raise JobError("artifact_manifest_invalid", 503) from None

    def committed_ref(
        self, job: DurableJob, manifest: dict[str, Any], name: str
    ) -> ArtifactRef:
        if name == "manifest.json" and job.result:
            return job.result
        prefix = f"runs/{job.run_id}/attempt-{job.fencing_token}/"
        for entry in manifest["objects"]:
            if entry["object_name"] == prefix + name and name in TYPES:
                return ArtifactRef(
                    bucket=self.bucket,
                    **{
                        key: entry[key]
                        for key in ("object_name", "generation", "sha256", "size_bytes")
                    },
                )
        raise JobError("artifact_unavailable", 404)

    def cleanup_run(self, job: DurableJob, *, now: float, limit: int = 32) -> bool:
        """Trusted scheduler inventory only, preserve all unexpired winning objects.

        No current attempt can retain authority a day after the overall deadline.
        A partial page leaves the parent inventory for the next bounded sweep.
        """
        if (
            not 1 <= limit <= 100
            or now < job.deadline_at + 86400
            or (job.lease is not None)
        ):
            raise JobError("artifact_cleanup_requires_retention", 409)
        prefix = f"runs/{job.run_id}/"
        winner = (
            f"runs/{job.run_id}/attempt-{job.fencing_token}/"
            if job.result and now < job.expires_at
            else None
        )
        try:
            blobs = list(
                self._connect().list_blobs(
                    self.bucket, prefix=prefix, max_results=limit, retry=None, timeout=1
                )
            )
            for blob in blobs:
                if (
                    not re.fullmatch(
                        re.escape(prefix)
                        + r"attempt-[0-9]{1,3}/("
                        + "|".join(re.escape(name) for name in TYPES)
                        + r")",
                        blob.name,
                    )
                    or not blob.generation
                ):
                    raise JobError("artifact_cleanup_ownership_invalid", 409)
                if winner is None or not blob.name.startswith(winner):
                    blob.delete(
                        if_generation_match=int(blob.generation), retry=None, timeout=1
                    )
            return len(blobs) < limit
        except JobError:
            raise
        except Exception:  # noqa: BLE001 - sanitize SDK failures
            raise JobError("artifact_cleanup_unavailable", 503) from None

    def delete(self, ref: ArtifactRef) -> None:
        # B3's retention inventory must prove non-winning ownership before using
        # the generation-matched primitive. Unconditional deletion is unsafe.
        raise JobError("artifact_cleanup_requires_retention", 409)

    def cleanup_orphan(
        self, store: JobStore, job_id: str, fence: int, *, now: float
    ) -> int:
        """Delete one known, irrevocably fenced attempt after its retention floor.

        A trusted operator supplies a known job/fence, never a client bucket/path.
        B3 still owns global inventory and cleanup after job metadata expiry.
        """
        job = store.inspect_attempt(job_id)
        prefix = f"runs/{job.run_id}/attempt-{fence}/"
        if (
            type(fence) is not int
            or not 1 <= fence <= job.fencing_token
            or now < job.deadline_at + 86400
            or (job.lease is not None and job.lease.fencing_token == fence)
            or (job.result is not None and job.result.object_name.startswith(prefix))
            or (
                fence == job.fencing_token
                and job.state.value not in {"failed", "cancelled", "expired"}
            )
        ):
            raise JobError("artifact_cleanup_requires_retention", 409)
        try:
            objects = list(
                self._connect().list_blobs(
                    self.bucket, prefix=prefix, max_results=10, retry=None, timeout=1
                )
            )
            if len(objects) > len(TYPES) or any(
                not b.name.startswith(prefix)
                or b.name.removeprefix(prefix) not in TYPES
                or not b.generation
                for b in objects
            ):
                raise JobError("artifact_cleanup_ownership_invalid", 409)
            for blob in objects:
                blob.delete(
                    if_generation_match=int(blob.generation), retry=None, timeout=1
                )
            return len(objects)
        except JobError:
            raise
        except Exception:  # noqa: BLE001 - sanitize SDK failures
            raise JobError("artifact_cleanup_unavailable", 503) from None
