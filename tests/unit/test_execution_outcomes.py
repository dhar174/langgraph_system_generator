"""Synthetic admission controls; actual generated graph execution is integration-tested."""

import copy
import json
import zipfile
from pathlib import Path

import nbformat
import pytest
from pydantic import ValidationError

from langgraph_system_generator.generator.state import CellSpec
from langgraph_system_generator.notebook.composer import NotebookComposer
from langgraph_system_generator.qa.evaluated_bundle import build_evaluated_bundle
from langgraph_system_generator.qa.execution_models import (
    ExecutionDataset,
    ExecutionResult,
)
from langgraph_system_generator.qa.execution_qualification import (
    DATASET_SHA256,
    _mark_supervised,
    digest,
    qualify_execution,
    required_assertions,
)
from langgraph_system_generator.qa.outcomes import (
    derive_generation_outcome,
    execution_description,
    notebook_candidate_id,
    outcome_markdown,
    read_generation_outcome,
)
from langgraph_system_generator.qa.summary import build_qa_summary

ROOT = Path(__file__).parents[2]
DATASET = ExecutionDataset.model_validate_json(
    (ROOT / "tests/evaluation/generated_notebook_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture
def evidence(tmp_path):
    case = DATASET.cases[0]
    cells = [CellSpec(cell_type="code", content="value = 1", section="nodes")]
    notebook = NotebookComposer().build_notebook(cells)
    original = nbformat.writes(notebook).encode()
    identity = notebook_candidate_id(notebook)
    source = tmp_path / "generated"
    source.mkdir()
    (source / "notebook.ipynb").write_bytes(original)
    (source / "generated_cells.json").write_text(
        json.dumps([cell.model_dump() for cell in cells])
    )
    reports = [
        {
            "stage": "static",
            "rule_id": "syntax",
            "passed": True,
            "severity": "error",
            "evidence": {"candidate_id": identity},
        }
    ]
    manifest = {
        "generation_outcome": derive_generation_outcome(
            reports,
            candidate_sha256=identity,
            pipeline="completed",
            has_cells=True,
        ).model_dump(mode="json"),
        "qa_reports": reports,
    }
    (tmp_path / "fixture-manifest.json").write_text(json.dumps(manifest))
    derived = tmp_path / "clean-execution.ipynb"
    derived.write_text(
        nbformat.writes(
            nbformat.v4.new_notebook(
                cells=[
                    nbformat.v4.new_code_cell("# unit bootstrap"),
                    *[
                        cell
                        for cell in notebook.cells
                        if not (
                            cell.cell_type == "code"
                            and cell.metadata.get("section") == "setup"
                        )
                    ],
                    nbformat.v4.new_code_cell("# unit probe"),
                ]
            )
        ),
        encoding="utf-8",
    )
    code = [
        i
        for i, cell in enumerate(notebook.cells, 1)
        if cell.cell_type == "code" and cell.metadata.get("section") != "setup"
    ]
    excluded = {
        str(i): "Dependency installation excluded; dependencies preflighted in child"
        for i, cell in enumerate(notebook.cells, 1)
        if cell.cell_type == "code" and cell.metadata.get("section") == "setup"
    }
    provenance = dict(
        generator_revision="a" * 40,
        source_dirty=False,
        source_diff_sha256=digest(b""),
        source_tree_sha256="b" * 64,
        source_files_sha256={"fixture.py": "c" * 64},
    )
    result = ExecutionResult(
        case_id=case.id,
        fixture=case.fixture,
        **provenance,
        notebook_path=str(source / "notebook.ipynb"),
        notebook_sha256=digest(original),
        candidate_sha256=identity,
        original_candidate_sha256=identity,
        derived_notebook_path=str(derived),
        derived_sha256=digest(derived.read_bytes()),
        serialized_cell_count=len(notebook.cells),
        environment={
            "source_manifest_sha256": digest(
                (tmp_path / "fixture-manifest.json").read_bytes()
            ),
            "source_cells_sha256": digest(
                (source / "generated_cells.json").read_bytes()
            ),
            "python": "synthetic unit fixture",
            "kernel": "fake unit kernel",
            "dependencies": {name: "unit-version" for name in case.dependencies},
            "case_specification": case.model_dump(mode="json"),
            "derived_attempted_cells": [1, 2],
            "derived_completed_cells": [1, 2],
        },
        isolation={
            "level": "trusted fixture",
            "network": "guard",
            "credentials": "synthetic",
            "enforced_limits": {"memory": "bounded", "cpu": "bounded"},
        },
        attempted_cells=code,
        completed_cells=code,
        excluded_cells=excluded,
        observations=[
            {"invocation": invocation.id, "nodes": invocation.expected_nodes}
            for invocation in case.invocations
        ],
        assertions=[
            {"name": name, "passed": True} for name in sorted(required_assertions(case))
        ],
        executed=["LangGraph"],
        cleanup_verified=True,
        status="passed",
    )
    (tmp_path / "clean-receipt.json").write_text(result.model_dump_json())
    _mark_supervised(result, provenance)
    return dict(
        case=case,
        result=result,
        notebook=notebook,
        manifest=manifest,
        source_bytes=original,
        provenance=provenance,
        dataset_sha256=DATASET_SHA256,
        controls_verified=True,
        raw_receipt_sha256="d" * 64,
    )


@pytest.mark.parametrize("passed,expected_exit", [(True, 0), (False, 1)])
def test_separate_evaluation_command_exit_semantics(
    tmp_path, monkeypatch, passed, expected_exit
):
    import importlib.util

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "qualification_exit", ROOT / "scripts/run_generated_notebook_eval.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "output_root", lambda path: tmp_path)
    calls = []

    def fake_run(dataset, root, **kwargs):
        calls.append(kwargs)
        return {"passed": passed}

    monkeypatch.setattr(runner, "run", fake_run)
    assert (
        runner.main(["--qualify-outcomes", "--output", str(tmp_path)]) == expected_exit
    )
    assert calls == [{"qualify_outcomes": True}]


def outcome(evidence, **kwargs):
    qualified = qualify_execution(**evidence)
    return derive_generation_outcome(
        evidence["manifest"]["qa_reports"],
        candidate_sha256=kwargs.pop(
            "candidate_sha256", notebook_candidate_id(evidence["notebook"])
        ),
        pipeline="completed",
        has_cells=True,
        execution_evaluation=qualified,
        **kwargs,
    )


def test_approved_dataset_and_independent_assertion_inventory():
    assert digest(DATASET.model_dump_json().encode()) == DATASET_SHA256
    assert [len(required_assertions(case)) for case in DATASET.cases] == [34, 25, 51]


def test_scoped_pass_round_trip_prose_and_api(evidence):
    from langgraph_system_generator.api.server import GenerationResponse

    result = outcome(evidence)
    assert result.schema_version == 2
    assert result.generated_execution.result == "passed"
    assert result.static_qa == "passed" and result.pipeline == "completed"
    assert result.usability == "no_known_blockers"
    assert (
        read_generation_outcome(
            {
                "generation_outcome": result.model_dump(),
                "qa_reports": evidence["manifest"]["qa_reports"],
            },
            execution_evaluation=qualify_execution(**evidence),
        )
        == result
    )
    response = GenerationResponse(success=True, generation_outcome=result)
    assert (
        response.model_dump()["generation_outcome"]["generated_execution"]["result"]
        == "passed"
    )
    prose = outcome_markdown(result)
    assert (
        "case support-router v1" in prose
        and "Mocked:" in prose
        and "Untested:" in prose
    )
    assert "execution: not_run" not in prose
    assert "unverified" in execution_description(result)
    summary = build_qa_summary(evidence["manifest"]["qa_reports"], result)
    assert summary["status"] == "passed"
    assert "Controlled generated" in " ".join(summary["validation_scope"]["validated"])


@pytest.mark.parametrize(
    "defect",
    [
        "candidate",
        "artifact_sha",
        "case",
        "fixture",
        "dirty_source",
        "source_revision",
        "source_files",
        "dataset",
        "skipped_assertion",
        "duplicate_assertion",
        "partial_cells",
        "excluded_cells",
        "missing_controls",
        "derived_artifact",
        "case_config",
        "dependency",
    ],
)
def test_invalid_evidence_never_promotes_a_pass(evidence, defect):
    result = evidence["result"]
    if defect == "candidate":
        result.candidate_sha256 = "e" * 64
    elif defect == "artifact_sha":
        result.notebook_sha256 = "e" * 64
    elif defect == "case":
        result.case_id = "another-case"
    elif defect == "fixture":
        result.fixture = "handwritten-substitute"
    elif defect == "dirty_source":
        result.source_dirty = True
    elif defect == "source_revision":
        result.generator_revision = "e" * 40
    elif defect == "source_files":
        result.source_files_sha256 = {}
    elif defect == "dataset":
        evidence["dataset_sha256"] = "e" * 64
    elif defect == "skipped_assertion":
        result.assertions.pop()
    elif defect == "duplicate_assertion":
        result.assertions.append(result.assertions[0])
    elif defect == "partial_cells":
        result.completed_cells.pop()
    elif defect == "excluded_cells":
        result.excluded_cells["999"] = "silently skip a node"
    elif defect == "missing_controls":
        evidence["controls_verified"] = False
    elif defect == "derived_artifact":
        Path(result.derived_notebook_path).write_text("substitute")
    elif defect == "case_config":
        result.environment["case_specification"]["invocations"] = []
    elif defect == "dependency":
        result.environment["dependencies"] = {}
    qualified = outcome(evidence)
    assert qualified.generated_execution.result == "incomplete"
    assert qualified.usability == "unknown" and qualified.status == "unverified"


@pytest.mark.parametrize("change", ["edit", "order", "metadata"])
def test_modified_candidate_and_repair_invalidate_prior_pass(evidence, change):
    notebook = evidence["notebook"]
    if change == "edit":
        notebook.cells[-1].source += "\nchanged = True"
    elif change == "order":
        notebook.cells.reverse()
    else:
        notebook.cells[-1].metadata["changed"] = True
    assert outcome(evidence).generated_execution.result == "incomplete"
    original = qualify_execution(
        **{**evidence, "notebook": nbformat.reads(evidence["source_bytes"].decode(), 4)}
    )
    repaired = derive_generation_outcome(
        candidate_sha256="f" * 64, execution_evaluation=original
    )
    assert (
        repaired.generated_execution.result == "incomplete"
        and repaired.usability == "unknown"
    )


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("runtime", "failed"),
        ("wrong-route", "failed"),
        ("unreachable-tool", "failed"),
        ("nontermination", "failed"),
        ("dependency", "unavailable"),
        ("kernel", "unavailable"),
        ("isolation", "unavailable"),
        ("early_timeout", "incomplete"),
        ("cleanup", "incomplete"),
    ],
)
def test_failure_classification_preserves_pipeline(evidence, kind, expected):
    result = evidence["result"]
    result.status = "failed"
    if kind == "runtime":
        result.errors = [
            {"phase": "notebook_execution", "kernel_error_type": "RuntimeError"}
        ]
    elif kind in {"wrong-route", "unreachable-tool"}:
        result.assertions[0].passed = False
    elif kind == "nontermination":
        result.timed_out = True
        result.errors = [
            {"type": "CellTimeoutError", "derived_cell": {"role": "behavioral_probe"}}
        ]
    elif kind in {"dependency", "kernel"}:
        result.errors = [{"phase": "generation_or_setup", "type": "ImportError"}]
    elif kind == "isolation":
        result.errors = [
            {"phase": "isolation_setup_or_cleanup", "type": "RuntimeError"}
        ]
    elif kind == "early_timeout":
        result.timed_out = True
        result.observations = []
    else:
        result.cleanup_verified = False
    actual = outcome(evidence)
    assert actual.generated_execution.result == expected
    assert actual.pipeline == "completed"
    assert actual.usability == ("blocked" if expected == "failed" else "unknown")


