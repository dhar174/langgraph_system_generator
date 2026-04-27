# Experimental Deep Agents Architecture Support

## Goal

Add an explicit, experimental `deepagents` architecture option without changing
the public request shape beyond the existing `agent_type` value set.

## Checklist

- [x] Confirm PR #298 merged and refresh #256 so public docs/onboarding is
  complete and Experimental Deep Agents is the remaining MVP blocker.
- [x] Create a fresh isolated worktree from current `origin/main`.
- [x] Register `deepagents` in the architecture registry.
- [x] Register a deterministic, validated `deepagents` graph fallback with a
  terminal path and Mermaid/schema exports.
- [x] Add `DeepAgentsPattern` with lazy optional `create_deep_agent(...)`
  imports and an offline deterministic fallback.
- [x] Wire CLI/API validation and stub generation for
  `--agent-type deepagents`.
- [x] Wire notebook composition/dependency planning so only Deep Agents
  notebooks include the optional `deepagents` runtime package.
- [x] Add compact script/notebook examples using deterministic toy tools and
  optional subagent specs.
- [x] Refresh docs that enumerate architecture values or pattern support.
- [x] Add focused tests for selector, graph fallback/export, notebook composer,
  CLI/API, and generated pattern snippets.

## Verification

- `python -m pytest tests/unit/test_generator_agents.py tests/unit/test_generator_nodes.py tests/unit/test_generator_nodes_additional.py tests/unit/test_generator_notebook_composer.py tests/unit/test_cli_api.py tests/unit/test_patterns.py -q`
- `python -m pytest tests/unit -q`
- `python -m pytest --asyncio-mode=auto -q`
- `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`

## Notes

- `deepagents` remains opt-in and experimental.
- The generated notebook imports `deepagents` only inside the live harness
  builder, so core imports and stub-mode generation remain offline-friendly.
- No new CLI flags, API request fields, web UI inputs, or `GeneratorState` keys
  are introduced.
