"""Candidate-bound qualification, real routing, and artifact representation parity."""

import copy
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import nbformat
import pytest

from langgraph_system_generator import cli
from langgraph_system_generator.generator import graph, nodes
from langgraph_system_generator.generator.state import CellSpec, QAReport
from langgraph_system_generator.qa.outcomes import (
    candidate_id,
    derive_generation_outcome,
    notebook_candidate_id,
    read_generation_outcome,
)
from langgraph_system_generator.qa.repair import RepairOutcome
from langgraph_system_generator.qa.summary import build_qa_summary
from langgraph_system_generator.utils.config import settings
from langgraph_system_generator.utils.error_handling import GenerationError


def report(identity=None, *, passed=True, severity="error", stage="static"):
    return QAReport(
        check_name="Candidate check",
        rule_id="candidate_check",
        passed=passed,
        severity=severity,
        message="OK" if passed else "Resolve the candidate finding.",
        stage=stage,
        evidence={"candidate_id": identity} if identity else {},
        suggestions=[] if passed else ["Inspect the selected candidate."],
    )


@pytest.mark.parametrize(
    "kind,status,static,usable",
    [
        ("pass", "completed", "passed", "no_known_blockers"),
        ("advisory", "advisories", "passed", "no_known_blockers"),
        ("block", "blocked", "failed", "blocked"),
        ("empty", "unverified", "not_run", "unknown"),
        ("stale", "unverified", "not_run", "unknown"),
        ("unbound", "unverified", "not_run", "unknown"),
        ("unbound_error", "blocked", "failed", "blocked"),
    ],
)
def test_outcome_evidence_matrix(kind, status, static, usable):
    identity = "a" * 64
    reports = [report(identity)]
    if kind == "advisory":
        reports.append(report(identity, passed=False, severity="warning"))
    elif kind in {"block", "unbound_error"}:
        reports = [report(identity if kind == "block" else None, passed=False)]
    elif kind == "empty":
        reports = []
    elif kind == "stale":
        reports = [report("b" * 64)]
    elif kind == "unbound":
        reports = [report()]
    outcome = derive_generation_outcome(
        reports, candidate_sha256=identity, pipeline="completed", has_cells=True
    )
    assert (outcome.status, outcome.static_qa, outcome.usability) == (
        status,
        static,
        usable,
    )
    assert outcome.generated_execution.result == "not_run"
    assert outcome.generated_execution.scope == "generated_notebook"
    assert "verified" != outcome.status
    assert (
        outcome.model_dump_json()
        == derive_generation_outcome(
            reports, candidate_sha256=identity, pipeline="completed", has_cells=True
        ).model_dump_json()
    )


def test_missing_and_legacy_reports_are_not_passes_or_execution_evidence():
    assert build_qa_summary([])["status"] == "not_run"
    assert build_qa_summary([])["artifacts_usable"] is None
    for manifest in (
        {},
        {"generation_outcome": {"schema_version": 99}},
        {"qa_reports": [report().model_dump()]},
    ):
        before = copy.deepcopy(manifest)
        outcome = read_generation_outcome(manifest)
        assert outcome.status == "unverified" and outcome.candidate.legacy_limited
        assert outcome.generated_execution.result == "not_run"
        assert manifest == before
    blocked = read_generation_outcome(
        {"qa_reports": [report(passed=False).model_dump()]}
    )
    assert blocked.usability == "blocked"
    for version in (None, {"schema_version": 99}):
        blocked = read_generation_outcome(
            {
                "generation_outcome": version,
                "qa_reports": [report("a" * 64, passed=False).model_dump()],
            }
        )
        assert blocked.usability == "blocked" and blocked.blocking_count == 1
        assert (
            blocked.candidate.missing_reports == 1
            and blocked.candidate.stale_reports == 0
        )
    forged = report("a" * 64, stage="runtime").model_copy(
        update={
            "evidence": {
                "candidate_id": "a" * 64,
                "execution_scope": "generated_notebook",
                "executed": True,
            }
        }
    )
    assert (
        derive_generation_outcome(
            [forged], candidate_sha256="a" * 64
        ).generated_execution.result
        == "not_run"
    )


