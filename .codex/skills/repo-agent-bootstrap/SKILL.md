---
name: repo-agent-bootstrap
description: 'Bootstrap or maintain a repo-specific Copilot, Codex, and Claude agent stack by inventorying docs, commands, workflows, and existing AI assets before scaffolding managed guidance.'
---

# Repo Agent Bootstrap

Use this skill when setting up or refreshing agentic coding support for a repository. It is for plan-first scaffolding and maintenance of:

- `AGENTS.md` and `CLAUDE.md`
- `.github/copilot-instructions.md` and `.github/instructions/*.instructions.md`
- `.github/agents/*.agent.md`
- selected `.github/skills/*`
- `memory-bank/`, `plans/`, ADRs, and architecture docs
- safe workflow and hook stubs when the repo justifies them

## When To Use This Skill

Use this skill when the task is to:

- bootstrap AI agent support for a new repo
- standardize a messy or inconsistent existing agent stack
- refresh repo guidance after architecture or workflow drift
- create a reusable Copilot/Codex/Claude setup tied to the repo's real purpose

Do not use this skill when the task is only:

- writing one standalone `AGENTS.md`
- adding a single custom agent to an otherwise healthy stack
- making a small documentation tweak unrelated to repo-wide agent workflows
- importing unvetted third-party assets without pinned provenance

## What This Skill Produces

This skill is designed to create or maintain a hybrid stack that works across GitHub Copilot, Codex, and Claude. It always:

1. inventories the repo first
2. derives major workflows from real docs and manifests
3. proposes or generates an orchestrator agent plus focused specialists
4. writes managed sections so later maintenance runs preserve human edits outside them
5. records provenance for any imported third-party assets

## Workflow

### 1. Inventory first

Run the inventory helper before generating files. Because this is installed as a global skill, invoke the bundled script from the global skill folder:

```bash
python "$HOME/.agents/skills/repo-agent-bootstrap/scripts/inventory_repo.py" --repo-root .
```

Review the JSON output for:

- repo purpose
- stack and commands
- repo map and high-signal files
- existing AI assets
- risky boundaries
- major workflows worth dedicated agents or instructions

If the repo already has `AGENTS.md`, `.github/agents/`, `.github/instructions/`, or `memory-bank/`, treat those as existing product context, not noise.

### 2. Plan the stack

Before writing files, decide:

- which workflows deserve custom agents
- which guidance belongs in always-on root files versus on-demand skills
- which path-specific instruction files are justified
- whether workflow or hook stubs are appropriate
- whether any third-party asset is clearly worth importing

Always include at least one orchestrator/planning agent.

Use these decision rules instead of guessing:

- Generate exactly one orchestrator/planning agent by default.
- Add a specialist agent only when a workflow is both repo-specific and recurring enough to justify a dedicated role.
- Prefer 2-5 total generated agents. Go above that only when the repo has clearly separate subsystems with different commands, risks, or contributor audiences.
- Add a path-specific instruction file only when a directory or file family has stable rules that differ from root guidance and are likely to matter repeatedly.
- Add a skill instead of more root guidance when the instructions are detailed, procedural, and only relevant sometimes.
- Add a hook or workflow stub only when the repo already has CI/automation patterns or a repeated validation routine that benefits from explicit automation guidance.
- If a candidate automation would be noisy, destructive, or hard to validate, skip it and record the skip in the final summary.
- Vendor a third-party asset only if it is pinned, attributable, licensed clearly enough to reuse, and materially better than a repo-specific original. Otherwise recommend it without copying it.

### 3. Scaffold the stack

Use the scaffolder to render managed content:

```bash
python "$HOME/.agents/skills/repo-agent-bootstrap/scripts/scaffold_agent_stack.py" --repo-root . --generated-on YYYY-MM-DD
```

The scaffolder writes managed sections for:

- root guidance files
- memory-bank files
- plans and ADRs
- path-specific instructions
- custom agents
- selected repo skills
- a provenance manifest

### 4. Maintain instead of replacing

