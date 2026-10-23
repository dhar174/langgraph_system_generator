"""Child-side nbclient execution of actual exported trusted fixture notebooks."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path
from typing import Any

import nbformat
from nbclient import NotebookClient

from langgraph_system_generator.qa.execution_models import (
    AssertionResult,
    EvidenceCaptureLimitError,
    ExecutionCase,
    ExecutionResult,
)
from langgraph_system_generator.qa.outcomes import candidate_id, notebook_candidate_id
from langgraph_system_generator.utils.credential_redaction import (
    _sanitize_text_credentials,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def persist(result: ExecutionResult, path: Path) -> None:
    """Atomic partial receipts survive cell errors and parent timeouts."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    # Windows readers/AV may briefly hold the previous receipt without delete
    # sharing. Retain atomic publication and bound retries under the outer TTL.
    for attempt in range(8):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(min(0.02 * 2**attempt, 0.25))


def mutate(notebook: Any, mutation: str) -> None:
    """Change only a copy, and fail if the expected mutation site is absent."""
    for cell in notebook.cells:
        source = cell.source
        if (
            mutation == "runtime-failure"
            and cell.metadata.get("section") == "graph"
            and cell.cell_type == "code"
        ):
            cell.source += (
                '\nraise RuntimeError("mutation: graph construction failure")'
            )
            return
        if mutation == "wrong-route" and '"route": decision.route' in source:
            cell.source = source.replace(
                '"route": decision.route', '"route": "technical"', 1
            )
            return
        if (
            mutation == "unreachable-tool"
            and "tools_node = ToolNode(TOOLS, handle_tool_errors=True)" in source
        ):
            cell.source = source.replace(
                "tools_node = ToolNode(TOOLS, handle_tool_errors=True)",
                'def tools_node(state):\n    return {"messages": []}',
                1,
            )
            return
        if mutation == "nontermination" and "def router_node(" in source:
            # A genuine generated graph node blocks in graph.stream, bounded by
            # the probe cell's timeout and the outer process-tree deadline.
            position = source.index("\n", source.index("def router_node("))
            cell.source = (
                source[:position]
                + "\n    while True:\n        pass"
                + source[position:]
            )
            return
    raise ValueError(f"Mutation site not found: {mutation}")


class BoundedClient(NotebookClient):
    """Bound IOPub content before nbclient retains it."""

    captured_bytes = 0
    capture_limit = 65536

    def process_message(self, msg: Any, cell: Any, cell_index: int) -> Any:
        self.captured_bytes += len(
            json.dumps(msg.get("content", {}), default=str).encode("utf-8")
        )
        if self.captured_bytes > self.capture_limit:
            raise EvidenceCaptureLimitError("Kernel output capture budget exceeded")
        return super().process_message(msg, cell, cell_index)


