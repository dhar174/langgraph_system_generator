<!-- repo-agent-bootstrap:file-kind=adr -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# ADR 0001: Preserve the existing hybrid agent stack while bootstrapping missing files

## Status
Accepted

## Context
This repository already contains a large contributor-facing AI stack in
`AGENTS.md`, `.github/agents/`, `.github/instructions/`, `.github/skills/`,
`.github/prompts/`, and `memory-bank/`. The repo bootstrap skill identified
missing supporting files, but its generated custom agents do not match this
repository's stricter test-enforced frontmatter and content conventions.

## Decision
Add only the missing bootstrap-compatible support files that do not overwrite or
replace the existing agent, skill, or instruction inventory. Keep future
maintenance non-destructive by using managed markers in the newly added files.

## Consequences
### Positive
- The repository now has the bootstrap support documents that were missing.
- Existing custom agents, skills, prompts, and instructions remain untouched.
- Future maintenance can replace only the managed sections in these files.

### Negative
- The repository still does not adopt the scaffolded bootstrap agent roster.
- Any broader bootstrap refresh must be adapted to this repo's custom agent
  tests before it can be applied safely.
<!-- repo-agent-bootstrap:managed:end -->
