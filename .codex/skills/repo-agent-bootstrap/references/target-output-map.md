# Target Output Map

The scaffolder is designed to create or maintain these areas in a target repo:

- root docs: `AGENTS.md`, `CLAUDE.md`
- repo-wide Copilot instructions: `.github/copilot-instructions.md`
- path-specific instructions: `.github/instructions/*.instructions.md`
- custom agents: `.github/agents/*.agent.md`
- selected repo skills: `.github/skills/*`
- memory-bank: `memory-bank/*.md`
- deep docs: `docs/architecture.md`, `docs/adr/*.md`
- active execution docs: `plans/*.md`
- optional automation stubs: `.github/workflows/*`, `.github/hooks/*`
- provenance: `.github/agent-stack-provenance.json`

Only generate what the repo inventory justifies. The goal is a tight stack, not maximum file count.
