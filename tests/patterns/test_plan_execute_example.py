"""Focused tests for the runnable plan-and-execute example."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import nbformat


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "examples" / "planning_and_execute_example.py"
NOTEBOOK_PATH = REPO_ROOT / "examples" / "planning_and_execute_example.ipynb"


def _load_example_module():
    spec = importlib.util.spec_from_file_location(
        "planning_and_execute_example", MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_demo_stub_respects_max_steps_and_emits_trace():
    module = _load_example_module()

    result = module.run_demo(
        "Explain when planner and executor prompts should differ.",
        mode="stub",
        max_steps=2,
    )

    assert len(result["plan_steps"]) == 2
    assert all(step["step_id"] for step in result["plan_steps"])
    assert all(step["objective"] for step in result["plan_steps"])
    assert result["execution_trace"][0] == "Planner created 2 steps."
    assert any(
        "Orchestrator dispatched step 1" in entry
        for entry in result["execution_trace"]
    )
    assert "frame_problem" in result["final_output"]
    assert "collect_evidence" in result["final_output"]
    assert "synthesize_answer" not in result["final_output"]


def test_build_graph_uses_separate_live_models(monkeypatch):
    module = _load_example_module()
    created_models: list[tuple[str, int]] = []

    class FakeChatOpenAI:
        def __init__(self, model: str, temperature: int = 0):
            created_models.append((model, temperature))

    monkeypatch.setattr(module, "ChatOpenAI", FakeChatOpenAI)

    module.build_graph(
        "live",
        "fallback-model",
        planner_model="planner-model",
        executor_model="executor-model",
    )

    assert created_models == [
        ("planner-model", 0),
        ("executor-model", 0),
    ]


def test_plan_execute_notebook_includes_walkthrough_and_live_setup():
    with NOTEBOOK_PATH.open("r", encoding="utf-8") as handle:
        notebook = nbformat.read(handle, as_version=4)

    markdown = "\n\n".join(
        "".join(cell.source) for cell in notebook.cells if cell.cell_type == "markdown"
    )
    code = "\n\n".join(
        "".join(cell.source) for cell in notebook.cells if cell.cell_type == "code"
    )

    assert "Walkthrough" in markdown
    assert "OPENAI_API_KEY" in markdown
    assert "execution trace" in markdown.lower()
    assert "PLANNER_MODEL = MODEL" in code
    assert "EXECUTOR_MODEL = MODEL" in code
    assert "PlanStep.model_validate" in code
