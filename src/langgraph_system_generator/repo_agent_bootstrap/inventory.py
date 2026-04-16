from __future__ import annotations

import json
import re
from pathlib import Path

from .models import RepoProfile

README_NAMES = ("README.md", "readme.md")
KNOWN_REPO_MAP = {
    "src": "Primary application or package source.",
    "app": "Application entrypoints and composition root.",
    "packages": "Monorepo packages or shared modules.",
    "tests": "Automated validation and regression coverage.",
    "docs": "Deep reference docs, ADRs, and contributor guidance.",
    ".github": "Copilot assets, workflows, prompts, hooks, and repository automation.",
    "memory-bank": "Persistent AI project memory and resumable context.",
    "skills": "Codex-discoverable mirrored skills or local reusable workflows.",
    "scripts": "Repository automation and operational helpers.",
}
AI_ASSET_GLOBS = {
    "agents_md": ["AGENTS.md", "**/AGENTS.md"],
    "claude_md": ["CLAUDE.md"],
    "copilot_instructions": [".github/copilot-instructions.md"],
    "path_instructions": [".github/instructions/**/*.instructions.md"],
    "custom_agents": [".github/agents/*.agent.md"],
    "repo_skills": [".github/skills/*/SKILL.md"],
    "mirrored_skills": ["skills/*/SKILL.md"],
    "hooks": [".github/hooks/**/*.json"],
    "prompt_files": [".github/prompts/*.prompt.md"],
}


def build_repo_profile(repo_root: Path) -> RepoProfile:
    """Create a best-effort profile from repository documentation and manifests."""

    repo_root = repo_root.resolve()
    readme_path = _first_existing(repo_root, README_NAMES)
    agents_path = repo_root / "AGENTS.md"
    readme_text = _read_text(readme_path)
    agents_text = _read_text(agents_path)
    projectbrief_text = _read_text(repo_root / "memory-bank" / "projectbrief.md")

    purpose = (
        _extract_first_paragraph(readme_text)
        or _extract_first_paragraph(projectbrief_text)
        or f"{repo_root.name} repository"
    )

    primary_languages = _detect_primary_languages(repo_root, readme_text)
    frameworks = _detect_frameworks(repo_root, readme_text)
    package_managers = _detect_package_managers(repo_root)
    commands = _detect_commands(repo_root, readme_text, package_managers)
    repo_map = _build_repo_map(repo_root)
    high_signal_files = _high_signal_files(repo_root)
    source_documents = [path for path in high_signal_files if path.endswith(".md")]
    if readme_path:
        source_documents.insert(0, readme_path.relative_to(repo_root).as_posix())
    source_documents = _dedupe(source_documents)

    existing_ai_assets = _discover_ai_assets(repo_root)
    ci_files = existing_ai_assets.get("workflows", [])
    major_workflows = _infer_major_workflows(
        repo_root=repo_root,
        readme_text=readme_text,
        primary_languages=primary_languages,
        repo_map=repo_map,
        existing_ai_assets=existing_ai_assets,
    )
    risky_boundaries = _infer_risky_boundaries(repo_root, agents_text)

    return RepoProfile(
        repo_name=repo_root.name,
        repo_root=repo_root.as_posix(),
        purpose=purpose,
        primary_languages=primary_languages,
        frameworks=frameworks,
        package_managers=package_managers,
        commands=commands,
        repo_map=repo_map,
        high_signal_files=high_signal_files,
        major_workflows=major_workflows,
        risky_boundaries=risky_boundaries,
        ci_files=ci_files,
        source_documents=source_documents,
        existing_ai_assets=existing_ai_assets,
    )