def test_artifact_presence_and_availability_are_independent():
    present = derive_generation_outcome(
        artifacts_present=True, artifacts_available=False
    )
    assert (
        present.artifacts.presence == "present"
        and present.artifacts.availability == "not_available"
    )
    missing = derive_generation_outcome(
        artifacts_present=False, artifacts_available=False
    )
    assert missing.artifacts.presence == "missing"


def test_bound_advisories_remain_visible_in_feedback():
    feedback = nodes._qa_repair_feedback_from_reports(
        [report("a" * 64, passed=False, severity="warning")],
        repair_attempts=0,
    )
    assert any("advisories" in warning for warning in feedback.warnings)


def test_fingerprint_covers_exact_composed_cells_but_not_random_ids_or_qa_prose():
    from langgraph_system_generator.notebook.composer import NotebookComposer
    from langgraph_system_generator.qa.outcomes import with_outcome_summary

    cells = [CellSpec(cell_type="code", content="value = 1", section="nodes")]
    identity = candidate_id(cells)
    assert identity == candidate_id(cells)
    outcome = derive_generation_outcome(candidate_sha256=identity)
    assert candidate_id(with_outcome_summary(cells, outcome)) == identity
    notebook = NotebookComposer().build_notebook(cells)
    assert notebook_candidate_id(notebook) == identity
    notebook.cells[0]["id"] = "other-id"
    assert notebook_candidate_id(notebook) == identity
    notebook.cells[0].source += " "
    assert notebook_candidate_id(notebook) != identity
    executable = CellSpec(
        cell_type="code", content="value = 2", metadata={"kind": "generation_outcome"}
    )
    rendered = with_outcome_summary([executable], outcome)
    assert rendered[0] == executable
    assert candidate_id([executable]) != identity


async def invoke_graph(
    monkeypatch,
    *,
    budget=1,
    repair="success",
    empty=False,
    missing_reports=False,
    unavailable=None,
):
    monkeypatch.setattr(settings, "max_repair_attempts", budget)
    for name in (
        "intake_node",
        "rag_retrieval_node",
        "architecture_selection_node",
        "context_pack_node",
        "graph_design_node",
        "tooling_plan_node",
        "notebook_assembly_node",
    ):
        monkeypatch.setattr(graph, name, AsyncMock(return_value={}))
    calls = {"static": 0, "runtime": 0, "repair": 0}

    def validate(self, notebook):
        calls["static"] += 1
        if missing_reports:
            return []
        bad = any("bad_candidate" in cell.source for cell in notebook.cells)
        return [report(passed=not bad)]

    def preflight():
        calls["runtime"] += 1
        return (
            (False, "Runtime validation unavailable: no kernel", {})
            if unavailable
            else (True, "OK", {})
        )

    class Repair:
        def __init__(self, max_attempts):
            assert max_attempts == budget

        def repair_cells(self, cells, reports, attempt):
            assert attempt < budget
            calls["repair"] += 1
            accepted = repair == "success"
            selected = (
                [CellSpec(cell_type="code", content="good_candidate = 1")]
                if accepted
                else list(cells)
            )
            # Deliberately optimistic intermediate QA cannot substitute for final QA.
            return RepairOutcome(
                status="applied" if accepted else "rolled_back",
                cells=selected,
                qa_reports=[report(passed=True)],
                persisted=accepted,
                rollback_used=not accepted,
                validation_summary={"attempted_candidate_id": "f" * 64},
            )

    monkeypatch.setattr(nodes.NotebookValidator, "validate_notebook", validate)
    monkeypatch.setattr(nodes, "inspect_notebook_runtime_support", preflight)
    monkeypatch.setattr(
        nodes, "run_notebook_smoke_test", lambda: (True, "trusted smoke only")
    )
    monkeypatch.setattr(nodes, "NotebookRepairAgent", Repair)
    cells = (
        []
        if empty
        else [
            CellSpec(
                cell_type="code",
                content=(
                    "good_candidate = 1"
                    if unavailable or missing_reports
                    else "bad_candidate = 1"
                ),
            )
        ]
    )
    state = {
        "user_prompt": "offline routing",
        "generated_cells": cells,
        "qa_reports": [],
        "qa_history": [],
        "repair_attempts": 0,
        "constraints": [],
        "generation_mode": unavailable or "stub",
        "generation_complete": False,
    }
    result = await graph.create_generator_graph().ainvoke(
        state, config={"recursion_limit": 30 + 3 * budget}
    )
    return result, calls