def execute(
    case: ExecutionCase,
    result: ExecutionResult,
    directory: Path,
    receipt: Path,
    work: Path,
) -> None:
    """Generate/verify once, then execute original cell sources in a child kernel."""
    from jupyter_client.kernelspec import KernelSpecManager

    from langgraph_system_generator.qa.execution_fixtures import generate_fixture

    original = directory / "generated" / "notebook.ipynb"
    manifest_path = directory / "generated" / "manifest.json"
    if result.mutation is None:
        artifacts = asyncio.run(generate_fixture(case, original.parent))
        manifest = artifacts["manifest"]
        original = Path(manifest["notebook_path"])
        # Keep the exact returned manifest independent from implementation filenames.
        manifest_path = directory / "fixture-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    else:
        manifest_path = directory / "fixture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    notebook = nbformat.read(original, as_version=nbformat.NO_CONVERT)
    if notebook.nbformat != 4:
        raise ValueError("Exported artifact must already be nbformat v4")
    nbformat.validate(notebook)
    result.notebook_path = str(original)
    result.notebook_sha256 = sha256(original)
    result.serialized_cell_count = len(notebook.cells)
    original_id = notebook_candidate_id(notebook)
    result.original_candidate_sha256 = original_id
    cells = json.loads(Path(manifest["cells_path"]).read_text(encoding="utf-8"))
    if (
        original_id != candidate_id(cells)
        or original_id != manifest["generation_outcome"]["candidate"]["sha256"]
    ):
        raise ValueError(
            "Exported notebook / serialized cells / manifest candidate mismatch"
        )
    if len(notebook.cells) != manifest["cell_count"]:
        raise ValueError("Serialized cell count mismatch")
    if manifest["generation_outcome"]["generated_execution"]["result"] != "not_run":
        raise ValueError("Production outcome contract changed unexpectedly")
    if result.mutation:
        mutate(notebook, result.mutation)
        mutant = directory / f"{result.mutation}.ipynb"
        nbformat.write(notebook, mutant)
        result.mutated_notebook_path = str(mutant)
        result.mutation_applied = notebook_candidate_id(notebook) != original_id
    result.candidate_sha256 = notebook_candidate_id(notebook)
    spec = manifest["graph_exports"]["schema"]
    result.assertions.append(AssertionResult(name="artifact_identity", passed=True))
    result.environment = {
        "source_manifest_sha256": sha256(manifest_path),
        "source_cells_sha256": sha256(Path(manifest["cells_path"])),
        "case_specification": case.model_dump(mode="json"),
        "generation_outcome": manifest["generation_outcome"],
        "tool_contract_summary": manifest.get("tool_contract_summary", {}),
        "python": sys.version,
        "executable": sys.executable,
        "kernel": "private current-interpreter ipykernel",
        "dependencies": {},
    }
    # Retain source identity even when dependency preflight is unavailable.
    result.environment["dependencies"] = {
        name: importlib.metadata.version(name) for name in case.dependencies
    }
    kernel_root = work / "kernels"
    kernel = kernel_root / "lnf-eval"
    kernel.mkdir(parents=True)
    (kernel / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [
                    sys.executable,
                    "-m",
                    "ipykernel_launcher",
                    "-f",
                    "{connection_file}",
                ],
                "display_name": "LNF trusted evaluation",
                "language": "python",
            }
        ),
        encoding="utf-8",
    )
    observed = work / "observations.json"
    bootstrap = nbformat.v4.new_code_cell(
        "from langgraph_system_generator.qa.execution_fixtures import install_runtime_fixtures\n"
        "install_runtime_fixtures()\n"
        "import socket\n"
        "assert socket.socket.connect.__module__ == 'sitecustomize'\n"
        "assert socket.socket.sendto.__module__ == 'sitecustomize'\n"
        "try:\n"
        "    socket.getaddrinfo('external.invalid', 443)\n"
        "except OSError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('External DNS guard is inactive')\n"
    )
    derived_cells = [bootstrap]
    indices: dict[int, int] = {}
    for index, cell in enumerate(notebook.cells, 1):
        if cell.cell_type == "code" and cell.metadata.get("section") == "setup":
            result.excluded_cells[str(index)] = (
                "Dependency installation excluded; dependencies preflighted in child"
            )
            continue
        indices[len(derived_cells)] = index
        derived_cells.append(cell)
    derived_cells.append(
        nbformat.v4.new_code_cell(
            "from langgraph_system_generator.qa.execution_probe import write_probe\n"
            f"write_probe(globals(), {case.model_dump(mode='json')!r}, {str(observed)!r})"
        )
    )
    derived = nbformat.v4.new_notebook(cells=derived_cells)
    derived_path = directory / f"{result.mutation or 'clean'}-execution.ipynb"
    nbformat.write(derived, derived_path)
    result.derived_notebook_path = str(derived_path)
    result.derived_sha256 = sha256(derived_path)
    result.mocked = [
        "generation ChatOpenAI responses",
        "docs retrieval",
        "runtime ChatOpenAI constructor",
        "synthetic fixture credential",
        "environment smoke omitted",
    ]
    if case.tool_fixture != "none":
        result.mocked.append(
            f"tool behavior fixture: {case.tool_fixture}; generated function executes normally"
        )

    def starting(cell: Any, cell_index: int, **kwargs: Any) -> None:
        if cell.cell_type == "code":
            result.environment["active_cell"] = {
                "derived_index": cell_index + 1,
                "original_index": indices.get(cell_index),
                "section": cell.metadata.get("section"),
                "role": (
                    "original"
                    if cell_index in indices
                    else "bootstrap" if cell_index == 0 else "behavioral_probe"
                ),
            }
            result.environment.setdefault("derived_attempted_cells", []).append(
                cell_index + 1
            )
            if cell_index in indices:
                result.attempted_cells.append(indices[cell_index])
            persist(result, receipt)

    def completed(cell: Any, cell_index: int, **kwargs: Any) -> None:
        if cell.cell_type == "code" and not any(
            output.get("output_type") == "error" for output in cell.outputs
        ):
            result.environment.setdefault("derived_completed_cells", []).append(
                cell_index + 1
            )
            if cell_index in indices:
                result.completed_cells.append(indices[cell_index])
            persist(result, receipt)

    client = BoundedClient(
        derived,
        timeout=case.cell_timeout,
        shutdown_kernel="immediate",
        record_timing=False,
        kernel_name="lnf-eval",
        resources={"metadata": {"path": str(work)}},
        on_cell_start=starting,
        on_cell_executed=completed,
    )
    client.capture_limit = case.capture_bytes
    result.environment["nbclient_timeout_seconds"] = client.timeout
    # A private spec prevents a host kernelspec from switching interpreter/env.
    client.create_kernel_manager()
    assert client.km is not None
    client.km.kernel_spec_manager = KernelSpecManager(kernel_dirs=[str(kernel_root)])
    persist(result, receipt)
    try:
        client.execute()
    except Exception:
        # Preserve observed graph-start evidence on a real invocation timeout;
        # absence of this evidence must never become a behavioral failure claim.
        if observed.is_file():
            partial = json.loads(observed.read_text(encoding="utf-8"))
            result.observations = partial.get("observations", [])
            result.executed = partial.get("executed", [])
        raise
    finally:
        executed_path = directory / f"{result.mutation or 'clean'}-executed.ipynb"
        nbformat.write(derived, executed_path)
        result.environment["executed_notebook_path"] = str(executed_path)
    evidence = json.loads(observed.read_text(encoding="utf-8"))
    result.assertions.extend(
        AssertionResult.model_validate(item) for item in evidence["assertions"]
    )
    result.assertions.append(
        AssertionResult(
            name="manifest_graph_consistency", passed=evidence["canonical_spec"] == spec
        )
    )
    result.assertions.append(
        AssertionResult(
            name="original_artifact_unchanged",
            passed=sha256(original) == result.notebook_sha256,
        )
    )
    result.assertions.append(
        AssertionResult(
            name="executed_source_identity_preserved",
            passed=notebook_candidate_id(notebook) == result.candidate_sha256,
        )
    )
    result.observations = evidence["observations"]
    result.executed = evidence["executed"]
    # Parent alone can mark passed, after process-tree cleanup succeeds.
    result.status = (
        "incomplete" if all(item.passed for item in result.assertions) else "failed"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    case = ExecutionCase.model_validate(request["case"])
    result = ExecutionResult.model_validate(request["result"])
    receipt = Path(request["receipt"])
    started = time.monotonic()
    try:
        if sys.platform != "win32":
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (case.memory_mb * 1024**2,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (case.cpu_seconds,) * 2)
        execute(
            case, result, Path(request["directory"]), receipt, Path(request["work"])
        )
    except Exception as exc:  # noqa: BLE001 -- serialize failures at the child boundary
        result.status = "failed"
        result.timed_out = type(exc).__name__ in {"CellTimeoutError", "TimeoutError"}
        result.resource_limit_hit = (
            isinstance(exc, MemoryError) or getattr(exc, "ename", None) == "MemoryError"
        )
        if result.resource_limit_hit:
            result.resource_limit_outcome = "hit"
        elif type(exc).__name__ in {"DeadKernelError", "KernelDiedError"}:
            result.resource_limit_outcome = "unknown"
        result.errors.append(
            {
                "phase": (
                    "notebook_execution"
                    if result.attempted_cells
                    else "generation_or_setup"
                ),
                "cell": result.environment.get("active_cell", {}).get("original_index"),
                "derived_cell": result.environment.get("active_cell"),
                "kernel_error_type": getattr(exc, "ename", None),
                "timeout_seconds": case.cell_timeout if result.timed_out else None,
                "type": type(exc).__name__,
                "message": _sanitize_text_credentials(str(exc))[:2000],
            }
        )
    result.runtime_seconds = round(time.monotonic() - started, 3)
    persist(result, receipt)
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
