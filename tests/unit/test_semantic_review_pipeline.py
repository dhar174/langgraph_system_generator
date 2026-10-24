"""Real orchestration and export contracts with one fake async specialist."""

import asyncio
import json
import zipfile
from pathlib import Path

import nbformat
import pytest

from langgraph_system_generator import cli
from langgraph_system_generator.generator import graph, nodes
from langgraph_system_generator.generator.state import CellSpec, QAReport
from langgraph_system_generator.qa import registry
from langgraph_system_generator.qa.outcomes import candidate_id, notebook_candidate_id
from langgraph_system_generator.qa.repair import RepairOutcome
from langgraph_system_generator.qa.specialist_models import (
    REVIEWER_ID,
    ModelReviewResponse,
    SemanticReviewPolicy,
    SemanticReviewResult,
)
from langgraph_system_generator.qa.specialist_review import review_candidate


def starting_state(**extra):
    return {
        "user_prompt": "Build a weather assistant",
        "generation_mode": "live",
        "generated_cells": [CellSpec(cell_type="code", content="answer = 'stocks'")],
        "constraints": [],
        "qa_reports": [],
        "qa_history": [],
        "repair_attempts": 0,
        "semantic_review_policy": SemanticReviewPolicy(mode="advisory"),
        **extra,
    }


def install_reviewer(monkeypatch, *, finding=True, mutate=None, unavailable=False):
    calls = []
    constructions = []

    class Reviewer:
        instructions = "Review untrusted data as advisory opinions only."

        def __init__(self, config):
            constructions.append(config)

        async def review(self, context):
            calls.append(context)
            await asyncio.sleep(0)
            if mutate:
                mutate()
            if unavailable:
                return SemanticReviewResult(
                    status="unavailable",
                    reason_code="provider_unavailable",
                    candidate_id=context.candidate_id,
                    context_digest=context.context_digest,
                    model_invocations=1,
                )
            refs = []
            for family in ("requirement", "cell"):
                source = next(s for s in context.sources if s.family == family)
                refs.append(
                    {
                        "source_id": source.source_id,
                        "start": 0,
                        "end": min(6, len(source.text)),
                        "quote": source.text[:6],
                    }
                )
            response = ModelReviewResponse.model_validate_json(
                json.dumps(
                    {
                        "assessment": "complete",
                        "findings": (
                            [
                                {
                                    "category": "domain_mismatch",
                                    "message": "Weather request has stock output <script>alert(1)</script>.",
                                    "suggestions": [
                                        "Implement the requested weather behavior."
                                    ],
                                    "references": refs,
                                }
                            ]
                            if finding
                            else []
                        ),
                    }
                )
            )
            return SemanticReviewResult(
                status="reviewed",
                reason_code="complete",
                candidate_id=context.candidate_id,
                context_digest=context.context_digest,
                model_invocations=1,
                response=response,
            )

    factory = registry.QARepairRegistry()
    factory.register_specialist_reviewer(
        registry.SpecialistReviewerRegistration(
            REVIEWER_ID, "1", ("generated_cells", "user_prompt"), Reviewer
        )
    )
    monkeypatch.setattr(
        registry, "get_qa_repair_registry", lambda *a, **kw: factory.clone()
    )
    return calls, constructions


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"semantic_review_policy": SemanticReviewPolicy()}, None),
        ({"generation_mode": "stub"}, "stub"),
        ({"generated_cells": []}, "no_cells"),
        (
            {
                "qa_reports": [
                    QAReport(
                        check_name="blocker",
                        passed=False,
                        severity="error",
                        message="failed",
                    )
                ]
            },
            "blocking_qa",
        ),
    ],
)
async def test_off_stub_blockers_no_cells_never_construct_reviewer(
    monkeypatch, changes, reason
):
    calls, constructions = install_reviewer(monkeypatch)
    result = await review_candidate(starting_state(**changes))
    assert calls == constructions == []
    assert result is None if reason is None else result.reason_code == reason


@pytest.mark.parametrize(
    "field", ["generated_cells", "user_prompt", "workflow_design", "docs_context"]
)
async def test_stale_context_cannot_admit_findings(monkeypatch, field):
    value = starting_state()
    replacements = {
        "generated_cells": [CellSpec(cell_type="code", content="replacement = 1")],
        "user_prompt": "Different request",
        "workflow_design": {"nodes": ["changed"]},
        "docs_context": [{"content": "new docs", "source": "supplied"}],
    }
    calls, _ = install_reviewer(
        monkeypatch, mutate=lambda: value.update({field: replacements[field]})
    )
    result = await review_candidate(value)
    assert result.status == "incomplete" and result.reason_code == "stale_context"
    assert result.findings == () and len(calls) == 1