@pytest.mark.parametrize(
    "budget,repair",
    [(0, "success"), (1, "success"), (1, "rollback"), (3, "rollback"), (6, "rollback")],
)
async def test_real_graph_validates_final_repair_without_exceeding_budget(
    monkeypatch, budget, repair
):
    result, calls = await invoke_graph(monkeypatch, budget=budget, repair=repair)
    expected_repairs = (1 if repair == "success" else budget) if budget else 0
    assert calls == {
        "static": expected_repairs + 1,
        "runtime": expected_repairs + 1,
        "repair": expected_repairs,
    }
    outcome = result["generation_outcome"]
    assert outcome.status == (
        "completed" if budget and repair == "success" else "blocked"
    )
    assert outcome.candidate.sha256 == candidate_id(result["generated_cells"])
    assert all(
        r.evidence["candidate_id"] == outcome.candidate.sha256
        for r in result["qa_reports"]
    )
    assert result["generation_complete"] is True
    assert outcome.generated_execution.result == "not_run"
    if repair == "rollback":
        assert "bad_candidate" in result["generated_cells"][0].content
        assert outcome.repair.rollback_used
    changed_history = dict(result, qa_history=[report(passed=False)] * 150)
    packaged = await nodes.package_outputs_node(changed_history)
    assert packaged["generation_outcome"] == outcome


@pytest.mark.parametrize(
    "mode,status,usable",
    [("live", "failed", "blocked"), ("stub", "completed", "no_known_blockers")],
)
async def test_real_graph_runtime_unavailable_is_mode_specific_without_repair(
    monkeypatch, mode, status, usable
):
    result, calls = await invoke_graph(monkeypatch, unavailable=mode)
    assert calls == {"static": 1, "runtime": 1, "repair": 0}
    outcome = result["generation_outcome"]
    assert (outcome.status, outcome.usability, outcome.environment_smoke.result) == (
        status,
        usable,
        "unavailable",
    )


async def test_real_graph_missing_reports_and_no_cells(monkeypatch):
    result, calls = await invoke_graph(monkeypatch, missing_reports=True)
    assert result["generation_outcome"].status == "unverified" and calls["repair"] == 0
    result, calls = await invoke_graph(monkeypatch, empty=True)
    assert result["generation_outcome"].status == "failed"
    assert result["generation_complete"] is False and result["artifacts_manifest"] == {}
    assert calls["repair"] == 0


@pytest.mark.parametrize(
    "kind,status",
    [
        ("pass", "completed"),
        ("advisory", "advisories"),
        ("block", "blocked"),
        ("empty", "unverified"),
    ],
)
async def test_real_exports_share_candidate_quality_and_receipts(
    monkeypatch, tmp_path, kind, status
):
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    real_stub = cli._build_stub_result
    result = real_stub("Create a router")
    identity = candidate_id(result["generated_cells"])
    result["qa_reports"] = [] if kind == "empty" else [report(identity)]
    if kind in {"advisory", "block"}:
        result["qa_reports"].append(
            report(
                identity,
                passed=False,
                severity="warning" if kind == "advisory" else "error",
            )
        )
    monkeypatch.setattr(
        cli, "_build_stub_result", lambda *args, **kwargs: copy.deepcopy(result)
    )
    artifacts = await cli.generate_artifacts(
        "Create a router", output_dir=tmp_path / kind, formats=["ipynb", "html", "zip"]
    )
    manifest = json.loads(Path(artifacts["manifest_path"]).read_text(encoding="utf-8"))
    outcome = manifest["generation_outcome"]
    assert (
        outcome
        == artifacts["generation_outcome"]
        == artifacts["result"]["generation_outcome"]
    )
    assert (
        outcome["status"] == status
        and outcome["generated_execution"]["result"] == "not_run"
    )
    assert outcome["artifacts"]["availability"] == "available"
    notebook = nbformat.read(manifest["notebook_path"], as_version=4)
    assert notebook_candidate_id(notebook) == identity
    prose = "\n".join(
        cell.source for cell in notebook.cells if cell.cell_type == "markdown"
    )
    assert (
        f"Outcome: {status}" in prose
        and "Generated notebook execution: not_run" in prose
    )
    if kind == "block":
        assert "Resolve the candidate finding." in prose
        assert "Inspect the selected candidate." in prose
    assert f"Outcome: {status}" in Path(manifest["html_path"]).read_text(
        encoding="utf-8"
    )
    with zipfile.ZipFile(manifest["zip_path"]) as archive:
        zipped = nbformat.reads(
            archive.read("notebook.ipynb").decode("utf-8"), as_version=4
        )
        assert notebook_candidate_id(zipped) == identity
        assert f"Outcome: {status}" in "\n".join(c.source for c in zipped.cells)
        assert archive.read("notebook.html") == Path(manifest["html_path"]).read_bytes()


