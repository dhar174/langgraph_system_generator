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


def build_tool_contract_summary(
    tools_plan: Iterable[Any] | None,
    graph_exports: Any | None = None,
    qa_reports: Iterable[QAReport | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize planned tools and their honest execution contract."""

    planned_tools = [_tool_payload(tool) for tool in (tools_plan or [])]
    reachability = _tool_reachability_entries(graph_exports)
    reachability_by_id = {
        str(
            entry.get("tool_id") or entry.get("name") or entry.get("tool_name") or ""
        ): entry
        for entry in reachability
        if entry.get("tool_id") or entry.get("name") or entry.get("tool_name")
    }
    executable_paths = {
        "tool_node",
        "manual_loop",
        "create_agent",
        "create_react_agent",
    }
    utility_paths = {
        "demo_only",
        "deterministic_node",
        "omitted",
        "utility",
        "local_helper",
    }

    executable_tools: list[dict[str, Any]] = []
    utility_helpers: list[dict[str, Any]] = []
    unsupported_tools: list[dict[str, Any]] = []
    unclassified_tools: list[dict[str, Any]] = []
    summarized_ids: set[str] = set()

    for tool in planned_tools:
        tool_id = str(tool.get("tool_id") or tool.get("name") or "").strip()
        status = str(tool.get("status") or "ready").strip().lower()
        reachability_entry = reachability_by_id.get(tool_id, {})
        execution_path = str(
            reachability_entry.get("execution_path")
            or reachability_entry.get("path")
            or ""
        ).strip()
        summary_entry = {
            "tool_id": tool_id,
            "name": tool.get("name") or tool_id,
            "status": status or "ready",
            "execution_path": execution_path or None,
            "node": reachability_entry.get("node"),
            "rationale": reachability_entry.get("rationale") or "",
        }
        if status == "unsupported":
            unsupported_tools.append(summary_entry)
        elif execution_path in executable_paths:
            executable_tools.append(summary_entry)
        elif execution_path in utility_paths:
            utility_helpers.append(summary_entry)
        else:
            summary_entry["status"] = "missing_contract"
            unclassified_tools.append(summary_entry)
        if tool_id:
            summarized_ids.add(tool_id)

    for tool_id, reachability_entry in reachability_by_id.items():
        if tool_id in summarized_ids:
            continue
        execution_path = str(
            reachability_entry.get("execution_path")
            or reachability_entry.get("path")
            or ""
        ).strip()
        summary_entry = {
            "tool_id": tool_id,
            "name": reachability_entry.get("name") or tool_id,
            "status": "planned_by_graph",
            "execution_path": execution_path or None,
            "node": reachability_entry.get("node"),
            "rationale": reachability_entry.get("rationale") or "",
        }
        if execution_path in executable_paths:
            executable_tools.append(summary_entry)
        elif execution_path in utility_paths:
            utility_helpers.append(summary_entry)
        else:
            summary_entry["status"] = "unrecognized_execution_path"
            unclassified_tools.append(summary_entry)

    qa_evidence = _tool_contract_qa_evidence(qa_reports or [])
    return {
        "version": 1,
        "counts": {
            "planned": len(planned_tools),
            "executable": len(executable_tools),
            "utility": len(utility_helpers),
            "unsupported": len(unsupported_tools),
            "unclassified": len(unclassified_tools),
        },
        "planned_tools": planned_tools,
        "executable_tools": executable_tools,
        "utility_helpers": utility_helpers,
        "unsupported_tools": unsupported_tools,
        "unclassified_tools": unclassified_tools,
        "qa_evidence": qa_evidence,
        "source_precedence": [
            "graph_exports.schema.tool_reachability",
            "tools_plan",
            "qa_reports.tool_reachability",
        ],
    }


def _tool_payload(tool: Any) -> dict[str, Any]:
    """Return a normalized manifest-safe tool payload."""

    if hasattr(tool, "model_dump"):
        payload = tool.model_dump()
    elif isinstance(tool, dict):
        payload = dict(tool)
    else:
        payload = {
            "tool_id": str(getattr(tool, "tool_id", "")),
            "name": str(getattr(tool, "name", "")),
            "status": str(getattr(tool, "status", "ready")),
        }
    payload.setdefault("status", "ready")
    return payload


def _tool_reachability_entries(graph_exports: Any | None) -> list[dict[str, Any]]:
    """Extract graph tool reachability metadata from dict or Pydantic exports."""

    if graph_exports is None:
        return []
    if hasattr(graph_exports, "model_dump"):
        payload = graph_exports.model_dump(by_alias=True)
    elif isinstance(graph_exports, dict):
        payload = graph_exports
    else:
        return []

    schema = payload.get("schema") or payload.get("schema_payload") or {}
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump()
    if not isinstance(schema, dict):
        return []
    entries = schema.get("tool_reachability") or payload.get("tool_reachability") or []
    normalized_entries: list[dict[str, Any]] = []
    for entry in entries:
        if hasattr(entry, "model_dump"):
            normalized_entries.append(entry.model_dump())
        elif isinstance(entry, dict):
            normalized_entries.append(dict(entry))
    return normalized_entries


def _tool_contract_qa_evidence(
    qa_reports: Iterable[QAReport | dict[str, Any]],
) -> dict[str, Any]:
    """Collect tool-reachability QA evidence without overriding planner truth."""

    reachable_tools: list[str] = []
    advisories: list[dict[str, Any]] = []
    for report in (serialize_qa_report(item) for item in qa_reports):
        if report.get("rule_id") != "tool_reachability":
            continue
        evidence = report.get("evidence") or {}
        for tool_name in evidence.get("reachable_tools") or []:
            if tool_name not in reachable_tools:
                reachable_tools.append(tool_name)
        for advisory in evidence.get("advisories") or []:
            if isinstance(advisory, dict):
                advisories.append(dict(advisory))
    return {"reachable_tools": reachable_tools, "advisories": advisories}


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

    def _execution_scope(report: dict[str, Any]) -> str | None:
        evidence = report.get("evidence")
        if not isinstance(evidence, dict):
            return None
        scope = evidence.get("execution_scope")
        if isinstance(scope, str):
            return scope
        execution = evidence.get("execution")
        if isinstance(execution, dict):
            nested_scope = execution.get("execution_scope")
            if isinstance(nested_scope, str):
                return nested_scope
        return None

    smoke_only = any(
        report.get("rule_id") == "runtime_smoke_test"
        and _execution_scope(report) == "trusted_smoke_test"
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
