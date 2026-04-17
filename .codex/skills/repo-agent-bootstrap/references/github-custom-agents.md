# GitHub Custom Agents

Use the current GitHub custom-agent format for files under `.github/agents/`.

Working rules for this skill:

- include a concise `description`
- use focused tool lists instead of defaulting to everything
- always include the delegation alias `custom-agent` so the agent can hand work to another specialist
- target `github-copilot`
- prefer current frontmatter fields such as `disable-model-invocation` and `user-invocable`

Repository references:

- `https://docs.github.com/en/copilot/reference/custom-agents-configuration`
- `https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-custom-agents`

Practical guidance:

- keep each agent narrow and tied to a real repo workflow
- do not create a dozen generic roleplay agents
- use handoffs only when a natural next step exists
- preserve the repo's own commands, boundaries, and validation expectations in agent bodies
