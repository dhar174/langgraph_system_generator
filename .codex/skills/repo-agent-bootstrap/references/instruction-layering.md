# Instruction Layering

Use the layers intentionally:

- `AGENTS.md`: repo-wide defaults, commands, conventions, and hard boundaries
- `CLAUDE.md`: Claude-specific notes that should stay tiny and point back to `AGENTS.md`
- `.github/copilot-instructions.md`: short repo-wide Copilot guidance
- `.github/instructions/*.instructions.md`: path-specific or concern-specific rules
- `memory-bank/`: resumable project state, not timeless policy
- skills: detailed workflows that should only load when relevant

Good split:

- put almost-always-true rules in root files
- put directory-specific constraints in `.github/instructions/`
- put long operational playbooks in skills or docs
- keep active work state in `memory-bank/`

Reference:

- `https://docs.github.com/en/copilot/how-tos/custom-instructions/adding-repository-custom-instructions-for-github-copilot`
