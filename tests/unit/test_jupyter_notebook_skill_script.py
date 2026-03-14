from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / ".github/skills/jupyter-notebook/scripts/new_notebook.py"


def test_new_notebook_default_output_uses_current_working_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--kind",
            "experiment",
            "--title",
            "Compare prompt variants",
        ],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    output_path = tmp_path / "output" / "jupyter-notebook" / "compare-prompt-variants.ipynb"
    assert output_path.exists()
    assert str(output_path) in result.stdout

    notebook = json.loads(output_path.read_text(encoding="utf-8"))
    assert notebook["cells"][0]["source"][0] == "# Experiment: Compare prompt variants\n"
