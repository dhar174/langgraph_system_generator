"""Execute actual normal-composition artifacts and all four negative controls."""

import json
import os
import subprocess
import sys
from pathlib import Path

import nbformat

from langgraph_system_generator.qa.outcomes import notebook_candidate_id

ROOT = Path(__file__).resolve().parents[2]


def test_generated_graphs_and_negative_controls(tmp_path):
    env = {
        **os.environ,
        "BASE_OUTPUT_DIR": str(tmp_path),
        "PYTHON_DOTENV_DISABLED": "1",
    }
    output = tmp_path / "evaluation"
    process = subprocess.run(
        [
            sys.executable,
            "scripts/run_generated_notebook_eval.py",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=900,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["passed"]
    assert not report["skipped"]
    assert len(report["cases"]) == 3
    assert len(report["negative_controls"]) == 4
    for result in report["cases"]:
        original = Path(result["notebook_path"])
        nb = nbformat.read(original, as_version=4)
        nbformat.validate(nb)
        assert result["candidate_sha256"] == notebook_candidate_id(nb)
        assert result["status"] == "passed"
        assert result["cleanup_verified"]
        assert result["attempted_cells"] == result["completed_cells"]
        assert result["observations"]
        assert all(item["passed"] for item in result["assertions"])
        assert result["excluded_cells"]
    for control in report["negative_controls"]:
        assert control["detected"]
        result = control["result"]
        clean = next(
            item for item in report["cases"] if item["case_id"] == result["case_id"]
        )
        assert result["original_candidate_sha256"] == clean["candidate_sha256"]
        assert result["candidate_sha256"] != clean["candidate_sha256"]
        assert result["cleanup_verified"]
        assert result["errors"] or any(
            not item["passed"] for item in result["assertions"]
        )
    controls = {
        item["mutation"]: item["result"] for item in report["negative_controls"]
    }
    assert controls["runtime-failure"]["errors"][0]["type"] == "CellExecutionError"
    assert any(
        item["name"].endswith("executed_nodes") and not item["passed"]
        for item in controls["wrong-route"]["assertions"]
    )
    assert any(
        item["name"].endswith("actual_tool_executions") and not item["passed"]
        for item in controls["unreachable-tool"]["assertions"]
    )
    assert controls["nontermination"]["timed_out"]