async def test_no_cells_package_fails_without_empty_manifest(monkeypatch, tmp_path):
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        cli,
        "_build_stub_result",
        lambda *a, **k: {"generated_cells": [], "generation_complete": True},
    )
    with pytest.raises(GenerationError) as caught:
        await cli.generate_artifacts("empty", output_dir=tmp_path / "empty")
    assert caught.value.details["generation_outcome"]["status"] == "failed"
    assert not (tmp_path / "empty" / "manifest.json").exists()


async def test_real_stub_outcome_serialization_is_deterministic(monkeypatch, tmp_path):
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    first = await cli.generate_artifacts(
        "Create a router", output_dir=tmp_path / "one", formats=["ipynb"]
    )
    second = await cli.generate_artifacts(
        "Create a router", output_dir=tmp_path / "two", formats=["ipynb"]
    )
    assert first["generation_outcome"] == second["generation_outcome"]
    assert first["generation_outcome"]["static_qa"] == "not_run"
    assert first["generation_outcome"]["usability"] == "unknown"


async def test_incomplete_candidate_and_terminal_exception_are_explicit_failures(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    result = cli._build_stub_result("Create a router")
    result["generation_complete"] = False
    monkeypatch.setattr(cli, "_build_stub_result", lambda *a, **k: result)
    with pytest.raises(GenerationError) as incomplete:
        await cli.generate_artifacts(
            "incomplete", output_dir=tmp_path / "incomplete", formats=["ipynb"]
        )
    assert incomplete.value.details["generation_outcome"]["pipeline"] == "failed"
    fake_graph = type(
        "Graph", (), {"ainvoke": AsyncMock(side_effect=RuntimeError("private failure"))}
    )()
    monkeypatch.setattr(cli, "_load_generator_graph", lambda: lambda: fake_graph)
    with pytest.raises(GenerationError) as failure:
        await cli.generate_artifacts(
            "failure", mode="live", output_dir=tmp_path / "failure", formats=["ipynb"]
        )
    payload = failure.value.to_payload()
    assert payload["details"]["generation_outcome"]["status"] == "failed"
    assert "private failure" not in json.dumps(payload)
    assert not (tmp_path / "failure" / "manifest.json").exists()


@pytest.mark.parametrize(
    "kind,exit_code", [("pass", 0), ("advisory", 0), ("empty", 0), ("block", 2)]
)
def test_cli_quality_exit_and_diagnostic_paths(monkeypatch, capsys, kind, exit_code):
    identity = "a" * 64
    reports = [] if kind == "empty" else [report(identity, passed=kind != "block")]
    if kind == "advisory":
        reports.append(report(identity, passed=False, severity="warning"))
    outcome = derive_generation_outcome(
        reports, candidate_sha256=identity, pipeline="completed", has_cells=True
    )
    artifacts = {
        "manifest": {
            "generation_outcome": outcome.model_dump(),
            "notebook_path": "diagnostics.ipynb",
        },
        "manifest_path": "manifest.json",
        "output_dir": "diagnostics",
    }
    monkeypatch.setattr(cli, "generate_artifacts", AsyncMock(return_value=artifacts))
    assert cli.main(["generate", "offline"]) == exit_code
    text = capsys.readouterr().out
    assert "diagnostics.ipynb" in text and "not_run" in text
