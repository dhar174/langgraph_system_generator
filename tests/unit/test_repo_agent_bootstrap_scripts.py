from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_SCRIPT = REPO_ROOT / ".github/skills/repo-agent-bootstrap/scripts/inventory_repo.py"
SCAFFOLD_SCRIPT = REPO_ROOT / ".github/skills/repo-agent-bootstrap/scripts/scaffold_agent_stack.py"
VALIDATE_SCRIPT = REPO_ROOT / ".github/skills/repo-agent-bootstrap/scripts/validate_agent_stack.py"


def test_repo_agent_bootstrap_scripts_scaffold_and_validate(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Temp Repo\n\nA Python API with tests and docs.\n\n```bash\npytest\nruff check .\nmypy .\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi\nruff\nmypy\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")

    inventory_result = subprocess.run(
        [sys.executable, str(INVENTORY_SCRIPT), "--repo-root", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    inventory = json.loads(inventory_result.stdout)
    assert inventory["repo_name"] == tmp_path.name
    assert "Python" in inventory["primary_languages"]

    subprocess.run(
        [
            sys.executable,
            str(SCAFFOLD_SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--generated-on",
            "2026-04-15",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".github" / "agents" / "repo-planner.agent.md").exists()

    validate_result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT), "--repo-root", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    report = json.loads(validate_result.stdout)
    assert report["is_valid"] is True
