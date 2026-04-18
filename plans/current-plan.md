<!-- repo-agent-bootstrap:file-kind=current-plan -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# Current Plan

## Objective
Keep the repository's existing AI guidance stack intact while filling in the
missing bootstrap support files required for safe maintenance.

## Scope
Included:
- `CLAUDE.md`
- `docs/adr/0001-agent-stack-bootstrap.md`
- `plans/current-plan.md`
- `plans/runbook.md`

Excluded:
- Replacing existing `.github/agents/*.agent.md`
- Replacing existing `.github/instructions/*.instructions.md`
- Replacing existing `.github/skills/*`
- Importing unpinned third-party assets

## Plan
1. Inventory the repository and compare the bootstrap output against the
   current AI asset stack.
2. Add only the missing support files that do not conflict with existing repo
   conventions.
3. Re-run bootstrap validation and report any remaining drift explicitly.

## Validation
- `python .github/skills/repo-agent-bootstrap/scripts/validate_agent_stack.py`

## Completion criteria
- The missing support files exist.
- Existing agents, skills, prompts, and instructions remain untouched.
- The bootstrap validator no longer fails on the missing support-file set.
<!-- repo-agent-bootstrap:managed:end -->
