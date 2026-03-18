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
        assert "rows" in namespace
        assert namespace["rows"]
        assert "MARKDOWN_TABLE" in namespace
        assert namespace["MARKDOWN_TABLE"]
        assert "summary" in namespace
        assert namespace["summary"]
    else:
        assert "RESULT" in namespace
        assert namespace["RESULT"]
