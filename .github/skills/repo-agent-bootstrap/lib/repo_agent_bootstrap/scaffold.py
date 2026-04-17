from __future__ import annotations

import json
from pathlib import Path

from .managed_files import merge_managed_text, wrap_managed_block
from .models import AgentSpec, ExternalSource, RepoProfile


def suggest_agent_specs(profile: RepoProfile) -> list[AgentSpec]:
    """Suggest a focused set of custom agents for a target repository."""

    specs = [
        AgentSpec(
            slug="repo-planner",
            display_name="Repo Planner",
            description=(
                "Plans repo-specific work, delegates to specialists, and keeps scope, validation, and documentation aligned."
            ),
            tools=["read", "search", "edit", "execute", "web", "custom-agent"],
            responsibilities=[
                "Read the repo map, AGENTS files, and key docs before proposing implementation work.",
                "Break complex requests into specialist subtasks and sequence them safely.",
                "Name the validation commands and memory/doc updates needed before sign-off.",
            ],
            focus_paths=["AGENTS.md", ".github/", "docs/", "memory-bank/", "plans/"],
        )
    ]

    if "Python" in profile.primary_languages or "FastAPI" in profile.frameworks:
        specs.append(
            AgentSpec(
                slug="backend-python-specialist",
                display_name="Backend Python Specialist",
                description=(
                    "Owns Python backend, API, and service changes while protecting interfaces, tests, and operational commands."
                ),
                tools=["read", "search", "edit", "execute", "custom-agent"],
                responsibilities=[
                    "Work inside the main Python source tree and adjacent tests.",
                    "Preserve public interfaces unless the task explicitly calls for a breaking change.",
                    "Run the smallest relevant validation commands before handing work back.",
                ],
                focus_paths=["src/", "tests/", "requirements.txt", "setup.py"],
            )
        )

    if any("web ui" in workflow.lower() or "static assets" in workflow.lower() for workflow in profile.major_workflows):
        specs.append(
            AgentSpec(
                slug="frontend-experience-specialist",
                display_name="Frontend Experience Specialist",
                description=(
                    "Improves UI flows, static assets, and user-facing polish while preserving responsiveness and repo patterns."
                ),
                tools=["read", "search", "edit", "execute", "web", "custom-agent"],
                responsibilities=[
                    "Preserve the established visual language unless a redesign is explicitly requested.",
                    "Keep accessibility, responsiveness, and download flows intact.",
                    "Coordinate with backend and docs agents when interface changes ripple outward.",
                ],
                focus_paths=["src/", "docs/", ".github/instructions/"],
            )
        )

    if "docs" in profile.repo_map or profile.existing_ai_assets.get("agents_md"):
        specs.append(
            AgentSpec(
                slug="docs-memory-curator",
                display_name="Docs And Memory Curator",
                description=(
                    "Maintains AGENTS files, memory-bank context, ADRs, and architecture docs so future sessions inherit accurate context."
                ),
                tools=["read", "search", "edit", "web", "custom-agent"],
                responsibilities=[
                    "Update repo guidance only when behavior, architecture, or contributor expectations actually changed.",
                    "Keep root instructions concise and move deep detail into on-demand docs.",
                    "Preserve human-authored notes outside managed sections during maintenance runs.",
                ],
                focus_paths=["AGENTS.md", "CLAUDE.md", "docs/", "memory-bank/", "plans/"],
            )
        )

    if profile.ci_files or "tests" in profile.repo_map:
        specs.append(
            AgentSpec(
                slug="quality-automation-guardian",
                display_name="Quality Automation Guardian",
                description=(
                    "Owns tests, linting, type checks, CI workflows, and safe hooks so generated changes remain verifiable."
                ),
                tools=["read", "search", "edit", "execute", "custom-agent"],
                responsibilities=[
                    "Guard the default validation path and keep commands easy for other agents to run.",
                    "Tighten automation conservatively; avoid destructive or noisy hooks by default.",
                    "Escalate when existing CI expectations conflict with proposed scaffolding.",
                ],
                focus_paths=["tests/", ".github/workflows/", ".github/hooks/"],
            )
        )

    return specs


