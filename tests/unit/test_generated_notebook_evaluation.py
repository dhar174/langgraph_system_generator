"""Fail-closed receipt, dataset, identity and mutation contract checks."""

import copy
import json
from pathlib import Path

import nbformat
import pytest
from pydantic import ValidationError

from langgraph_system_generator.qa.execution_evaluation import mutate
from langgraph_system_generator.qa.execution_models import (
    ExecutionDataset,
    ExecutionResult,
)
from langgraph_system_generator.qa.outcomes import notebook_candidate_id

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_async_generation_fixture_is_a_real_graph_node():
    from unittest.mock import AsyncMock

    from langgraph.graph import END, START, StateGraph

    from langgraph_system_generator.qa.execution_fixtures import _async_fixture_node

    collaborator = AsyncMock(return_value={"docs_context": ["offline"]})
    builder = StateGraph(dict)
    builder.add_node("retrieval", _async_fixture_node(collaborator))
    builder.add_edge(START, "retrieval")
    builder.add_edge("retrieval", END)
    assert await builder.compile().ainvoke({"prompt": "support"}) == {
        "docs_context": ["offline"]
    }
    collaborator.assert_awaited_once_with({"prompt": "support"})


def test_dataset_requires_coverage_and_normal_composition():
    payload = json.loads(
        (ROOT / "tests/evaluation/generated_notebook_cases.json").read_text()
    )
    dataset = ExecutionDataset.model_validate(payload)
    assert len(dataset.cases) == 3
    assert len(dataset.cases[2].invocations) == 5
    payload["cases"][0]["id"] = payload["cases"][1]["id"]
    with pytest.raises(ValidationError, match="unique"):
        ExecutionDataset.model_validate(payload)


@pytest.mark.parametrize(
    "missing",
    [
        "observations",
        "assertions",
        "cleanup_verified",
        "candidate_sha256",
        "executed",
        "notebook_path",
        "notebook_sha256",
        "original_candidate_sha256",
        "source_tree_sha256",
        "source_files_sha256",
    ],
)
def test_pass_requires_actual_graph_evidence(missing):
    data = dict(  # noqa: C408 -- readable keyword fixture
        case_id="router",
        fixture="support-router-v1",
        generator_revision="a" * 40,
        source_dirty=False,
        source_diff_sha256="0" * 64,
        status="passed",
        observations=[{"nodes": ["router"]}],
        assertions=[{"name": "graph", "passed": True}],
        cleanup_verified=True,
        candidate_sha256="1" * 64,
        executed=["LangGraph"],
        notebook_path="fixture.ipynb",
        notebook_sha256="2" * 64,
        original_candidate_sha256="1" * 64,
        source_tree_sha256="3" * 64,
        source_files_sha256={"fixture.py": "4" * 64},
    )
    data[missing] = (
        False
        if missing == "cleanup_verified"
        else None if missing == "candidate_sha256" else []
    )
    with pytest.raises(ValidationError):
        ExecutionResult.model_validate(data)


def test_mutation_preserves_original_and_source_identity_ignores_outputs():
    original = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(
                'def router_node(state):\n    return {"route": decision.route}'
            )
        ]
    )
    identity = notebook_candidate_id(original)
    mutant = copy.deepcopy(original)
    mutate(mutant, "wrong-route")
    assert notebook_candidate_id(original) == identity
    assert notebook_candidate_id(mutant) != identity
    original.cells[0].execution_count = 1
    original.cells[0].outputs = [
        nbformat.v4.new_output("stream", name="stdout", text="executed")
    ]
    assert notebook_candidate_id(original) == identity
    with pytest.raises(ValueError, match="site not found"):
        mutate(original, "unreachable-tool")


def test_tool_codegen_requires_explicit_executable_contract():
    from langgraph_system_generator.notebook.tool_execution import (
        chatbot_tool_node_code,
    )

    assert (
        chatbot_tool_node_code({"name": "chat", "role": "assistant"}, {}, "chat_node")
        is None
    )


