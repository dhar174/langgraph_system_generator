"""Tests for the local 1.0 release evaluation gate."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_release_evaluation_dataset_covers_core_generator_surfaces() -> None:
    dataset_path = REPO_ROOT / "tests" / "evaluation" / "release_1_0_eval_cases.json"
    assert dataset_path.exists()

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = payload["cases"]
    surfaces = {surface for case in cases for surface in case["surfaces"]}

    assert "architecture_selection" in surfaces
    assert "graph_design" in surfaces
    assert "notebook_composition" in surfaces
    assert "qa_repair" in surfaces
    assert "examples" in surfaces


def test_release_evaluation_gate_runs_locally_without_upload(tmp_path: Path) -> None:
    output_path = tmp_path / "release-eval-report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_release_eval.py",
            "--no-upload",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["upload"] == "disabled"
    assert report["summary"]["failed"] == 0
    assert report["summary"]["total"] >= 5


def test_release_evaluation_gate_can_mark_langsmith_upload_requested(tmp_path: Path) -> None:
    output_path = tmp_path / "release-eval-report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_release_eval.py",
            "--upload-langsmith",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["upload"] == "requested"
    assert report["summary"]["failed"] == 0
