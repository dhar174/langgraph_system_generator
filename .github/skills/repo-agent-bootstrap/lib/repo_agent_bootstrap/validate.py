from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from .models import ExternalSource, ValidationReport

REQUIRED_CORE_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    ".github/copilot-instructions.md",
    "docs/architecture.md",
    "docs/adr/0001-agent-stack-bootstrap.md",
    "plans/current-plan.md",
    "plans/runbook.md",
    "memory-bank/projectbrief.md",
    "memory-bank/productContext.md",
    "memory-bank/activeContext.md",
    "memory-bank/systemPatterns.md",
    "memory-bank/techContext.md",
    "memory-bank/progress.md",
    "memory-bank/tasks/_index.md",
]
ALLOWED_AGENT_KEYS = {
    "name",
    "description",
    "target",
    "tools",
    "model",
    "disable-model-invocation",
    "user-invocable",
    "infer",
    "metadata",
    "mcp-servers",
}


def validate_generated_stack(repo_root: Path) -> ValidationReport:
    """Validate the generated bootstrap stack in a repository."""

    repo_root = repo_root.resolve()
    report = ValidationReport()

    for relative_path in REQUIRED_CORE_FILES:
        if not (repo_root / relative_path).exists():
            report.add_error(f"Missing required bootstrap file: {relative_path}", path=relative_path)

    agents_dir = repo_root / ".github" / "agents"
    agent_files = sorted(agents_dir.glob("*.agent.md"))
    if not agent_files:
        report.add_error("Expected at least one custom agent file under .github/agents/", path=".github/agents")

    for path in agent_files:
        _validate_agent_file(path, repo_root, report)

    provenance_path = repo_root / ".github" / "agent-stack-provenance.json"
    if provenance_path.exists():
        _validate_provenance_file(provenance_path, repo_root, report)

    return report


def validate_external_sources(sources: list[ExternalSource]) -> ValidationReport:
    """Validate that imported third-party sources are pinned and attributable."""

    report = ValidationReport()
    for source in sources:
        revision = source.revision.strip()
        if not revision or revision.lower() in {"main", "master", "latest", "head"}:
            report.add_error(
                f"External source '{source.name}' must use a pinned commit SHA or version tag.",
                path=source.url,
            )
        if not source.license.strip():
            report.add_error(
                f"External source '{source.name}' is missing license metadata.",
                path=source.url,
            )
        if not source.path.strip():
            report.add_error(
                f"External source '{source.name}' is missing the original source path.",
                path=source.url,
            )
    return report


def _validate_agent_file(path: Path, repo_root: Path, report: ValidationReport) -> None:
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    relative_path = path.relative_to(repo_root).as_posix()

    if not frontmatter:
        report.add_error("Agent file is missing YAML frontmatter.", path=relative_path)
        return

    missing = {"description", "tools"} - frontmatter.keys()
    if missing:
        report.add_error(
            f"Agent file is missing required frontmatter keys: {sorted(missing)}.",
            path=relative_path,
        )

    unexpected = set(frontmatter) - ALLOWED_AGENT_KEYS
    if unexpected:
        report.add_warning(
            f"Agent file uses unexpected frontmatter keys: {sorted(unexpected)}.",
            path=relative_path,
        )

    tools_value = frontmatter.get("tools", "")
    try:
        parsed_tools = ast.literal_eval(tools_value)
    except (SyntaxError, ValueError):
        report.add_error("Agent tools must parse as a list.", path=relative_path)
        return

    if not isinstance(parsed_tools, list):
        report.add_error("Agent tools must parse as a list.", path=relative_path)
        return

    normalized_tools = {str(tool).lower() for tool in parsed_tools}
    if "custom-agent" not in normalized_tools and "agent" not in normalized_tools and "task" not in normalized_tools:
        report.add_error(
            "Agent tools must include the delegation alias (`custom-agent`, `agent`, or `Task`).",
            path=relative_path,
        )
    if not {"read", "search"} & normalized_tools:
        report.add_warning(
            "Agent should expose at least one repo-inspection tool (`read` or `search`).",
            path=relative_path,
        )


def _validate_provenance_file(path: Path, repo_root: Path, report: ValidationReport) -> None:
    relative_path = path.relative_to(repo_root).as_posix()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.add_error(f"Provenance JSON could not be parsed: {exc}", path=relative_path)
        return

    sources = [ExternalSource(**item) for item in payload.get("externalSources", [])]
    source_report = validate_external_sources(sources)
    report.errors.extend(source_report.errors)
    report.warnings.extend(source_report.warnings)


def _parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return {}

    end_index = lines[1:].index("---") + 1
    frontmatter_lines = lines[1:end_index]
    data: dict[str, str] = {}
    for line in frontmatter_lines:
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            key, value = match.groups()
            data[key] = value
    return data
