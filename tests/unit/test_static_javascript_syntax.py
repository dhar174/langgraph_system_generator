"""Regression tests for browser static JavaScript parseability."""

import shutil
import subprocess
from pathlib import Path

import pytest


def _find_repo_root() -> Path:
    """Find the repository root from this test file."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "setup.py").exists() and (
            candidate / "src/langgraph_system_generator"
        ).is_dir():
            return candidate
    raise AssertionError("Repository root not found")


def test_web_ui_javascript_is_parseable():
    """Verify the web UI JavaScript bundle has no syntax errors."""
    node_path = shutil.which("node")
    if node_path is None:
        pytest.skip("node executable is required for JavaScript syntax validation")

    repo_root = _find_repo_root()
    app_js = repo_root / "src/langgraph_system_generator/api/static/app.js"
    result = subprocess.run(
        [node_path, "--check", str(app_js)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
