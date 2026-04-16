from __future__ import annotations

from pathlib import Path

from langgraph_system_generator.repo_agent_bootstrap import (
    ExternalSource,
    build_bootstrap_files,
    build_repo_profile,
    merge_managed_text,
    wrap_managed_block,
)
from langgraph_system_generator.repo_agent_bootstrap.validate import validate_external_sources


def test_build_repo_profile_detects_python_repo_commands(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example Repo\n\nA Python service for validating customer documents.\n\n```bash\npython -m pytest\nruff check .\nmypy .\nuvicorn example:app --reload\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi\nruff\nmypy\n", encoding="utf-8")
    (tmp_path / "setup.py").write_text("from setuptools import setup\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / ".github" / "skills" / "foo").mkdir(parents=True)
    (tmp_path / ".github" / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\ndescription: bar\n---\n", encoding="utf-8")

    profile = build_repo_profile(tmp_path)

    assert profile.repo_name == tmp_path.name
    assert "Python" in profile.primary_languages
    assert "FastAPI" in profile.frameworks
    assert profile.commands["install"] == "pip install -r requirements.txt"
    assert profile.commands["test"] == "python -m pytest"
    assert profile.commands["lint"] == "ruff check ."
    assert profile.commands["typecheck"] == "mypy ."
    assert any("AI assets" in workflow or "skills" in workflow for workflow in profile.major_workflows)


def test_build_repo_profile_detects_node_commands_from_package_json(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Web Repo\n\nA web app for collaborative editing.\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts":{"dev":"vite","test":"vitest","lint":"eslint .","typecheck":"tsc --noEmit"}}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "src").mkdir()

    profile = build_repo_profile(tmp_path)

    assert "JavaScript" in profile.primary_languages or "TypeScript" in profile.primary_languages
    assert profile.commands["install"] == "npm install"
    assert profile.commands["dev"] == "npm run dev"
    assert profile.commands["test"] == "npm run test"


def test_merge_managed_text_preserves_user_content() -> None:
    existing = "User note before.\n\n" + wrap_managed_block(
        "# Old body", file_kind="agents-md", provenance="repo-agent-bootstrap@2026-01-01"
    ) + "\nUser note after.\n"
    incoming = wrap_managed_block(
        "# New body", file_kind="agents-md", provenance="repo-agent-bootstrap@2026-04-15"
    )

    merged = merge_managed_text(existing, incoming)

    assert "User note before." in merged
    assert "User note after." in merged
    assert "# New body" in merged
    assert "# Old body" not in merged


def test_build_bootstrap_files_renders_core_outputs_and_agents(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example Repo\n\nA Python API with docs and tests.\n\n```bash\npytest\nruff check .\nmypy .\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi\nruff\nmypy\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")

    profile = build_repo_profile(tmp_path)
    rendered = build_bootstrap_files(profile, generated_on="2026-04-15")

    assert "AGENTS.md" in rendered
    assert ".github/copilot-instructions.md" in rendered
    assert "memory-bank/projectbrief.md" in rendered
    assert ".github/agent-stack-provenance.json" in rendered

    agent_paths = [path for path in rendered if path.startswith(".github/agents/")]
    assert agent_paths
    assert any("repo-planner.agent.md" in path for path in agent_paths)
    assert any('"custom-agent"' in rendered[path] for path in agent_paths)
    assert all("disable-model-invocation" in rendered[path] for path in agent_paths)


def test_validate_external_sources_requires_pinned_revision_and_license() -> None:
    report = validate_external_sources(
        [
            ExternalSource(
                name="bad-source",
                url="https://example.com/repo",
                revision="main",
                path="skills/foo/SKILL.md",
                license="",
                reason="Testing",
            )
        ]
    )

    assert not report.is_valid
    messages = [issue.message for issue in report.errors]
    assert any("pinned commit SHA or version tag" in message for message in messages)
    assert any("missing license metadata" in message for message in messages)