When rerunning on an existing repo, preserve human edits outside managed blocks. Use:

```bash
python "$HOME/.agents/skills/repo-agent-bootstrap/scripts/merge_managed_file.py" --target AGENTS.md --source-file draft-managed.md
```

Use maintenance mode when:

- the repo architecture changed
- the command surface changed
- contributor guidance drifted
- the major workflows changed enough that the agent roster is now wrong

### 5. Validate before handoff

Always validate the generated stack:

```bash
python "$HOME/.agents/skills/repo-agent-bootstrap/scripts/validate_agent_stack.py" --repo-root .
```

On Windows PowerShell, the same commands can use `${HOME}`:

```powershell
python "${HOME}\.agents\skills\repo-agent-bootstrap\scripts\inventory_repo.py" --repo-root .
python "${HOME}\.agents\skills\repo-agent-bootstrap\scripts\scaffold_agent_stack.py" --repo-root . --generated-on YYYY-MM-DD
python "${HOME}\.agents\skills\repo-agent-bootstrap\scripts\validate_agent_stack.py" --repo-root .
```

The validator checks for:

- required bootstrap files
- custom agent frontmatter
- delegation-tool presence (`custom-agent`, compatible with `Task`)
- provenance structure for imported assets

## External Source Policy

Only vendor third-party prompts, skills, hooks, or workflows when all of the following are true:

- the source is pinned to a commit SHA or version tag
- the original path is recorded
- license/provenance is recorded
- the asset is clearly better than a repo-specific original

If licensing, provenance, or revision pinning is unclear:

- do not vendor the asset
- mention it only as a recommendation
- record exactly why it was not imported

Read these references before importing anything:

- [External sourcing policy](references/external-sourcing-policy.md)
- [GitHub custom agent notes](references/github-custom-agents.md)
- [Hooks and workflow guidance](references/hooks-and-workflows.md)

## Reference Pack

Load these on demand, not all at once:

- [GitHub custom agents](references/github-custom-agents.md)
- [Instruction layering](references/instruction-layering.md)
- [Hooks and workflows](references/hooks-and-workflows.md)
- [Managed maintenance](references/maintenance-strategy.md)
- [Target output map](references/target-output-map.md)

## Bundled Templates

Template skeletons live under `assets/templates/stack/`. Use them when you need a concrete file shape quickly, but prefer tailoring the rendered content to the actual repo inventory instead of copying placeholders blindly.

## Required Output Contract

When you use this skill, the final handoff should include all of the following:

1. A short repo profile summary:
   - purpose
   - stack
   - commands
   - major workflows
   - risky boundaries
2. The planned or generated agent roster:
   - orchestrator agent
   - specialist agents
   - any path-specific instruction files
   - any selected repo skills
3. A concrete file summary:
   - files created
   - files updated
   - files intentionally skipped
4. Validation results:
   - which validation command ran
   - whether it passed
   - unresolved warnings or drift
5. External-source provenance:
   - imported items and pinned revisions
   - or explicit note that no third-party assets were vendored

Do not end with only “done” or a raw diff summary. The output should make it obvious what was discovered, what was generated, what was skipped, and why.

## Scripts

- `scripts/inventory_repo.py`: emit a structured repo profile as JSON
- `scripts/scaffold_agent_stack.py`: render and write the managed bootstrap stack
- `scripts/merge_managed_file.py`: replace only the managed section in an existing file
- `scripts/validate_agent_stack.py`: validate the generated stack
- `lib/repo_agent_bootstrap/`: bundled portable Python library so the global skill works even when the source repo is not installed locally

## Optional installer

If you are working from the source repository and want to publish this repo-local skill into your global shared skills folder, use the repository helper:

```powershell
.\scripts\install-global-skill.ps1 -SkillName repo-agent-bootstrap
```

Preview without changing anything:

```powershell
.\scripts\install-global-skill.ps1 -SkillName repo-agent-bootstrap -WhatIf
```

If you are reading this skill from an already-installed global location, you can ignore this installer section.
