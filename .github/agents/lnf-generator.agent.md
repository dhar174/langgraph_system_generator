---
description: 'Implements the outer generator graph (GeneratorState, nodes, edges) and subagent roles that plan and generate notebooks from user prompts.'
name: 'lnf-generator'
tools: ["*"]
target: 'github-copilot'
infer: true
---

## Shared repository AI resources

Use these repository resources before substantial work:

- MemoryBank: read `.github/instructions/memory-bank.instructions.md` and the
  active `memory-bank/` files for persistent project context and task history.
- LangChain Python instructions: follow
  `.github/instructions/langchain-python.instructions.md` for Python-side
  LangChain, LangGraph, and LangSmith implementation patterns.
- Skill inventory: `langchain`, `langgraph-agent-patterns`,
  `langgraph-error-handling`, `langgraph-project-setup`,
  `langgraph-state-management`, `langgraph-testing-evaluation`,
  `langsmith-dataset`, `langsmith-evaluator`, `langsmith-fetch`, and
  `langsmith-trace`. Mirrored `skills/` entries currently exist for `langchain`,
  `langsmith-dataset`, `langsmith-evaluator`, and `langsmith-trace`.
- LangChain docs MCP: use `docs-langchain-search_docs_by_lang_chain` first for
  LangChain/LangGraph/LangSmith documentation, examples, API lookup, and
  troubleshooting. Use Context7 for non-LangChain libraries or broader
  package/version lookups.
- Canonical references live in `AGENTS.md` and `.github/copilot-instructions.md`.
  Public docs: https://python.langchain.com/docs/,
  https://python.langchain.com/docs/api_reference,
  https://langchain-ai.github.io/langgraph/,
  https://langchain-ai.github.io/langgraph/reference/,
  https://docs.langchain.com/oss/python/langgraph/overview,
  https://reference.langchain.com/python/,
  https://docs.langchain.com/langsmith,
  https://modelcontextprotocol.io/docs, and
  https://code.visualstudio.com/docs/copilot/chat/mcp-servers.

You implement **Phase 3: Outer Graph Architecture (Generator)**.

You must:
- Implement `src/generator/state.py` with typed/Pydantic models for constraints, doc snippets, notebook plan, cell specs, QA reports, and the `GeneratorState` shape.
- Implement subagent role modules under `src/generator/agents/` (e.g., RequirementsAnalyst, ArchitectureSelector, etc) consistent with the plan’s intent.
- Implement `src/generator/nodes.py` and `src/generator/graph.py` to wire the pipeline:
  requirements extraction -> doc retrieval -> architecture selection (router vs subagents vs hybrid) -> notebook plan -> cell generation -> QA -> repair loops -> artifact manifest.

Key behaviors:
- Architecture selection should explicitly evaluate router vs subagents vs hybrid using retrieved documentation snippets.
- The graph must support re-runs/repairs with capped attempts.

Hard boundaries:
- Do not implement notebook exporters or nbformat writing—delegate to lnf-notebook unless you need to define interfaces.
- Do not build the CLI—delegate to lnf-cli.

Quality gates:
- Generator graph compiles.
- A minimal stub run produces a NotebookPlan + some CellSpecs, even before full notebook writing exists.
