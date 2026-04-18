<!-- repo-agent-bootstrap:file-kind=runbook -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# Runbook

## Operating mode
1. Read `AGENTS.md`, `memory-bank/activeContext.md`, and
   `memory-bank/progress.md` first.
2. Inventory the existing `.github/agents/`, `.github/instructions/`,
   `.github/skills/`, and `.github/prompts/` assets before adding new
   contributor-facing guidance.
3. Prefer additive, non-destructive changes; preserve existing repo-specific AI
   assets unless the task explicitly requires migration.

## Maintenance workflow
1. Run the repo bootstrap inventory script to understand the current repo
   profile.
2. Use bootstrap dry-run output to identify missing or drifting support files.
3. Apply only the smallest safe subset of changes that fits this repository's
   established tests and conventions.
4. Re-run validation and surface any remaining drift instead of forcing
   scaffolded content into incompatible files.

## Verification checklist
- Existing custom agent files still satisfy the test-enforced frontmatter and
  shared-resource rules.
- Existing skills, prompts, and instructions were not overwritten during
  bootstrap follow-up work.
- Any newly added bootstrap files use managed markers so later maintenance can
  remain targeted.
<!-- repo-agent-bootstrap:managed:end -->
