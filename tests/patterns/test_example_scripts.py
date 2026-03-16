"""Smoke tests for the runnable pattern example scripts."""

from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("script_name", "expected_text"),
    [
        ("router_pattern_example.py", "Route selected:"),
        ("subagents_pattern_example.py", "Agent history:"),
        ("critique_revise_pattern_example.py", "Quality score:"),
    ],
)
def test_example_script_runs_in_stub_mode(script_name: str, expected_text: str) -> None:
    script_path = REPO_ROOT / "examples" / script_name

    completed = subprocess.run(
        [sys.executable, str(script_path), "--mode", "stub"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "Mode: stub" in completed.stdout
    assert expected_text in completed.stdout


@pytest.mark.parametrize(
    "script_name",
    [
        "router_pattern_example.py",
        "subagents_pattern_example.py",
        "critique_revise_pattern_example.py",
    ],
)
def test_example_script_requires_api_key_for_live_mode(script_name: str) -> None:
    script_path = REPO_ROOT / "examples" / script_name
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)

    completed = subprocess.run(
        [sys.executable, str(script_path), "--mode", "live"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    assert completed.returncode != 0
    assert "OPENAI_API_KEY is required" in (completed.stderr or completed.stdout)
