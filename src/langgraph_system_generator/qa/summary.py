"""Compact QA report classification for manifests, APIs, and UI surfaces."""

from __future__ import annotations

from typing import Any, Iterable

from langgraph_system_generator.generator.state import QAReport


def serialize_qa_report(report: QAReport | dict[str, Any]) -> dict[str, Any]:
    """Return a plain dict for a QA report-like object."""

    if hasattr(report, "model_dump"):
        return report.model_dump()
    if isinstance(report, dict):
        return dict(report)
    return {
        "check_name": str(getattr(report, "check_name", "QA Check")),
        "passed": bool(getattr(report, "passed", True)),
        "message": str(getattr(report, "message", "")),
        "rule_id": str(getattr(report, "rule_id", "qa_report")),
        "severity": str(getattr(report, "severity", "info")),
        "category": str(getattr(report, "category", "general")),
        "suggestions": list(getattr(report, "suggestions", []) or []),
        "repairable": bool(getattr(report, "repairable", False)),
        "stage": getattr(report, "stage", None),
        "attempt": getattr(report, "attempt", None),
        "evidence": dict(getattr(report, "evidence", {}) or {}),
    }


def qa_failure_classification(report: QAReport | dict[str, Any]) -> str | None:
    """Classify failed QA reports by release impact."""

    payload = serialize_qa_report(report)
    if payload.get("passed", True):
        return None
    severity = str(payload.get("severity") or "info").lower()
    if severity == "error":
        return "blocking"
    if severity == "warning":
        return "non_blocking"
    return "informational"


def has_blocking_failures(reports: Iterable[QAReport | dict[str, Any]]) -> bool:
    """Return True when any current QA report is a blocking failure."""

    return any(qa_failure_classification(report) == "blocking" for report in reports)


def build_qa_summary(reports: Iterable[QAReport | dict[str, Any]]) -> dict[str, Any]:
    """Build a compact manifest/API summary for the current QA snapshot."""

    serialized_reports = [serialize_qa_report(report) for report in reports]
    findings: list[dict[str, Any]] = []
    counts = {
        "total": len(serialized_reports),
        "passed": 0,
        "failed": 0,
        "blocking": 0,
        "non_blocking": 0,
        "informational": 0,
    }

    for report in serialized_reports:
        if report.get("passed", True):
            counts["passed"] += 1
            continue

        counts["failed"] += 1
        classification = qa_failure_classification(report) or "informational"
        counts[classification] += 1
        findings.append(
            {
                "classification": classification,
                "stage": report.get("stage"),
                "check_name": report.get("check_name", "QA Check"),
                "rule_id": report.get("rule_id", "qa_report"),
                "severity": report.get("severity", "info"),
                "message": report.get("message", ""),
                "suggestions": list(report.get("suggestions") or []),
                "repairable": bool(report.get("repairable", False)),
                "attempt": report.get("attempt"),
            }
        )

    if counts["blocking"]:
        status = "blocking_failed"
    elif counts["non_blocking"] or counts["informational"]:
        status = "advisories"
    else:
        status = "passed"

    return {
        "status": status,
        "artifacts_usable": counts["blocking"] == 0,
        "counts": counts,
        "findings": findings,
        "validation_scope": _build_validation_scope(serialized_reports),
    }


def _build_validation_scope(reports: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Describe what QA reports prove and what remains outside their scope."""

    validated: list[str] = []
    not_validated: list[str] = []
    notes: list[str] = []

    if not reports:
        not_validated.append("No QA reports were recorded for this run.")
        return {
            "validated": validated,
            "not_validated": not_validated,
            "notes": notes,
        }

    stages = {str(report.get("stage") or "").lower() for report in reports}
    rule_ids = {str(report.get("rule_id") or "") for report in reports}

    if "static" in stages:
        validated.append(
            "Static QA checked the generated notebook cells covered by qa_reports."
        )

    runtime_reports = [
        report
        for report in reports
        if str(report.get("stage") or "").lower() == "runtime"
        or str(report.get("category") or "").lower() == "runtime"
    ]
    smoke_only = any(
        report.get("rule_id") == "runtime_smoke_test"
        and (report.get("evidence") or {}).get("execution_scope")
        == "trusted_smoke_test"
        for report in runtime_reports
    )

    if smoke_only:
        validated.append(
            "Runtime QA validated that the Python/Jupyter environment can execute a trusted smoke notebook."
        )
        not_validated.append(
            "Runtime QA did not execute the full generated notebook or verify prompt-specific behavior."
        )
    elif runtime_reports:
        validated.append(
            "Runtime QA is limited to the runtime checks reported in qa_reports."
        )

    if rule_ids - {"runtime_smoke_test"}:
        notes.append("See qa_reports for rule-level findings and evidence.")

    return {
        "validated": validated,
        "not_validated": not_validated,
        "notes": notes,
    }
