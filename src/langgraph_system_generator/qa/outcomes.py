"""One deterministic qualification derivation; never execute generated code."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Literal

from pydantic import TypeAdapter, ValidationError

from langgraph_system_generator.generator.outcome_models import (
    ArtifactOutcome,
    CandidateEvidence,
    EnvironmentSmokeOutcome,
    GenerationOutcome,
    GenerationOutcomeV2,
    RepairEvidence,
    SupportedGenerationOutcome,
)

if TYPE_CHECKING:
    from langgraph_system_generator.qa.execution_qualification import QualifiedExecution

SUMMARY_SECTIONS = frozenset({"qa_repair_summary", "generation_outcome"})


def _is_summary(
    cell_type: str, metadata: Mapping[str, Any], section: Any = None
) -> bool:
    """Only derived Markdown is excluded; never discard executable cells."""
    markers = (section, metadata.get("section"), metadata.get("kind"))
    return cell_type == "markdown" and any(
        isinstance(marker, str) and marker in SUMMARY_SECTIONS for marker in markers
    )


def report_payload(report: Any) -> dict[str, Any]:
    """Normalize typed and serialized reports without inventing evidence."""
    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    return dict(report) if isinstance(report, Mapping) else {}


def classify_report(report: Any) -> str | None:
    payload = report_payload(report)
    if payload.get("passed") is not False:
        return None
    severity = str(payload.get("severity") or "info").lower()
    return {"error": "blocking", "warning": "non_blocking"}.get(
        severity, "informational"
    )


def notebook_candidate_id(notebook: Mapping[str, Any]) -> str:
    """Hash exact ordered candidate cells, excluding only derived QA prose."""
    cells = []
    for cell in notebook.get("cells", []):
        metadata = dict(cell.get("metadata") or {})
        if _is_summary(cell["cell_type"], metadata):
            continue
        source = cell.get("source", "")
        cells.append(
            {
                "cell_type": cell["cell_type"],
                "source": "".join(source) if isinstance(source, list) else source,
                "metadata": metadata,
            }
        )
    payload = json.dumps(
        cells,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(b"notebook-cells-v1\0" + payload).hexdigest()


def candidate_id(cells: Iterable[Any]) -> str | None:
    """Compose exactly as validation/export do, with lazy optional imports."""
    from langgraph_system_generator.generator.state import CellSpec
    from langgraph_system_generator.notebook.composer import NotebookComposer

    specs = [cell if isinstance(cell, CellSpec) else CellSpec(**cell) for cell in cells]
    if not specs:
        return None
    return notebook_candidate_id(NotebookComposer().build_notebook(specs))


def derive_generation_outcome(
    reports: Iterable[Any] = (),
    *,
    candidate_sha256: str | None = None,
    pipeline: Literal["completed", "failed", "unknown"] = "unknown",
    has_cells: bool | None = None,
    artifacts_present: bool | None = None,
    artifacts_available: bool | None = None,
    repair_attempts: int = 0,
    max_repair_attempts: int = 0,
    rollback_used: bool = False,
    legacy_limited: bool = False,
    execution_evaluation: QualifiedExecution | None = None,
) -> SupportedGenerationOutcome:
    """Derive from current reports and explicit facts, never QA history.

    Unbound failures remain conservative blockers; unbound passes prove nothing.
    Explicitly stale reports belong to another candidate and are excluded.
    No report, including a caller-supplied execution claim, awards execution here.
    """
    selected = []
    matched = []
    missing = stale = 0
    for item in reports:
        report = report_payload(item)
        evidence = report.get("evidence") or {}
        identity = evidence.get("candidate_id") if isinstance(evidence, dict) else None
        if candidate_sha256 and identity and identity != candidate_sha256:
            stale += 1
            continue
        if not identity or not candidate_sha256:
            missing += 1
        else:
            matched.append(report)
        selected.append(report)

    blocking = sum(classify_report(r) == "blocking" for r in selected)
    advisory = sum(
        classify_report(r) in {"non_blocking", "informational"} for r in selected
    )
    static_reports = [r for r in matched if r.get("stage") == "static"]
    static_failed = any(
        r.get("stage") == "static" and classify_report(r) == "blocking"
        for r in selected
    )
    static_qa: Literal["passed", "failed", "not_run"] = (
        "failed" if static_failed else ("passed" if static_reports else "not_run")
    )
    smoke: Literal["passed", "failed", "unavailable", "not_run"] = "not_run"
    for report in matched:
        if report.get("rule_id") != "runtime_smoke_test":
            continue
        evidence = report.get("evidence") or {}
        execution = evidence.get("execution") or {}
        if evidence.get("failure_kind") == "runtime_unavailable":
            smoke = "unavailable"
        elif execution.get("execution_scope") == "trusted_smoke_test":
            smoke = "passed" if report.get("passed") is True else "failed"
    for report in selected:
        evidence = report.get("evidence") or {}
        if (
            classify_report(report) == "blocking"
            and evidence.get("failure_kind") == "runtime_unavailable"
            and evidence.get("generation_mode") == "live"
        ):
            pipeline = "failed"
    if has_cells is False:
        pipeline = "failed"
        if artifacts_present is None:
            artifacts_present = False
    unknown = not static_reports or bool(missing or stale) or legacy_limited
    usability: Literal["blocked", "no_known_blockers", "unknown"] = (
        "blocked"
        if pipeline == "failed" or blocking
        else ("unknown" if unknown else "no_known_blockers")
    )
    status: Literal["completed", "advisories", "blocked", "unverified", "failed"] = (
        "failed"
        if pipeline == "failed"
        else (
            "blocked"
            if blocking
            else (
                "unverified"
                if unknown or pipeline == "unknown"
                else ("advisories" if advisory else "completed")
            )
        )
    )
    outcome = GenerationOutcome(
        status=status,
        pipeline=pipeline,
        artifacts=ArtifactOutcome(
            presence=(
                "present"
                if artifacts_present is True
                else ("missing" if artifacts_present is False else "unknown")
            ),
            availability=(
                "unknown"
                if artifacts_available is None
                else ("available" if artifacts_available else "not_available")
            ),
        ),
        static_qa=static_qa,
        environment_smoke=EnvironmentSmokeOutcome(result=smoke),
        usability=usability,
        blocking_count=blocking,
        advisory_count=advisory,
        checks=sorted(
            {
                f"{r.get('stage') or 'unknown'}:{r.get('rule_id') or 'qa_report'}"
                for r in matched
            }
        ),
        candidate=CandidateEvidence(
            sha256=candidate_sha256,
            matched_reports=len(matched),
            missing_reports=missing,
            stale_reports=stale,
            legacy_limited=legacy_limited,
        ),
        repair=RepairEvidence(
            attempts=repair_attempts,
            limit=max_repair_attempts,
            budget_exhausted=repair_attempts >= max_repair_attempts,
            rollback_used=rollback_used,
        ),
    )
    if execution_evaluation is None:
        return outcome
    from langgraph_system_generator.qa.execution_qualification import admitted

    if not admitted(execution_evaluation):
        raise ValueError("Execution evidence must come from the trusted evaluator")
    execution = execution_evaluation.summary
    if not candidate_sha256 or execution.candidate_sha256 != candidate_sha256:
        execution = execution.model_copy(
            update={
                "result": "incomplete",
                "failure_classification": "evidence_integrity",
                "limitations": [
                    *execution.limitations,
                    "Selected candidate differs from evaluated candidate",
                ],
            }
        )
    values = outcome.model_dump(exclude={"schema_version", "generated_execution"})
    if execution.result == "failed":
        values.update(blocking_count=blocking + 1, usability="blocked")
        if outcome.pipeline != "failed":
            values["status"] = "blocked"
    elif execution.result != "passed" and outcome.usability != "blocked":
        values.update(usability="unknown", status="unverified")
    values["checks"] = sorted(
        {*outcome.checks, f"execution:{execution.case_id}:v{execution.case_version}"}
    )
    return GenerationOutcomeV2(**values, generated_execution=execution)


def read_generation_outcome(
    manifest: Mapping[str, Any],
    *,
    execution_evaluation: QualifiedExecution | None = None,
) -> SupportedGenerationOutcome:
    """Read additive outcomes; old/unknown versions get limited qualification."""
    try:
        parsed: SupportedGenerationOutcome = TypeAdapter(
            SupportedGenerationOutcome
        ).validate_python(manifest.get("generation_outcome"))
        if parsed.schema_version == 1:
            return parsed
        from langgraph_system_generator.qa.execution_qualification import (
            admitted,
            digest,
        )

        if admitted(execution_evaluation):
            assert execution_evaluation is not None
            expected_digest = digest(
                json.dumps(
                    execution_evaluation.receipt, sort_keys=True, indent=2
                ).encode("utf-8")
            )
            if (
                parsed.generated_execution == execution_evaluation.summary
                and parsed.generated_execution.receipt_sha256 == expected_digest
            ):
                source_qa = digest(
                    json.dumps(manifest.get("qa_reports", []), sort_keys=True).encode()
                )
                if source_qa == execution_evaluation.receipt.get("source_qa_sha256"):
                    return derive_generation_outcome(
                        manifest.get("qa_reports") or [],
                        candidate_sha256=parsed.candidate.sha256,
                        pipeline=execution_evaluation.receipt["source_pipeline"],
                        has_cells=parsed.candidate.sha256 is not None,
                        artifacts_present={"present": True, "missing": False}.get(
                            parsed.artifacts.presence
                        ),
                        artifacts_available={
                            "available": True,
                            "not_available": False,
                        }.get(parsed.artifacts.availability),
                        repair_attempts=parsed.repair.attempts,
                        max_repair_attempts=parsed.repair.limit,
                        rollback_used=parsed.repair.rollback_used,
                        execution_evaluation=execution_evaluation,
                    )
        # Serialized metadata, including a digest-looking string, is not
        # attestation. Ordinary API/durable readers have no local runner authority.
        return derive_generation_outcome(
            manifest.get("qa_reports") or [], legacy_limited=True
        )
    except ValidationError:
        return derive_generation_outcome(
            manifest.get("qa_reports") or [], legacy_limited=True
        )


def execution_description(outcome: SupportedGenerationOutcome) -> str:
    """Shared human wording, including precise scope for positive evidence."""
    if outcome.schema_version == 1:
        return "not_run. Prompt-specific behavior remains unverified."
    execution = outcome.generated_execution
    return (
        f"{execution.result}; case {execution.case_id} v{execution.case_version}; "
        f"{execution.assertions_passed}/{execution.assertions_required} assertions passed. "
        f"Mocked: {', '.join(execution.mocked) or 'none declared'}. "
        f"Untested: {'; '.join(execution.untested)}. "
        "Requirements beyond these controlled assertions remain unverified."
    )


def outcome_markdown(
    outcome: SupportedGenerationOutcome, reports: Iterable[Any] = ()
) -> str:
    """Candidate-quality prose only; never predict export/publication receipts."""
    prose = "\n".join(
        [
            "## Generation Outcome",
            "",
            f"Outcome: {outcome.status}; pipeline: {outcome.pipeline}.",
            f"Usability: {outcome.usability} (not full functional verification).",
            f"Static QA: {outcome.static_qa}.",
            f"Environment smoke (trusted_smoke_test): {outcome.environment_smoke.result}.",
            "Generated notebook execution: " + execution_description(outcome),
            f"Blocking findings: {outcome.blocking_count}; advisories: {outcome.advisory_count}.",
            f"Candidate (notebook-cells-v1): {outcome.candidate.sha256 or 'unknown'}.",
            f"Repair attempts: {outcome.repair.attempts}/{outcome.repair.limit}; rollback: {outcome.repair.rollback_used}.",
            "Checks evidenced: " + (", ".join(outcome.checks) or "none"),
            (
                "Diagnostic output: resolve blocking findings before use."
                if outcome.usability == "blocked"
                else "No known blockers is not a guarantee that generated code works."
            ),
        ]
    )
    findings = []
    for item in reports:
        report = report_payload(item)
        identity = (report.get("evidence") or {}).get("candidate_id")
        if (
            identity
            and outcome.candidate.sha256
            and identity != outcome.candidate.sha256
        ):
            continue
        if classify_report(report):
            findings.append(
                f"- {report.get('severity', 'info')} / {report.get('check_name', 'QA Check')}: {report.get('message', '')}"
            )
            findings.extend(
                f"  - Next step: {suggestion}"
                for suggestion in report.get("suggestions") or []
            )
    return prose + (
        "\n\nCurrent QA findings:\n" + "\n".join(findings) if findings else ""
    )


def with_outcome_summary(
    cells: Iterable[Any],
    outcome: SupportedGenerationOutcome,
    reports: Iterable[Any] = (),
) -> list[Any]:
    """Replace derived prose so rejected/stale repair claims cannot survive."""
    from langgraph_system_generator.generator.state import CellSpec

    retained = []
    for cell in cells:
        spec = cell if isinstance(cell, CellSpec) else CellSpec(**cell)
        if not _is_summary(spec.cell_type, spec.metadata, spec.section):
            retained.append(spec)
    retained.append(
        CellSpec(
            cell_type="markdown",
            content=outcome_markdown(outcome, reports),
            section="generation_outcome",
            metadata={"section": "generation_outcome", "kind": "generation_outcome"},
        )
    )
    return retained