def test_output_root_rejects_traversal_and_existing_evidence(tmp_path, monkeypatch):
    import importlib.util

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "notebook_eval_runner", ROOT / "scripts/run_generated_notebook_eval.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        runner.output_root(tmp_path / ".." / "outside")
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="empty"):
        runner.output_root(existing)


def test_negative_control_rejects_unrelated_setup_failure(tmp_path, monkeypatch):
    import importlib.util

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "eval_negative_gate", ROOT / "scripts/run_generated_notebook_eval.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    clean = ExecutionResult(
        case_id="case",
        fixture="support-router-v1",
        generator_revision="a" * 40,
        source_dirty=False,
        source_diff_sha256="0" * 64,
        candidate_sha256="1" * 64,
        observations=[{"nodes": ["router"]}],
        assertions=[{"name": "compiled_graph", "passed": True}],
        executed=["LangGraph"],
        notebook_path="fixture.ipynb",
        notebook_sha256="2" * 64,
        original_candidate_sha256="1" * 64,
        source_tree_sha256="3" * 64,
        source_files_sha256={"fixture.py": "4" * 64},
        cleanup_verified=True,
        status="passed",
    )
    mutant = clean.model_copy(deep=True)
    mutant.status = "failed"
    mutant.mutation = "wrong-route"
    mutant.mutation_applied = True
    mutant.original_candidate_sha256 = clean.candidate_sha256
    mutant.candidate_sha256 = "2" * 64
    mutant.errors = [{"phase": "isolation_setup_or_cleanup", "type": "RuntimeError"}]
    assert not runner.mutation_detected(clean, mutant)
    mutant.mutation = "nontermination"
    mutant.timed_out = True
    mutant.errors = [{"phase": "supervision", "type": "OverallTimeout"}]
    assert not runner.mutation_detected(clean, mutant)


def test_observed_detached_process_is_killed_and_reaped(monkeypatch):
    import importlib.util
    import os
    import subprocess
    import sys
    import time

    import psutil

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "eval_cleanup", ROOT / "scripts/run_generated_notebook_eval.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=os.name != "nt",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        observed = psutil.Process(process.pid)
        runner.stop_observed_descendants(
            {(observed.pid, observed.create_time()): observed}
        )
        # psutil may reap first on POSIX, so Popen cannot recover the exit code.
        # Prove the 60-second sleeper is gone promptly rather than guessing it.
        process.wait(timeout=5)
        assert not observed.is_running()
        assert time.monotonic() - started < 10
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_open_output_pipe_cannot_claim_verified_cleanup(tmp_path, monkeypatch):
    import importlib.util
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "eval_pipe_cleanup", ROOT / "scripts/run_generated_notebook_eval.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    process = SimpleNamespace(poll=lambda: 0, returncode=0)

    class Scope:
        job = None

        def start(self, *args, **kwargs):
            return process

        def stop(self, process):
            pass

    cleanup_calls = []
    monkeypatch.setattr(runner, "ProcessScope", Scope)
    monkeypatch.setattr(runner, "configure_limits", lambda *args: {})
    monkeypatch.setattr(
        runner, "stop_observed_descendants", lambda values: cleanup_calls.append(True)
    )
    monkeypatch.setattr(
        runner.threading,
        "Thread",
        lambda **kwargs: SimpleNamespace(
            start=lambda: None, join=lambda **kwargs: None, is_alive=lambda: True
        ),
    )
    dataset = ExecutionDataset.model_validate_json(
        (ROOT / "tests/evaluation/generated_notebook_cases.json").read_text()
    )
    result = runner.run_case(
        dataset.cases[0],
        tmp_path,
        {
            "generator_revision": "a" * 40,
            "source_dirty": False,
            "source_diff_sha256": "0" * 64,
        },
    )
    assert result.status == "failed"
    assert not result.cleanup_verified
    assert len(cleanup_calls) >= 2
    assert any(
        "pipe did not close" in error.get("message", "") for error in result.errors
    )
