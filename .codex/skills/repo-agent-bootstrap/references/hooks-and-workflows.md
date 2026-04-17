# Hooks And Workflows

Hooks and workflow stubs are optional. Add them only when the repo's real workflows justify the extra automation.

Default stance:

- prefer safe, quiet stubs over always-on automation
- document what the hook or workflow is for
- keep validation commands explicit
- do not add destructive commands to automated hooks

For imported automation:

- pin the source revision
- record original URL and path
- record license/provenance
- adapt the automation to the target repo's commands instead of blindly copying

References:

- `https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/use-hooks`
- `https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/customize-the-agent-environment`