def test_static_blocker_and_missing_static_are_independent(evidence):
    evidence["manifest"]["qa_reports"][0]["passed"] = False
    actual = outcome(evidence)
    assert (
        actual.static_qa == "failed" and actual.generated_execution.result == "passed"
    )
    assert actual.status == "blocked" and actual.usability == "blocked"
    evidence["manifest"]["qa_reports"] = []
    actual = outcome(evidence)
    assert (
        actual.generated_execution.result == "passed" and actual.usability == "unknown"
    )


def test_untrusted_results_and_unsupported_schemas(evidence):
    with pytest.raises(ValueError, match="trusted evaluator"):
        derive_generation_outcome(execution_evaluation={"result": "passed"})
    raw = evidence["result"].model_dump()
    raw["schema_version"] = 99
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(raw)
    # Receipt JSON loses the parent-only capability even when all fields look valid.
    raw["schema_version"] = 1
    injected = {**evidence, "result": ExecutionResult.model_validate(raw)}
    assert qualify_execution(**injected).summary.result == "incomplete"
    for payload in ({}, {"generation_outcome": {"schema_version": 99}}):
        before = copy.deepcopy(payload)
        result = read_generation_outcome(payload)
        assert (
            result.schema_version == 1
            and result.generated_execution.result == "not_run"
        )
        assert payload == before


