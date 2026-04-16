---
name: repo-agent-bootstrap
description: 'Bootstrap or maintain a repo-specific Copilot, Codex, and Claude agent stack by inventorying docs, commands, workflows, and existing AI assets before scaffolding managed guidance.'
---

# Repo Agent Bootstrap

This is the Codex-discoverable mirror of the canonical repo-local skill at:

`../../.github/skills/repo-agent-bootstrap/`

Use the canonical repo-local resources for scripts, references, and templates:

- `../../.github/skills/repo-agent-bootstrap/scripts/`
- `../../.github/skills/repo-agent-bootstrap/references/`
- `../../.github/skills/repo-agent-bootstrap/assets/templates/stack/`

## Workflow

1. Inventory the repository first:

```bash
python .github/skills/repo-agent-bootstrap/scripts/inventory_repo.py --repo-root .
```

2. Plan the stack around real repo workflows, commands, and boundaries.
3. Scaffold managed content:

```bash
python .github/skills/repo-agent-bootstrap/scripts/scaffold_agent_stack.py --repo-root . --generated-on 2026-04-15
```

4. Validate before handoff:

```bash
python .github/skills/repo-agent-bootstrap/scripts/validate_agent_stack.py --repo-root .
```

## Rules

- Use this skill for repo-wide bootstrap or maintenance, not for one-off single-file agent edits.
- Always include at least one orchestrator/planning agent.
- Prefer 2-5 total generated agents unless the repo clearly has more independent workflows.
- Use strategic tool allowlists and always include `custom-agent` for delegation.
- Add path-specific instructions only when subtree rules are materially different from root guidance.
- Preserve user edits outside managed sections.
- Vendor third-party assets only from pinned revisions with provenance and license notes.
- If provenance or licensing is unclear, recommend the asset but do not copy it.

## Required Handoff

End with:

1. repo profile summary
2. agent roster summary
3. file summary for created, updated, and skipped files
4. validation result
5. provenance summary for imported third-party content, or an explicit note that none were imported

## Optional installer

From this repository, you can publish the canonical repo-local skill to your shared global skills folder with:

```powershell
.\scripts\install-global-skill.ps1 -SkillName repo-agent-bootstrap
```