def _first_existing(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def _read_text(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _extract_first_paragraph(text: str) -> str:
    if not text:
        return ""

    paragraphs = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith("#") or line.startswith("![") or line.startswith("[!["):
            continue
        if re.fullmatch(r"[-*_`]+", line) or line.startswith(">"):
            continue
        current.append(line)

    if current:
        paragraphs.append(" ".join(current))

    for paragraph in paragraphs:
        cleaned = re.sub(r"`([^`]+)`", r"\1", paragraph)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned).strip()
        if len(cleaned) >= 40:
            return cleaned
    return paragraphs[0] if paragraphs else ""


def _detect_primary_languages(repo_root: Path, readme_text: str) -> list[str]:
    matches: list[str] = []
    lower_readme = readme_text.lower()
    if (repo_root / "package.json").exists():
        package_json_text = _read_text(repo_root / "package.json").lower()
        if "typescript" in package_json_text or "tsc" in package_json_text:
            matches.append("TypeScript")
        else:
            matches.append("JavaScript")
    if any(repo_root.glob("**/*.py")) or "python" in lower_readme or (repo_root / "setup.py").exists():
        matches.append("Python")
    if any(repo_root.glob("**/*.ts")) or "typescript" in lower_readme:
        matches.append("TypeScript")
    if any(repo_root.glob("**/*.tsx")) or "react" in lower_readme:
        matches.append("TSX")
    if any(repo_root.glob("**/*.js")) or "javascript" in lower_readme:
        matches.append("JavaScript")
    if any(repo_root.glob("**/*.rs")) or (repo_root / "Cargo.toml").exists():
        matches.append("Rust")
    if any(repo_root.glob("**/*.go")) or (repo_root / "go.mod").exists():
        matches.append("Go")
    if not matches:
        matches.append("Unknown")
    return _dedupe(matches)


def _detect_frameworks(repo_root: Path, readme_text: str) -> list[str]:
    frameworks: list[str] = []
    lower = readme_text.lower()
    requirements_text = _read_text(repo_root / "requirements.txt").lower()
    if "langgraph" in lower or "langgraph" in requirements_text:
        frameworks.append("LangGraph")
    if "langchain" in lower or "langchain" in requirements_text:
        frameworks.append("LangChain")
    if "fastapi" in lower or "fastapi" in requirements_text:
        frameworks.append("FastAPI")
    if "react" in lower:
        frameworks.append("React")
    if "next.js" in lower or "nextjs" in lower:
        frameworks.append("Next.js")
    if "pytest" in lower or (repo_root / "pytest.ini").exists():
        frameworks.append("pytest")
    if "ruff" in lower or (repo_root / "ruff.toml").exists():
        frameworks.append("Ruff")
    return _dedupe(frameworks)


def _detect_package_managers(repo_root: Path) -> list[str]:
    managers: list[str] = []
    if (repo_root / "pnpm-lock.yaml").exists():
        managers.append("pnpm")
    if (repo_root / "package-lock.json").exists():
        managers.append("npm")
    if (repo_root / "yarn.lock").exists():
        managers.append("yarn")
    if (repo_root / "bun.lockb").exists() or (repo_root / "bun.lock").exists():
        managers.append("bun")
    if (repo_root / "uv.lock").exists():
        managers.append("uv")
    if (repo_root / "poetry.lock").exists():
        managers.append("poetry")
    if (repo_root / "requirements.txt").exists() or (repo_root / "setup.py").exists():
        managers.append("pip")
    return _dedupe(managers)


def _detect_commands(repo_root: Path, readme_text: str, package_managers: list[str]) -> dict[str, str]:
    commands: dict[str, str] = {}
    package_manager = package_managers[0] if package_managers else None

    if (repo_root / "package.json").exists():
        package_json = json.loads((repo_root / "package.json").read_text(encoding="utf-8"))
        scripts = package_json.get("scripts", {})
        if package_manager:
            if "dev" in scripts:
                commands["dev"] = _wrap_package_manager_command(package_manager, "dev")
            if "test" in scripts:
                commands["test"] = _wrap_package_manager_command(package_manager, "test")
            if "lint" in scripts:
                commands["lint"] = _wrap_package_manager_command(package_manager, "lint")
            if "typecheck" in scripts:
                commands["typecheck"] = _wrap_package_manager_command(package_manager, "typecheck")
            commands["install"] = _wrap_install_command(package_manager)

    readme_commands = {
        "install": _extract_command_from_markdown(readme_text, ["install", "sync"]),
        "dev": _extract_command_from_markdown(readme_text, ["dev", "uvicorn", "serve", "start"]),
        "test": _extract_command_from_markdown(readme_text, ["pytest", "test"]),
        "lint": _extract_command_from_markdown(readme_text, ["ruff", "flake8", "eslint", "lint"]),
        "typecheck": _extract_command_from_markdown(readme_text, ["mypy", "pyright", "typecheck"]),
    }
    for key, value in readme_commands.items():
        if value and key not in commands:
            commands[key] = value

    if "install" not in commands:
        if "uv" in package_managers:
            commands["install"] = "uv sync"
        elif "poetry" in package_managers:
            commands["install"] = "poetry install"
        elif "pip" in package_managers and (repo_root / "requirements.txt").exists():
            commands["install"] = "pip install -r requirements.txt"

    if "test" not in commands and ((repo_root / "pytest.ini").exists() or (repo_root / "tests").exists()):
        commands["test"] = "pytest"

    requirements_text = _read_text(repo_root / "requirements.txt").lower()
    if "lint" not in commands:
        if (repo_root / "ruff.toml").exists() or "ruff" in requirements_text:
            commands["lint"] = "ruff check ."
        elif "flake8" in requirements_text:
            commands["lint"] = "flake8 ."

    if "typecheck" not in commands:
        if "mypy" in requirements_text:
            commands["typecheck"] = "mypy ."
        elif (repo_root / "pyrightconfig.json").exists():
            commands["typecheck"] = "pyright"

    if "dev" not in commands and "FastAPI" in _detect_frameworks(repo_root, readme_text):
        commands["dev"] = "uvicorn app:app --reload"

    return commands


def _extract_command_from_markdown(text: str, keywords: list[str]) -> str:
    if not text:
        return ""

    code_lines = re.findall(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    flattened: list[str] = []
    for block in code_lines:
        for line in block.splitlines():
            candidate = line.strip()
            if candidate and not candidate.startswith("#"):
                flattened.append(candidate)

    for line in flattened:
        lower_line = line.lower()
        if "install" not in keywords and (
            lower_line.startswith("pip install")
            or lower_line.startswith("python -m pip install")
            or lower_line.startswith("npm install")
            or lower_line.startswith("pnpm install")
            or lower_line.startswith("yarn install")
            or lower_line.startswith("uv sync")
            or lower_line.startswith("poetry install")
        ):
            continue
        if any(keyword in lower_line for keyword in keywords):
            return line
    return ""


def _wrap_package_manager_command(package_manager: str, script_name: str) -> str:
    if package_manager in {"pnpm", "npm", "bun"}:
        return f"{package_manager} run {script_name}"
    if package_manager == "yarn":
        return f"yarn {script_name}"
    return script_name


def _wrap_install_command(package_manager: str) -> str:
    if package_manager in {"pnpm", "npm", "yarn", "bun"}:
        return f"{package_manager} install"
    if package_manager == "uv":
        return "uv sync"
    if package_manager == "poetry":
        return "poetry install"
    return "pip install -r requirements.txt"


def _build_repo_map(repo_root: Path) -> dict[str, str]:
    repo_map: dict[str, str] = {}
    for name, description in KNOWN_REPO_MAP.items():
        if (repo_root / name).exists():
            repo_map[name] = description
    for child in sorted(repo_root.iterdir()):
        if child.name.startswith(".") or child.name in repo_map:
            continue
        if child.is_dir() and child.name not in {"__pycache__", ".pytest_cache", ".venv"}:
            repo_map[child.name] = "Project-specific directory that should be inspected before large changes."
        if len(repo_map) >= 10:
            break
    return repo_map


def _high_signal_files(repo_root: Path) -> list[str]:
    candidates = [
        "README.md",
        "AGENTS.md",
        ".github/copilot-instructions.md",
        "CLAUDE.md",
        "setup.py",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "pytest.ini",
        ".github/workflows/python-app.yml",
        "memory-bank/projectbrief.md",
        "memory-bank/activeContext.md",
    ]
    return [candidate for candidate in candidates if (repo_root / candidate).exists()]


def _discover_ai_assets(repo_root: Path) -> dict[str, list[str]]:
    assets: dict[str, list[str]] = {}
    for name, patterns in AI_ASSET_GLOBS.items():
        matched: list[str] = []
        for pattern in patterns:
            matched.extend(
                path.relative_to(repo_root).as_posix()
                for path in repo_root.glob(pattern)
                if not _should_ignore_ai_asset_path(path.relative_to(repo_root).as_posix())
            )
        assets[name] = _dedupe(sorted(matched))

    workflow_paths = sorted(
        path.relative_to(repo_root).as_posix()
        for path in repo_root.glob(".github/workflows/*.yml")
    )
    assets["workflows"] = workflow_paths
    return assets


def _should_ignore_ai_asset_path(relative_path: str) -> bool:
    ignored_fragments = [
        "/assets/templates/",
        "/assets/example",
        "/references/",
        "/__pycache__/",
    ]
    normalized = "/" + relative_path.replace("\\", "/").strip("/")
    return any(fragment in normalized for fragment in ignored_fragments)


def _infer_major_workflows(
    repo_root: Path,
    readme_text: str,
    primary_languages: list[str],
    repo_map: dict[str, str],
    existing_ai_assets: dict[str, list[str]],
) -> list[str]:
    workflows: list[str] = []
    lower = readme_text.lower()

    if "cli" in lower:
        workflows.append("Maintain CLI flows, prompts, and output contracts.")
    if "api" in lower or "fastapi" in lower or "server" in lower:
        workflows.append("Extend and verify API or service behavior without breaking external callers.")
    if "web interface" in lower or "frontend" in lower or "ui" in lower or "static" in repo_map:
        workflows.append("Update web UI or static assets while preserving usability and responsiveness.")
    if "docs" in repo_map or "documentation" in lower:
        workflows.append("Keep deep documentation, agent guidance, and architecture notes in sync with the codebase.")
    if "tests" in repo_map:
        workflows.append("Add or adjust automated validation when behavior or interfaces change.")
    if existing_ai_assets.get("custom_agents") or existing_ai_assets.get("repo_skills"):
        workflows.append("Curate contributor-facing AI assets, skills, prompts, and instructions.")
    if existing_ai_assets.get("workflows"):
        workflows.append("Maintain CI/CD workflows, quality gates, and automation entrypoints.")
    if "memory-bank" in repo_map:
        workflows.append("Refresh resumable project memory when priorities, architecture, or milestones shift.")
    if not workflows:
        language = primary_languages[0] if primary_languages else "the primary stack"
        workflows.append(f"Implement and validate day-to-day feature work across {language} source and tests.")
    return _dedupe(workflows)


def _infer_risky_boundaries(repo_root: Path, agents_text: str) -> list[str]:
    boundaries: list[str] = []
    for line in agents_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Do not") or stripped.startswith("- Never"):
            boundaries.append(stripped[2:].strip())

    if (repo_root / "output").exists():
        boundaries.append("Treat `output/` as generated output unless the task explicitly targets generated artifacts.")
    if (repo_root / "sample_outputs").exists():
        boundaries.append("Do not rewrite sample artifacts casually; verify whether they are golden outputs first.")
    if (repo_root / ".env").exists():
        boundaries.append("Avoid editing `.env` or exposing secrets while scaffolding agent workflows.")
    if (repo_root / "data").exists():
        boundaries.append("Assume cached data and vector indexes under `data/` may be expensive to regenerate.")

    if not boundaries:
        boundaries.append("Preserve user-authored docs and existing agent assets outside managed sections.")
    return _dedupe(boundaries)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
