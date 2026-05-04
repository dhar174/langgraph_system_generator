"""Release-readiness metadata and workflow contract tests."""

from __future__ import annotations

import ast
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
ALPHA_RELEASE_STATUS = re.compile(
    r"(?:project|release|development)\s+status\s*[:=-]\s*alpha"
    r"|\balpha\s+(?:baseline|release|status)\b"
    r"|\bdevelopment status :: 3 - alpha\b",
    re.IGNORECASE,
)


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _setup_call_keywords() -> dict[str, ast.AST]:
    tree = ast.parse(_read("setup.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup":
            return {keyword.arg: keyword.value for keyword in node.keywords}
    raise AssertionError("setup.py does not call setup()")


def test_package_metadata_is_ready_for_1_0_release() -> None:
    keywords = _setup_call_keywords()

    assert ast.literal_eval(keywords["version"]) == "1.0.0"
    assert ast.literal_eval(keywords["license"]) == "MIT"
    assert (REPO_ROOT / "LICENSE").exists()
    assert (REPO_ROOT / "CHANGELOG.md").exists()

    classifiers = ast.literal_eval(keywords["classifiers"])
    assert "Development Status :: 5 - Production/Stable" in classifiers
    assert "Development Status :: 3 - Alpha" not in classifiers

    init_version = _read("src/langgraph_system_generator/__init__.py")
    assert '__version__ = "1.0.0"' in init_version


def test_public_docs_no_longer_describe_release_as_alpha() -> None:
    checked_paths = [
        "README.md",
        "docs/wiki/README.md",
        "docs/wiki/Home.md",
        "memory-bank/progress.md",
    ]

    for path in checked_paths:
        content = _read(path)
        assert "0.1.1" not in content
        assert ALPHA_RELEASE_STATUS.search(content) is None


def test_diagram_workflow_uses_pr_token_that_can_trigger_checks() -> None:
    workflow = _read(".github/workflows/diagram.yml")

    assert "token: ${{ secrets.GH_PAT }}" in workflow
    assert "token: ${{ github.token }}" not in workflow
    assert "steps.diagram-token.outputs.available == 'true'" in workflow
    assert "Skipping diagram refresh because secrets.GH_PAT is not configured" in workflow


def test_diagram_workflow_authenticates_checkout_before_diagram_generation() -> None:
    workflow = _read(".github/workflows/diagram.yml")

    token_check_index = workflow.index("- name: Check diagram PR token")
    checkout_index = workflow.index("- name: Checkout code")
    update_index = workflow.index("- name: Update diagram")

    assert token_check_index < checkout_index < update_index
    assert "if: steps.diagram-token.outputs.available == 'true'\n        uses: actions/checkout@v4" in workflow
    assert "token: ${{ secrets.GH_PAT }}" in workflow
    assert "persist-credentials: true" in workflow
    assert "Skipping diagram refresh because secrets.GH_PAT is not configured" in workflow
