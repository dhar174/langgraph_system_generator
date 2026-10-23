"""Admission policy for the explicit trusted-fixture runner, never JSON imports.

The Python caller is trusted. This is not cryptographic attestation or a hostile
code sandbox. No API/request/state deserializer constructs admitted evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph_system_generator.generator.outcome_models import (
    EvaluatedExecutionOutcome,
)
from langgraph_system_generator.qa.execution_models import (
    ExecutionCase,
    ExecutionResult,
)

EVALUATOR_VERSION = "trusted-fixture-qualification-v1"
DATASET_SHA256 = "600eaf4fed1f76128e4db8feaecbcad7340b6b8c5a56c256763590d5523e2805"
_ADMISSION = object()
_SUPERVISION = object()
LIMITATIONS = [
    "Trusted fixtures only; native networking is not contained",
    "Child retains the current user's filesystem privileges",
    "Only declared fixture behaviors were checked; requirements remain unverified",
    "Presentation derivatives share the executed code candidate, not its byte hash",
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def required_assertions(case: ExecutionCase) -> set[str]:
    """Independent coverage inventory; probe emissions do not define this set."""
    names = {
        "artifact_identity",
        "compiled_canonical_graph",
        "interactive_loop_disabled",
        "real_in_memory_checkpointer",
        "canonical_graph_spec_present",
        "compiled_nodes_match_spec",
        "manifest_graph_consistency",
        "original_artifact_unchanged",
        "executed_source_identity_preserved",
    }
    for invocation in case.invocations:
        checks = {"bounded_steps", "actual_tool_executions", "tool_callbacks"}
        checks.update(
            {"declared_failure_policy", "no_false_terminal_on_failure"}
            if invocation.expected_error
            else {"no_runtime_error", "executed_nodes", "terminal"}
        )
        checks.update("state:" + key for key in invocation.expected_state)
        if invocation.retained_text:
            checks.add("retained_thread_context")
        if invocation.absent_text:
            checks.add("thread_isolation")
        if invocation.expected_tool_calls:
            checks.update({"tool_arguments", "tool_request", "tool_result"})
        if case.fixture == "supervisor-v1" and not invocation.expected_error:
            checks.update(
                {
                    "reducer_combines_workers",
                    "aggregation_observes_results",
                    "delegated_instructions",
                    "same_superstep_fanout",
                }
            )
        names.update(invocation.id + ":" + name for name in checks)
    return names


@dataclass(frozen=True)
class QualifiedExecution:
    summary: EvaluatedExecutionOutcome
    receipt: dict[str, Any]
    _authority: object


def admitted(value: Any) -> bool:
    return isinstance(value, QualifiedExecution) and value._authority is _ADMISSION


def _mark_supervised(result: ExecutionResult, provenance: dict[str, Any]) -> None:
    """Private parent-runner capability; never represented in receipt JSON."""
    result._supervision = (_SUPERVISION, dict(provenance))


def _failure(result: ExecutionResult) -> tuple[str, str]:
    """Attribute only observed defects; setup/partial evidence is not a defect."""
    if any(
        error.get("phase") in {"generation_or_setup", "isolation_setup_or_cleanup"}
        or error.get("kernel_error_type", error.get("type"))
        in {"ModuleNotFoundError", "ImportError", "NoSuchKernel"}
        for error in result.errors
    ):
        return "unavailable", "environment"
    if not result.cleanup_verified or result.resource_limit_outcome == "unknown":
        return "incomplete", "partial_execution"
    graph_timeout = result.timed_out and any(
        error.get("type") == "CellTimeoutError"
        and (
            error.get("derived_cell", {}).get("role") == "behavioral_probe"
            or error.get("derived_cell", {}).get("section") == "execution"
        )
        for error in result.errors
    )
    graph_started = any(
        item.get("nodes") or item.get("phase") == "graph_invocation_started"
        for item in result.observations
    )
    code_error = any(
        error.get("phase") == "notebook_execution"
        and error.get("kernel_error_type")
        in {
            "RuntimeError",
            "ValueError",
            "TypeError",
            "NameError",
            "SyntaxError",
            "AssertionError",
            "KeyError",
            "AttributeError",
        }
        for error in result.errors
    )
    if graph_started and (
        graph_timeout
        or code_error
        or any(not item.passed for item in result.assertions)
    ):
        return "failed", "generated_behavior"
    return "incomplete", "partial_execution"


def qualify_execution(
    case: ExecutionCase,
    result: ExecutionResult,
    *,
    notebook: Any | None,
    manifest: dict[str, Any],
    source_bytes: bytes | None,
    provenance: dict[str, Any],
    dataset_sha256: str,
    controls_verified: bool,
    raw_receipt_sha256: str,
    receipt_reference: str = "evaluation-receipt.json",
) -> QualifiedExecution:
    """Called with typed completed results by the supervised local runner only.

    The parent supplies its own before/after source snapshot and supervised result;
    matching fields in arbitrary JSON are never a supported admission mechanism.
    """
    from langgraph_system_generator.qa.outcomes import notebook_candidate_id

    expected = required_assertions(case)
    names = [item.name for item in result.assertions]
    integrity: list[str] = []
    if (
        not result._supervision
        or result._supervision[0] is not _SUPERVISION
        or result._supervision[1] != provenance
    ):
        integrity.append("untrusted_result")
    if dataset_sha256 != DATASET_SHA256:
        integrity.append("unsupported_dataset")
    if (
        result.case_id != case.id
        or result.case_version != 1
        or result.fixture != case.fixture
    ):
        integrity.append("case_identity")
    if result.mutation is not None or result.mutation_applied:
        integrity.append("mutated_candidate")
    if (
        provenance.get("source_dirty")
        or any(
            getattr(result, key) != provenance.get(key)
            for key in (
                "generator_revision",
                "source_dirty",
                "source_diff_sha256",
                "source_tree_sha256",
                "source_files_sha256",
            )
        )
        or not result.source_files_sha256
    ):
        integrity.append("source_provenance")
    identity = notebook_candidate_id(notebook) if notebook is not None else None
    if notebook is not None and (
        identity != result.candidate_sha256
        or identity != result.original_candidate_sha256
        or identity
        != manifest.get("generation_outcome", {}).get("candidate", {}).get("sha256")
        or source_bytes is None
        or digest(source_bytes) != result.notebook_sha256
    ):
        integrity.append("artifact_identity")
    if len(names) != len(set(names)) or set(names) - expected:
        integrity.append("assertion_identity")
    if result.status == "passed":
        if set(names) != expected:
            integrity.append("missing_assertions")
        if not controls_verified:
            integrity.append("negative_controls_unverified")
        if [item.get("invocation") for item in result.observations] != [
            invocation.id for invocation in case.invocations
        ]:
            integrity.append("invocation_coverage")
        if notebook is None:
            integrity.append("missing_artifact")
        else:
            excluded = {
                str(index)
                for index, cell in enumerate(notebook.cells, 1)
                if cell.cell_type == "code" and cell.metadata.get("section") == "setup"
            }
            code = [
                index
                for index, cell in enumerate(notebook.cells, 1)
                if cell.cell_type == "code" and str(index) not in excluded
            ]
            if (
                set(result.excluded_cells) != excluded
                or result.attempted_cells != code
                or result.completed_cells != code
                or result.serialized_cell_count != len(notebook.cells)
                or result.environment.get("derived_attempted_cells")
                != result.environment.get("derived_completed_cells")
                or not result.environment.get("derived_completed_cells")
            ):
                integrity.append("partial_cells")
        if (
            not result.cleanup_verified
            or not result.isolation.get("enforced_limits")
            or not result.isolation.get("network")
            or not result.isolation.get("credentials")
            or set(result.environment.get("dependencies", {})) != set(case.dependencies)
            or result.environment.get("case_specification")
            != case.model_dump(mode="json")
        ):
            integrity.append("execution_conditions")
        if (
            not result.derived_notebook_path
            or not result.derived_sha256
            or (
                not Path(result.derived_notebook_path).is_file()
                or digest(Path(result.derived_notebook_path).read_bytes())
                != result.derived_sha256
            )
        ):
            integrity.append("derived_artifact")
        elif notebook is not None:
            import nbformat

            derived = nbformat.read(result.derived_notebook_path, as_version=4)

            def sources(cells):
                return [
                    (cell.cell_type, cell.source, dict(cell.metadata)) for cell in cells
                ]

            expected_cells = [
                cell
                for cell in notebook.cells
                if not (
                    cell.cell_type == "code" and cell.metadata.get("section") == "setup"
                )
            ]
            if sources(derived.cells[1:-1]) != sources(expected_cells):
                integrity.append("substituted_execution_source")
    status, classification = (
        ("incomplete", "evidence_integrity")
        if integrity
        else ("passed", "none") if result.status == "passed" else _failure(result)
    )
    # Only approved assertion identifiers enter public metadata, never details.
    assertions = [
        {"name": item.name, "passed": item.passed}
        for item in result.assertions
        if item.name in expected
    ]
    env = {
        key: str(result.environment[key])
        for key in ("python", "kernel")
        if key in result.environment
    }
    isolation = [
        str(result.isolation[key])
        for key in ("level", "process_tree", "network", "credentials")
        if key in result.isolation
    ]
    mocked = [
        "deterministic generation and runtime model responses",
        "offline docs retrieval",
    ]
    if case.tool_fixture != "none":
        mocked.append("calculator fixture; real generated ToolNode dispatch")
    receipt = {
        "schema_version": 1,
        "evaluator_version": EVALUATOR_VERSION,
        "dataset_sha256": dataset_sha256,
        "case_id": case.id,
        "case_version": 1,
        "case_config_sha256": digest(case.model_dump_json().encode()),
        "result": status,
        "failure_classification": classification,
        "candidate_algorithm": "notebook-cells-v1",
        "candidate_sha256": identity,
        "source_notebook_sha256": result.notebook_sha256,
        "executed_notebook_sha256": (
            result.notebook_sha256 if result.attempted_cells else None
        ),
        "generator_revision": result.generator_revision,
        "evaluator_source_sha256": result.source_tree_sha256,
        "raw_receipt_sha256": raw_receipt_sha256,
        "source_qa_sha256": digest(
            json.dumps(manifest.get("qa_reports", []), sort_keys=True).encode()
        ),
        "source_pipeline": manifest.get("generation_outcome", {}).get(
            "pipeline", "unknown"
        ),
        "source_manifest_sha256": result.environment.get("source_manifest_sha256"),
        "source_cells_sha256": result.environment.get("source_cells_sha256"),
        "derived_notebook_sha256": result.derived_sha256,
        "environment": env,
        "dependencies": result.environment.get("dependencies", {}),
        "isolation": isolation,
        "limits": result.isolation.get("enforced_limits", {}),
        "resource_bounds": {
            key: result.isolation[key]
            for key in (
                "cell_timeout_seconds",
                "total_timeout_seconds",
                "memory_mb",
                "cpu_seconds",
                "capture_bytes",
            )
            if key in result.isolation
        },
        "mocked": mocked,
        "executed": result.executed,
        "untested": case.untested,
        "assertions": assertions,
        "assertions_required": len(expected),
        "observed_invocations": [
            {
                "id": item.get("invocation"),
                "nodes": item.get("nodes", []),
                "phase": item.get("phase", "completed"),
            }
            for item in result.observations
        ],
        "integrity_findings": integrity,
        "attempted_cells": result.attempted_cells,
        "completed_cells": result.completed_cells,
        "excluded_cells": result.excluded_cells,
        "cleanup_verified": result.cleanup_verified,
        "negative_controls_verified": controls_verified,
        "limitations": LIMITATIONS,
    }
    receipt_bytes = json.dumps(receipt, sort_keys=True, indent=2).encode("utf-8")
    summary = EvaluatedExecutionOutcome(
        result=status,
        failure_classification=classification,
        candidate_sha256=identity,
        executed_notebook_sha256=(
            result.notebook_sha256 if result.attempted_cells else None
        ),
        generator_revision=result.generator_revision,
        evaluator_version=EVALUATOR_VERSION,
        dataset_sha256=dataset_sha256,
        case_id=case.id,
        case_version=1,
        environment=env,
        dependencies=receipt["dependencies"],
        isolation=isolation,
        mocked=mocked,
        executed=result.executed,
        untested=case.untested,
        assertions_passed=sum(item["passed"] for item in assertions),
        assertions_required=len(expected),
        failed_assertions=[item["name"] for item in assertions if not item["passed"]],
        receipt_reference=receipt_reference,
        receipt_sha256=digest(receipt_bytes),
        limitations=[*LIMITATIONS, *integrity],
    )
    return QualifiedExecution(summary, receipt, _ADMISSION)
