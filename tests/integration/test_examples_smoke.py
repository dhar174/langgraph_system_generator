"""Smoke tests for runnable example scripts and notebooks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import nbformat
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"

SCRIPT_CASES = [
    "router_pattern_example.py",
    "subagents_pattern_example.py",
    "critique_revise_pattern_example.py",
    "hierarchical_teams_example.py",
    "planning_and_execute_example.py",
    "rewoo_example.py",
    "human_approval_pattern.py",
    "llm_judge_example.py",
    "llm_compiler_example.py",
]

NOTEBOOK_CASES = [
    "router_pattern_example.ipynb",
    "subagents_pattern_example.ipynb",
    "critique_revise_pattern_example.ipynb",
    "hierarchical_teams_example.ipynb",
    "planning_and_execute_example.ipynb",
    "rewoo_example.ipynb",
    "human_approval_pattern.ipynb",
    "llm_judge_example.ipynb",
    "llm_compiler_example.ipynb",
    "benchmark_critique_vs_judge.ipynb",
]


@pytest.mark.parametrize("script_name", SCRIPT_CASES)
def test_example_scripts_run_in_stub_mode(script_name: str):
    """Each runnable example should complete in deterministic stub mode."""
    command = [sys.executable, str(EXAMPLES_DIR / script_name), "--mode", "stub"]
    if script_name == "human_approval_pattern.py":
        command.extend(["--decision", "edit"])

    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert "[trace]" in completed.stdout
    assert "Final output" in completed.stdout or "Final route" in completed.stdout or "Approval status" in completed.stdout


@pytest.mark.parametrize("notebook_name", NOTEBOOK_CASES)
def test_example_notebooks_execute_in_stub_mode(notebook_name: str):
    """Notebook wrappers should execute top-to-bottom without network calls."""
    notebook_path = EXAMPLES_DIR / notebook_name
    with notebook_path.open("r", encoding="utf-8") as handle:
        notebook = nbformat.read(handle, as_version=4)

    namespace: dict[str, object] = {}
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        exec(compile(cell.source, str(notebook_path), "exec"), namespace, namespace)

    if notebook_name == "benchmark_critique_vs_judge.ipynb":
        rows = namespace["rows"]
        summary = namespace["summary"]
        assert summary["mode"] == "stub"
        assert summary["fixture_version"] == "1.0.0"
        assert summary["fixture_sha256"] == "802542a2164d794453a052f0f81785c72c0dc4109202039b24b1edaf9e05e269"
        assert summary["task_count"] == len(rows) == 3
        assert summary["starting_draft_points"] == 5
        assert summary["possible_points"] == 8
        assert summary["judge_flagged_tasks"] == 2
        assert all(row["llm_judge"]["artifact"] == row["starting_draft"] for row in rows)
        assert rows[0]["starting_draft"]["route"] == "specialist"
        assert rows[0]["critique_revise"]["artifact"]["route"] == "clarify"
        assert rows[1]["critique_revise"]["checks"] == {"steps": 1, "owner": 1, "status": 0}
        assert namespace["score_artifact"]({"count": True}, {"count": 1, "missing": 0}) == {
            "count": 0,
            "missing": 0,
        }
        for arm, points in (("critique_revise", 7), ("llm_judge", 5)):
            assert summary["arms"][arm] == {
                "points": points,
                "latency_seconds": None,
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
            }
        table = namespace["MARKDOWN_TABLE"]
        assert "| handoff-order | 1/3 | 2/3 | 1/3 | flag |" in table
        assert "| Critique-Revise | 7/8 | Unknown | Unknown | Unknown | Unknown |" in table
        assert "| LLM-as-a-Judge | 5/8 | Unknown | Unknown | Unknown | Unknown |" in table
        assert "Live performance is unmeasured." in table
    else:
        assert "RESULT" in namespace
        assert namespace["RESULT"]