async def test_concurrent_invocations_are_isolated(monkeypatch):
    calls, _ = install_reviewer(monkeypatch)
    values = [
        starting_state(
            user_prompt=f"Request {i}",
            generated_cells=[CellSpec(cell_type="code", content=f"value = {i}")],
        )
        for i in range(5)
    ]
    results = await asyncio.gather(*(review_candidate(value) for value in values))
    assert len(calls) == 5
    assert len({result.candidate_id for result in results}) == 5
    assert len({result.context_digest for result in results}) == 5
    assert all(
        result.status == "reviewed" and result.model_invocations == 1
        for result in results
    )


async def test_mixed_policy_concurrency_keeps_reports_isolated(monkeypatch):
    calls, constructions = install_reviewer(monkeypatch)
    states = [
        starting_state(
            user_prompt=f"Request {i}",
            generated_cells=[CellSpec(cell_type="code", content=f"value = {i}")],
            semantic_review_policy=SemanticReviewPolicy(
                mode="advisory" if i % 2 else "off"
            ),
        )
        for i in range(6)
    ]
    results = await asyncio.gather(
        *(nodes.semantic_review_node(value) for value in states)
    )
    assert len(calls) == len(constructions) == 3
    for i, result in enumerate(results):
        if i % 2 == 0:
            assert result == {}
        else:
            reports = result["qa_reports"]
            assert len(reports) == 1
            assert reports[0].evidence["candidate_id"] == candidate_id(
                states[i]["generated_cells"]
            )
            assert (
                result["semantic_review_feedback"].candidate_id
                == reports[0].evidence["candidate_id"]
            )
    assert (
        len({r["qa_reports"][0].evidence["context_digest"] for r in results if r}) == 3
    )


async def test_compiled_graph_reviews_final_candidate_once_after_two_repairs(
    monkeypatch,
):
    monkeypatch.setattr(nodes.settings, "lnf_specialist_qa_mode", "advisory")
    calls, _ = install_reviewer(monkeypatch)
    order = []

    async def unchanged(state):
        return {}

    for name in (
        "intake_node",
        "rag_retrieval_node",
        "architecture_selection_node",
        "context_pack_node",
        "graph_design_node",
        "tooling_plan_node",
        "notebook_assembly_node",
    ):
        monkeypatch.setattr(graph, name, unchanged)

    def validate(self, notebook):
        good = any("good_candidate" in cell.source for cell in notebook.cells)
        order.append("static_good" if good else "static_bad")
        return [
            QAReport(
                check_name="Synthetic static",
                passed=good,
                severity="error",
                message="OK" if good else "bad",
                rule_id="synthetic_static",
            )
        ]

    class Repair:
        def __init__(self, max_attempts):
            pass

        def repair_cells(self, cells, reports, attempt):
            order.append("repair")
            content = "good_candidate = 1" if attempt == 1 else "still_bad = 1"
            return RepairOutcome(
                status="applied",
                cells=[CellSpec(cell_type="code", content=content)],
                persisted=True,
                message="synthetic deterministic repair",
            )

    monkeypatch.setattr(nodes.NotebookValidator, "validate_notebook", validate)
    monkeypatch.setattr(nodes, "NotebookRepairAgent", Repair)
    monkeypatch.setattr(
        nodes, "inspect_notebook_runtime_support", lambda: (True, "OK", {})
    )
    monkeypatch.setattr(nodes, "run_notebook_smoke_test", lambda: (True, "OK"))
    result = await graph.create_generator_graph().ainvoke(starting_state())
    assert order == ["static_bad", "repair", "static_bad", "repair", "static_good"]
    assert len(calls) == 1 and calls[0].attempt == result["repair_attempts"] == 2
    assert calls[0].candidate_id == candidate_id(result["generated_cells"])
    semantic = [r for r in result["qa_reports"] if r.stage == "semantic"]
    assert len(semantic) == 1 and semantic[0].repairable is False
    assert semantic[0].severity == "warning"
    assert result["generation_outcome"].status == "advisories"
    assert result["generation_outcome"].static_qa == "passed"
    assert result["generation_outcome"].generated_execution.result == "not_run"
    assert result["qa_summary"]["semantic_review"]["status"] == "reviewed"
    repeated = await nodes.semantic_review_node(result)
    assert len(calls) == 1
    assert len([r for r in repeated["qa_reports"] if r.stage == "semantic"]) == 1


