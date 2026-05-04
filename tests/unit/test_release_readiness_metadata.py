"""Release-readiness metadata and workflow contract tests."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


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
        assert "Alpha" not in content
        assert "alpha" not in content


def test_diagram_workflow_uses_default_github_token_for_pr_creation() -> None:
    workflow = _read(".github/workflows/diagram.yml")

    assert "token: ${{ github.token }}" in workflow
    assert "secrets.GH_PAT" not in workflow