@pytest.mark.parametrize(
    "field", ["receipt_sha256", "receipt_reference", "candidate_sha256"]
)
def test_reader_never_trusts_injected_or_changed_v2_json(evidence, field):
    qualified = qualify_execution(**evidence)
    payload = outcome(evidence).model_dump(mode="json")
    # Even intact serialized metadata alone cannot recreate runner authority.
    assert (
        read_generation_outcome({"generation_outcome": payload}).usability == "unknown"
    )
    payload["generated_execution"][field] = "f" * 64
    read = read_generation_outcome(
        {"generation_outcome": payload}, execution_evaluation=qualified
    )
    assert read.generated_execution.result != "passed" and read.usability == "unknown"


@pytest.mark.parametrize("kind", ["TypeError", "AttributeError", "CellTimeoutError"])
def test_pregraph_kernel_failure_remains_incomplete(evidence, kind):
    result = evidence["result"]
    result.status = "failed"
    result.observations = []
    result.errors = [
        {
            "phase": "notebook_execution",
            "kernel_error_type": kind,
            "type": kind,
            "derived_cell": {"role": "original", "section": "config"},
        }
    ]
    result.timed_out = kind == "CellTimeoutError"
    assert outcome(evidence).generated_execution.result == "incomplete"


def test_first_generated_node_exception_is_observed_before_any_update(evidence):
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph_system_generator.qa.execution_models import AssertionResult
    from langgraph_system_generator.qa.execution_probe import probe

    def broken_node(state):
        raise RuntimeError("synthetic first node failure")

    builder = StateGraph(dict)
    builder.add_node("router", broken_node)
    builder.add_edge(START, "router")
    builder.add_edge("router", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    observed = probe(
        {
            "graph": graph,
            "RUN_INTERACTIVE_LOOP": False,
            "CANONICAL_GRAPH_SPEC": {"nodes": [{"name": "router"}]},
        },
        evidence["case"].model_dump(mode="json"),
    )
    assert observed["observations"][0]["phase"] == "graph_invocation_started"
    assert observed["observations"][0]["nodes"] == []
    assert observed["observations"][0]["error_type"] == "RuntimeError"
    result = evidence["result"]
    result.status = "failed"
    result.observations = observed["observations"]
    result.assertions = [
        AssertionResult.model_validate(item) for item in observed["assertions"]
    ]
    assert outcome(evidence).generated_execution.result == "failed"


def test_reader_rederives_static_blockers_with_valid_execution(evidence):
    evidence["manifest"]["qa_reports"][0]["passed"] = False
    qualified = qualify_execution(**evidence)
    payload = outcome(evidence).model_dump(mode="json")
    payload.update(
        static_qa="passed",
        blocking_count=0,
        status="completed",
        usability="no_known_blockers",
    )
    read = read_generation_outcome(
        {
            "generation_outcome": payload,
            "qa_reports": evidence["manifest"]["qa_reports"],
        },
        execution_evaluation=qualified,
    )
    assert read.static_qa == "failed" and read.usability == "blocked"


@pytest.mark.parametrize(
    "artifact", ["fixture-manifest.json", "generated/generated_cells.json"]
)
def test_source_metadata_changes_after_execution_are_rejected(
    evidence, tmp_path, artifact
):
    (tmp_path / artifact).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after execution"):
        build_evaluated_bundle(
            evidence["case"],
            evidence["result"],
            tmp_path,
            provenance=evidence["provenance"],
            dataset_sha256=DATASET_SHA256,
            controls_verified=True,
        )


def test_inconsistent_and_stale_failure_models_are_rejected(evidence):
    from langgraph_system_generator.generator.outcome_models import GenerationOutcomeV2

    payload = outcome(evidence).model_dump(mode="json")
    payload["generated_execution"].update(
        result="failed", failure_classification="environment"
    )
    with pytest.raises(ValidationError, match="classification"):
        GenerationOutcomeV2.model_validate(payload)
    payload["generated_execution"].update(failure_classification="generated_behavior")
    with pytest.raises(ValidationError, match="blocking"):
        GenerationOutcomeV2.model_validate(payload)
    payload.update(status="blocked", usability="blocked", blocking_count=1)
    payload["generated_execution"]["candidate_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="another candidate"):
        GenerationOutcomeV2.model_validate(payload)


def test_api_request_cannot_supply_execution_results():
    from langgraph_system_generator.api.server import GenerationRequest

    with pytest.raises(ValidationError, match="Extra inputs"):
        GenerationRequest.model_validate(
            {
                "prompt": "support",
                "generation_outcome": {
                    "schema_version": 2,
                    "generated_execution": {"result": "passed"},
                },
            }
        )


def test_qualification_refuses_dirty_or_custom_inputs_before_launch(
    tmp_path, monkeypatch
):
    import importlib.util

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "qualification_boundary", ROOT / "scripts/run_generated_notebook_eval.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(
        runner, "run_case", lambda *args: pytest.fail("kernel must not launch")
    )
    monkeypatch.setattr(runner, "source_provenance", lambda: {"source_dirty": True})
    with pytest.raises(ValueError, match="clean committed"):
        runner.run(DATASET, tmp_path, qualify_outcomes=True)
    monkeypatch.setattr(runner, "source_provenance", lambda: {"source_dirty": False})
    custom = DATASET.model_copy(deep=True)
    custom.cases[0].invocations[0].expected_nodes = ["handwritten_substitute"]
    with pytest.raises(ValueError, match="canonical dataset"):
        runner.run(custom, tmp_path, qualify_outcomes=True)
    with pytest.raises(ValueError, match="negative controls"):
        runner.run(DATASET, tmp_path, mutations=False, qualify_outcomes=True)


def test_new_bundle_preserves_original_and_has_no_hash_cycles(
    evidence, tmp_path, monkeypatch
):
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    original = (tmp_path / "generated/notebook.ipynb").read_bytes()
    source_manifest = (tmp_path / "fixture-manifest.json").read_bytes()
    result = build_evaluated_bundle(
        evidence["case"],
        evidence["result"],
        tmp_path,
        provenance=evidence["provenance"],
        dataset_sha256=DATASET_SHA256,
        controls_verified=True,
    )
    result = result.as_report()
    manifest = json.loads(Path(result["manifest"]).read_text())
    evaluated = tmp_path / "evaluated"
    assert (tmp_path / "generated/notebook.ipynb").read_bytes() == original
    assert (tmp_path / "fixture-manifest.json").read_bytes() == source_manifest
    assert (evaluated / "executed-source.ipynb").read_bytes() == original
    assert manifest["source_generation_outcome"]["schema_version"] == 1
    assert manifest["generation_outcome"]["generated_execution"]["result"] == "passed"
    assert manifest["source_artifact"]["notebook_sha256"] == digest(original)
    for entry in manifest["artifact_inventory"]:
        data = (evaluated / entry["path"]).read_bytes()
        assert digest(data) == entry["sha256"] and len(data) == entry["size_bytes"]
    assert "manifest.json" not in {
        entry["path"] for entry in manifest["artifact_inventory"]
    }
    notebook = nbformat.read(evaluated / "notebook.ipynb", 4)
    assert notebook_candidate_id(notebook) == evidence["result"].candidate_sha256
    assert "execution: passed" in notebook.cells[-1].source
    assert "execution: not_run" not in " ".join(cell.source for cell in notebook.cells)
    with zipfile.ZipFile(evaluated / "notebook_bundle.zip") as archive:
        assert "manifest.json" not in archive.namelist()
        assert notebook_candidate_id(
            nbformat.reads(archive.read("notebook.ipynb").decode(), 4)
        ) == notebook_candidate_id(notebook)
    receipt_bytes = Path(result["receipt"]).read_bytes()
    assert (
        digest(receipt_bytes)
        == manifest["generation_outcome"]["generated_execution"]["receipt_sha256"]
    )
    assert "prompt" not in json.loads(
        receipt_bytes
    ) and "observations" not in json.loads(receipt_bytes)
    with pytest.raises(FileExistsError):
        build_evaluated_bundle(
            evidence["case"],
            evidence["result"],
            tmp_path,
            provenance=evidence["provenance"],
            dataset_sha256=DATASET_SHA256,
            controls_verified=True,
        )