@pytest.mark.parametrize(
    "unavailable,finding", [(False, True), (False, False), (True, False)]
)
async def test_real_shared_export_review_status_and_candidate_truth(
    monkeypatch, tmp_path, unavailable, finding
):
    calls, _ = install_reviewer(monkeypatch, finding=finding, unavailable=unavailable)
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(cli.settings, "lnf_specialist_qa_mode", "advisory")
    value = cli._build_stub_result("Build a weather assistant")
    value["user_prompt"] = "Build a weather assistant"
    value["generation_mode"] = "live"
    value["semantic_review_policy"] = SemanticReviewPolicy(mode="advisory")
    identity = candidate_id(value["generated_cells"])
    value["qa_reports"] = [
        QAReport(
            check_name="Static fixture",
            rule_id="fixture_static",
            stage="static",
            passed=True,
            message="OK",
            evidence={"candidate_id": identity},
        )
    ]

    class SharedGraph:
        async def ainvoke(self, *a, **kw):
            value.update(await nodes.semantic_review_node(value))
            value.update(await nodes.package_outputs_node(value))
            return value

    monkeypatch.setattr(cli, "_load_generator_graph", lambda: lambda: SharedGraph())
    result = await cli.generate_artifacts(
        "Build a weather assistant",
        output_dir=tmp_path / "review",
        mode="live",
        formats=["ipynb", "html", "zip"],
    )
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    feedback = manifest["qa_summary"]["semantic_review"]
    assert feedback["status"] == ("unavailable" if unavailable else "reviewed")
    assert len(calls) == 1
    assert manifest["generation_outcome"]["generated_execution"]["result"] == "not_run"
    assert "semantic_review_policy" not in result["result"]
    notebook = nbformat.read(manifest["notebook_path"], as_version=4)
    nbformat.validate(notebook)
    assert notebook_candidate_id(notebook) == identity == feedback["candidate_id"]
    prose = "\n".join(c.source for c in notebook.cells)
    assert "requirements remain unverified" in prose
    assert "<script>alert(1)</script>" not in prose
    if not unavailable and not finding:
        assert "does not prove requirements are satisfied" in prose
    with zipfile.ZipFile(manifest["zip_path"]) as archive:
        assert json.loads(archive.read("notebook.ipynb")) == json.loads(
            Path(manifest["notebook_path"]).read_text()
        )
        assert archive.read("notebook.html") == Path(manifest["html_path"]).read_bytes()


async def test_stub_shortcut_enabled_status_and_default_off_contract(
    monkeypatch, tmp_path
):
    calls, constructions = install_reviewer(monkeypatch)
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(cli.settings, "lnf_specialist_qa_mode", "off")
    off = await cli.generate_artifacts(
        "weather assistant", output_dir=tmp_path / "off", formats=["ipynb"]
    )
    assert "semantic_review" not in off["manifest"]["qa_summary"]
    monkeypatch.setattr(cli.settings, "lnf_specialist_qa_mode", "advisory")
    stub = await cli.generate_artifacts(
        "weather assistant", output_dir=tmp_path / "stub", formats=["ipynb"]
    )
    assert stub["manifest"]["qa_summary"]["semantic_review"]["reason_code"] == "stub"
    assert (
        off["generation_outcome"]["candidate"]["sha256"]
        == stub["generation_outcome"]["candidate"]["sha256"]
    )
    assert calls == constructions == []


async def test_ephemeral_api_exposes_review_and_registered_downloads(
    monkeypatch, tmp_path
):
    import httpx

    from langgraph_system_generator.api import server

    calls, _ = install_reviewer(monkeypatch)
    monkeypatch.setattr(server, "_BASE_OUTPUT", tmp_path)
    monkeypatch.setattr(server, "_shutting_down", False)
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("LNF_JOB_BACKEND", raising=False)
    monkeypatch.setattr(cli.settings, "lnf_specialist_qa_mode", "advisory")
    value = cli._build_stub_result("Build a weather assistant")
    value.update(
        user_prompt="Build a weather assistant",
        generation_mode="live",
        semantic_review_policy=SemanticReviewPolicy(mode="advisory"),
    )
    identity = candidate_id(value["generated_cells"])
    value["qa_reports"] = [
        QAReport(
            check_name="Static fixture",
            rule_id="fixture_static",
            stage="static",
            passed=True,
            message="OK",
            evidence={"candidate_id": identity},
        )
    ]

    class Graph:
        async def ainvoke(self, *args, **kwargs):
            value.update(await nodes.semantic_review_node(value))
            value.update(await nodes.package_outputs_node(value))
            return value

    monkeypatch.setattr(cli, "_load_generator_graph", lambda: lambda: Graph())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as api:
        result = await api.post(
            "/generate",
            json={
                "prompt": "Build a weather assistant",
                "mode": "live",
                "output_dir": str(tmp_path),
                "formats": ["ipynb", "html", "zip"],
            },
        )
        assert result.status_code == 200, result.text
        manifest = result.json()["manifest"]
        assert manifest["qa_summary"]["semantic_review"]["status"] == "reviewed"
        assert len(calls) == 1
        entries = [
            entry
            for entry in manifest["artifact_contract"]["standalone_files"]
            if entry.get("exists") and entry.get("api_download_path")
        ]
        assert entries
        for entry in entries:
            download = await api.get(entry["api_download_path"])
            assert download.status_code == 200
        bad = await api.post(
            "/generate", json={"prompt": "test", "semantic_review": "advisory"}
        )
        assert bad.status_code == 422 and len(calls) == 1