def build_bootstrap_files(
    profile: RepoProfile,
    *,
    generated_on: str,
    external_sources: list[ExternalSource] | None = None,
) -> dict[str, str]:
    """Render the core bootstrap stack for a repository."""

    external_sources = external_sources or []
    agents = suggest_agent_specs(profile)

    files: dict[str, str] = {
        "AGENTS.md": wrap_managed_block(
            _render_agents_md(profile), file_kind="agents-md", provenance=f"repo-agent-bootstrap@{generated_on}"
        ),
        "CLAUDE.md": wrap_managed_block(
            _render_claude_md(profile), file_kind="claude-md", provenance=f"repo-agent-bootstrap@{generated_on}"
        ),
        ".github/copilot-instructions.md": wrap_managed_block(
            _render_copilot_instructions(profile),
            file_kind="copilot-instructions",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        ".github/instructions/backend.instructions.md": _wrap_frontmatter_markdown(
            _render_backend_instructions(profile),
            file_kind="path-instructions",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        ".github/instructions/docs.instructions.md": _wrap_frontmatter_markdown(
            _render_docs_instructions(profile),
            file_kind="path-instructions",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        ".github/instructions/automation.instructions.md": _wrap_frontmatter_markdown(
            _render_automation_instructions(profile),
            file_kind="path-instructions",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        ".github/skills/repo-context-refresh/SKILL.md": _render_repo_context_refresh_skill(profile),
        ".github/skills/repo-quality-gates/SKILL.md": _render_repo_quality_gates_skill(profile),
        "docs/architecture.md": wrap_managed_block(
            _render_architecture_doc(profile),
            file_kind="architecture-doc",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "docs/adr/0001-agent-stack-bootstrap.md": wrap_managed_block(
            _render_adr(profile),
            file_kind="adr",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "plans/current-plan.md": wrap_managed_block(
            _render_current_plan(profile),
            file_kind="current-plan",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "plans/runbook.md": wrap_managed_block(
            _render_runbook(profile),
            file_kind="runbook",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "memory-bank/projectbrief.md": wrap_managed_block(
            _render_projectbrief(profile),
            file_kind="memory-bank",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "memory-bank/productContext.md": wrap_managed_block(
            _render_product_context(profile),
            file_kind="memory-bank",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "memory-bank/activeContext.md": wrap_managed_block(
            _render_active_context(profile),
            file_kind="memory-bank",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "memory-bank/systemPatterns.md": wrap_managed_block(
            _render_system_patterns(profile),
            file_kind="memory-bank",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "memory-bank/techContext.md": wrap_managed_block(
            _render_tech_context(profile),
            file_kind="memory-bank",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "memory-bank/progress.md": wrap_managed_block(
            _render_progress(profile, generated_on),
            file_kind="memory-bank",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        ),
        "memory-bank/tasks/_index.md": wrap_managed_block(
            _render_task_index(), file_kind="memory-bank", provenance=f"repo-agent-bootstrap@{generated_on}"
        ),
        ".github/workflows/copilot-setup-steps.yml": _render_workflow_stub(profile),
        ".github/hooks/session-guard/hooks.json": _render_hook_stub(),
        ".github/agent-stack-provenance.json": json.dumps(
            {
                "generatedOn": generated_on,
                "generator": "repo-agent-bootstrap",
                "externalSources": [source.to_dict() for source in external_sources],
            },
            indent=2,
        )
        + "\n",
    }

    for spec in agents:
        files[f".github/agents/{spec.slug}.agent.md"] = _wrap_frontmatter_markdown(
            _render_agent_markdown(spec),
            file_kind="custom-agent",
            provenance=f"repo-agent-bootstrap@{generated_on}",
        )

    return files


def write_bootstrap_files(repo_root: Path, rendered_files: dict[str, str]) -> list[str]:
    """Write rendered files into a target repository, preserving unmanaged prose."""

    repo_root = repo_root.resolve()
    written: list[str] = []
    for relative_path, content in rendered_files.items():
        destination = repo_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        existing = destination.read_text(encoding="utf-8") if destination.exists() else ""
        merged = merge_managed_text(existing, content)
        destination.write_text(merged, encoding="utf-8")
        written.append(relative_path)
    return sorted(written)


def _wrap_frontmatter_markdown(document: str, *, file_kind: str, provenance: str) -> str:
    """Insert managed markers after the first YAML frontmatter block."""

    if not document.startswith("---\n"):
        return wrap_managed_block(document, file_kind=file_kind, provenance=provenance)

    lines = document.splitlines()
    if "---" not in lines[1:]:
        return wrap_managed_block(document, file_kind=file_kind, provenance=provenance)

    end_index = lines[1:].index("---") + 1
    frontmatter = "\n".join(lines[: end_index + 1]).strip() + "\n"
    body = "\n".join(lines[end_index + 1 :]).strip()
    managed_body = wrap_managed_block(body, file_kind=file_kind, provenance=provenance)
    return frontmatter + "\n" + managed_body


def _render_agents_md(profile: RepoProfile) -> str:
    repo_map_lines = "\n".join(f"- `{path}` — {description}" for path, description in profile.repo_map.items())
    command_lines = "\n".join(
        f"- {label.capitalize()}: `{command}`" for label, command in profile.commands.items()
    )
    workflow_lines = "\n".join(f"- {workflow}" for workflow in profile.major_workflows)
    boundary_lines = "\n".join(f"- {boundary}" for boundary in profile.risky_boundaries)
    high_signal_lines = "\n".join(f"- `{path}`" for path in profile.high_signal_files[:8])

    return f"""# AGENTS.md

## Project overview
This repository contains {profile.purpose}

Primary goals:
{workflow_lines}

## Repo map
Important directories:
{repo_map_lines}

High-signal files:
{high_signal_lines}

## How to work in this repo
Before making changes:
1. Read `memory-bank/activeContext.md` and `memory-bank/progress.md`.
2. Skim `docs/architecture.md` and any nearby ADRs when the task changes behavior or architecture.
3. Inspect existing `.github/agents/`, `.github/instructions/`, and `.github/skills/` assets before adding new ones.

## Build, test, lint
Use the following commands unless the task explicitly requires otherwise:
{command_lines}

## Engineering conventions
- Prefer minimal, targeted changes over broad refactors.
- Preserve public interfaces unless the task explicitly calls for a breaking change.
- Add or update validation when behavior changes.
- Keep repo-wide instructions short and move deep detail into `docs/`, `memory-bank/`, or skills.

## Constraints / do-not rules
{boundary_lines}

## Definition of done
- Relevant tests pass.
- Lint and type checks pass when applicable.
- `memory-bank/` or `docs/` files are refreshed when architecture or contributor expectations change.
- The final diff stays within the requested scope.
"""


def _render_claude_md(profile: RepoProfile) -> str:
    return f"""# CLAUDE.md

Read `AGENTS.md` first for repo-wide defaults.

Then load:
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `docs/architecture.md` when the task affects system design

Claude-specific note:
- Keep responses concise, but preserve the same validation and boundary rules defined in `AGENTS.md`.
- Prefer the generated specialist agents and repository skills when the task clearly matches them.
- This repo's primary stack is {", ".join(profile.primary_languages)} with {", ".join(profile.frameworks or ['repo-specific tooling'])}.
"""


def _render_copilot_instructions(profile: RepoProfile) -> str:
    lines = [
        "# Repository-wide Copilot instructions",
        "",
        f"This repository uses {', '.join(profile.primary_languages)} and {', '.join(profile.frameworks or ['repo-specific tooling'])}.",
        "",
        "When making changes:",
        "- prefer small, focused diffs",
        "- preserve existing architecture unless the task explicitly changes it",
        "- run the relevant validation commands before finishing",
        "- update `memory-bank/activeContext.md` and `memory-bank/progress.md` when project state shifts",
        "",
        "Important references:",
        "- `AGENTS.md`",
        "- `docs/architecture.md`",
        "- `memory-bank/activeContext.md`",
        "- `memory-bank/progress.md`",
        "",
        "Do not:",
        "- edit generated files casually",
        "- introduce new dependencies without justification",
        "- remove tests to avoid fixing failures",
    ]
    return "\n".join(lines)


def _render_backend_instructions(profile: RepoProfile) -> str:
    test_command = profile.commands.get("test", "pytest")
    lint_command = profile.commands.get("lint", "ruff check .")
    typecheck_command = profile.commands.get("typecheck", "mypy .")
    return f"""---
applyTo: "src/**,tests/**"
---

# Backend instructions

- Preserve existing interfaces and module boundaries unless the task explicitly changes them.
- Add or update automated coverage for behavior changes.
- Run `{test_command}`, `{lint_command}`, and `{typecheck_command}` when the touched paths justify them.
- Reuse established helper modules before introducing new abstractions.
"""


def _render_docs_instructions(profile: RepoProfile) -> str:
    return """---
applyTo: "docs/**,AGENTS.md,CLAUDE.md,memory-bank/**,plans/**"
---

# Documentation instructions

- Keep repo-wide instructions concise and push deep detail into on-demand docs.
- Update memory-bank files when priorities, milestones, or architecture changed in meaningful ways.
- Prefer exact commands, paths, and examples over vague prose.
- Preserve human-authored commentary outside managed sections.
"""


def _render_automation_instructions(profile: RepoProfile) -> str:
    return """---
applyTo: ".github/**,scripts/**"
---

# Automation instructions

- Treat workflows, hooks, and repo automation as high-signal infrastructure.
- Favor safe defaults and narrow triggers over noisy or destructive automation.
- Document why a new workflow or hook exists and how it should be validated.
- Preserve pinned revisions and provenance for any imported third-party automation.
"""


def _render_agent_markdown(spec: AgentSpec) -> str:
    responsibilities = "\n".join(f"- {item}" for item in spec.responsibilities)
    focus_paths = "\n".join(f"- `{path}`" for path in spec.focus_paths) or "- Use the repo map to locate the right subsystem."
    tools_list = ", ".join(f'"{tool}"' for tool in spec.tools)
    return f"""---
name: "{spec.display_name}"
description: "{spec.description}"
target: "github-copilot"
tools: [{tools_list}]
disable-model-invocation: false
user-invocable: true
---

# {spec.display_name}

You are a repo-specific specialist. Ground yourself in `AGENTS.md`, `memory-bank/`, and the nearest path-specific instructions before making changes.

## Responsibilities
{responsibilities}

## Focus paths
{focus_paths}

## Collaboration rules
- Delegate with `custom-agent` when another specialist is clearly better suited for part of the task.
- Keep diffs focused and explain validation steps before handing work back.
- Escalate when instructions conflict or a maintenance run would overwrite user-owned content outside managed sections.
"""


def _render_architecture_doc(profile: RepoProfile) -> str:
    components = "\n".join(
        f"### {path}\n{description}" for path, description in list(profile.repo_map.items())[:5]
    )
    workflows = "\n".join(f"{index}. {workflow}" for index, workflow in enumerate(profile.major_workflows, start=1))
    return f"""# Architecture

## Overview
{profile.purpose}

This generated reference is the deeper architecture companion to `AGENTS.md`. Keep broadly applicable instructions in root guidance and reserve this file for subsystem relationships, data flow notes, and longer rationale.

## Modules
{components}

## Request / event lifecycle
{workflows}

## Security / reliability considerations
- Preserve contributor-authored content outside managed sections during maintenance runs.
- Keep third-party AI assets pinned, attributable, and license-checked before vendoring.
- Use the smallest relevant validation commands before merging automation changes.
"""


def _render_adr(profile: RepoProfile) -> str:
    return f"""# ADR 0001: Bootstrap a hybrid agent stack

## Status
Accepted

## Context
{profile.repo_name} needs repository guidance that works across GitHub Copilot, Codex, and Claude without overloading every task with the same context.

## Decision
Adopt a layered stack with root guidance (`AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`), path-specific instructions, repository custom agents, lightweight repo skills, and `memory-bank/` state files. Maintenance runs update only managed sections.

## Consequences
### Positive
- Agents can recover repo context quickly and delegate to specialists.
- Repo-wide guidance stays concise while deeper knowledge moves into on-demand files.

### Negative
- The stack introduces more files that need occasional maintenance.
- Generated sections require clear markers so human edits remain safe.
"""


def _render_current_plan(profile: RepoProfile) -> str:
    validations = "\n".join(f"- `{command}`" for command in profile.commands.values())
    return f"""# Current Plan

## Objective
Bootstrap or refresh the repository's AI agent stack so future agents inherit accurate guidance and reusable workflows.

## Scope
Included:
- Root guidance files
- Custom agents and selected skills
- Memory-bank and runbook scaffolding

Excluded:
- Unpinned third-party imports
- Destructive automation or hooks

## Plan
1. Inventory the repository's purpose, stack, commands, workflows, and current AI assets.
2. Render a repo-specific hybrid stack with managed sections and provenance metadata.
3. Validate the generated stack and hand back any drift or follow-up items.

## Validation
{validations}

## Completion criteria
- Core files exist and validate cleanly.
- Each agent exposes the delegation tool and focused tool access.
- Managed updates preserve user-authored content outside generated sections.
"""


def _render_runbook(profile: RepoProfile) -> str:
    return """# Runbook

## Operating mode
1. Read `AGENTS.md`, `memory-bank/activeContext.md`, and the nearest path-specific instructions first.
2. Inventory commands, workflows, AI assets, and risky boundaries before generating new agent files.
3. Prefer original repo-specific content; vendor third-party assets only from pinned revisions with provenance and license notes.

## Maintenance workflow
1. Detect existing managed sections and compare them to freshly rendered output.
2. Replace only managed blocks; preserve everything else.
3. Re-run stack validation and surface any unresolved drift explicitly.

## Verification checklist
- The agent roster still matches the repository's major workflows.
- Commands in docs match current manifests or README guidance.
- Memory-bank files reflect current priorities rather than stale templates.
- Imported external assets remain pinned and attributable.
"""


def _render_projectbrief(profile: RepoProfile) -> str:
    return f"""# Project Brief

## Project scope
{profile.purpose}

## Primary goals
{chr(10).join(f"- {workflow}" for workflow in profile.major_workflows[:4])}

## Repository boundaries
{chr(10).join(f"- {boundary}" for boundary in profile.risky_boundaries[:4])}
"""


def _render_product_context(profile: RepoProfile) -> str:
    return f"""# Product Context

## Problem
{profile.purpose}

## Target users
- Contributors working in {profile.repo_name}
- AI coding agents that need accurate repo context

## Core user goals
- Make safe repo-specific changes quickly.
- Recover context without re-reading the whole repository every session.
- Delegate specialized work to focused agents and skills.

## Non-goals
- Generic one-size-fits-all repo instructions
- Unpinned or unverifiable third-party AI assets
"""


def _render_active_context(profile: RepoProfile) -> str:
    relevant_files = "\n".join(f"- `{path}`" for path in profile.high_signal_files[:6])
    next_steps = "\n".join(f"{index}. {workflow}" for index, workflow in enumerate(profile.major_workflows[:3], start=1))
    return f"""# Active Context

## Current objective
Maintain a repo-specific hybrid agent stack that reflects the current codebase and contributor workflows.

## Why it matters now
The bootstrap stack only stays useful if commands, architecture notes, and specialist routing still match the repository.

## Current status
- Done:
  - Base repo inventory exists.
- In progress:
  - Keep managed guidance aligned with the codebase.
- Blocked:
  - none

## Relevant files
{relevant_files}

## Next recommended steps
{next_steps}
"""


def _render_system_patterns(profile: RepoProfile) -> str:
    components = "\n".join(
        f"### {path}\n- Responsibility: {description}\n- Inputs: repo-local changes and contributor requests\n- Outputs: validated artifacts or updated guidance\n- Dependencies: adjacent docs, tests, and automation"
        for path, description in list(profile.repo_map.items())[:4]
    )
    flows = "\n".join(f"{index}. {workflow}" for index, workflow in enumerate(profile.major_workflows[:4], start=1))
    return f"""# System Patterns

## High-level architecture
This repository uses a layered guidance model: root instructions for always-on context, path-specific instructions for targeted rules, focused custom agents for specialist work, and `memory-bank/` files for resumable state.

## Major components
{components}

## Key data flows
{flows}

## Extension points
- Add new custom agents only when a repo workflow is specialized and recurring.
- Add new path-specific instructions when a directory or file family has stable rules.
- Add or vendor skills only when the guidance is detailed but not needed on every task.
"""


def _render_tech_context(profile: RepoProfile) -> str:
    commands = profile.commands
    return f"""# Tech Context

## Stack
- Language: {", ".join(profile.primary_languages)}
- Frameworks: {", ".join(profile.frameworks or ['repo-specific tooling'])}
- CI/CD: {", ".join(profile.ci_files or ['No workflow detected yet'])}

## Local setup
- Install: {commands.get('install', 'discover from the primary manifest')}
- Dev server: {commands.get('dev', 'not yet detected')}
- Test command: {commands.get('test', 'discover from test tooling')}
- Lint command: {commands.get('lint', 'discover from lint tooling')}
- Typecheck command: {commands.get('typecheck', 'discover from type tooling')}

## Constraints
{chr(10).join(f"- {boundary}" for boundary in profile.risky_boundaries[:4])}
"""


def _render_progress(profile: RepoProfile, generated_on: str) -> str:
    command_status = "\n".join(
        f"- {label.capitalize()}: `{command}`" for label, command in profile.commands.items()
    )
    return f"""# Progress

## Milestones
- [x] Repository profile captured
- [x] Hybrid agent stack scaffolded
- [ ] Maintenance drift reviewed against future repo changes

## What works
- Repo-wide instructions, memory-bank scaffolding, and specialist agents exist.
- Managed sections allow maintenance runs to update generated content safely.

## What is incomplete
- Third-party imports remain optional until a pinned, licensed source is selected.
- The generated stack may still need repo-specific hand tuning after major architecture shifts.

## Validation status
{command_status}

## Last meaningful update
[{generated_on}] Generated or refreshed the repo bootstrap stack.
"""


def _render_task_index() -> str:
    return """# Tasks Index

## In Progress
- [BOOTSTRAP-001] Maintain repository agent stack - Keep managed guidance aligned with the codebase

## Pending
- [BOOTSTRAP-002] Evaluate third-party agent assets - Vendor only pinned, licensed sources

## Completed
- none yet
"""


def _render_repo_context_refresh_skill(profile: RepoProfile) -> str:
    return """---
name: repo-context-refresh
description: 'Refresh repository context files, memory-bank state, and root guidance after architecture, workflow, or milestone changes.'
---

# Repo Context Refresh

Use this skill when a task changes project direction, subsystem boundaries, or contributor expectations and the repo's agent-facing docs need to catch up.

## Workflow
1. Read `AGENTS.md`, `docs/architecture.md`, and `memory-bank/activeContext.md`.
2. Inspect the touched source paths and validation changes.
3. Update only the docs that changed meaningfully: `memory-bank/`, `plans/`, `AGENTS.md`, `CLAUDE.md`, or path-specific instructions.
4. Keep repo-wide instructions tight; move deep detail into on-demand docs.
"""


def _render_repo_quality_gates_skill(profile: RepoProfile) -> str:
    validation_lines = "\n".join(f"- `{command}`" for command in profile.commands.values())
    return f"""---
name: repo-quality-gates
description: 'Run the repository's test, lint, and typecheck commands, then summarize failures and next actions for coding agents.'
---

# Repo Quality Gates

Use this skill when you need to validate a change or interpret failing automation for this repository.

## Default validation commands
{validation_lines}

## Workflow
1. Run the smallest relevant validation subset first.
2. Group failures by root cause instead of by raw output order.
3. Call out missing tooling or environment issues separately from code regressions.
4. Do not relax or delete tests just to produce a green run.
"""


def _render_workflow_stub(profile: RepoProfile) -> str:
    test_command = profile.commands.get("test", "pytest")
    lint_command = profile.commands.get("lint", "ruff check .")
    return f"""name: copilot-setup-steps

on:
  workflow_dispatch:

jobs:
  verify-agent-stack:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify agent stack commands
        run: |
          echo "Run {test_command}"
          echo "Run {lint_command}"
          echo "Replace this stub with repo-specific environment setup before enabling on every push."
"""


def _render_hook_stub() -> str:
    return """{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "name": "announce-managed-guidance",
        "command": "echo 'Read AGENTS.md and memory-bank/ before significant work.'"
      }
    ]
  }
}"""
