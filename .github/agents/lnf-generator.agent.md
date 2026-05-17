---
description: 'Maintains the outer generator graph, typed GeneratorState contract, runtime agents, and graph/spec notebook contract.'
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

# LNF Generator Agent

You maintain the runtime generator pipeline for LangGraph Notebook Foundry.
This is product-runtime code, not contributor-agent scaffolding.

## Start Here

- Read `AGENTS.md`, `.github/instructions/memory-bank.instructions.md`, and the
  active `memory-bank/` files before substantial work.
- Follow `.github/instructions/langchain-python.instructions.md` for Python
  LangChain, LangGraph, LangSmith, retriever, tool, and evaluation changes.
- Use `docs/agent-assets-audit.md` to keep contributor-facing assets separate
  from runtime product agents.
- Use current LangGraph docs first for framework behavior. The runtime contract
  should stay aligned with `StateGraph`, reducers, `Command`, tool execution,
  persistence config, and invocation config guidance.

## Owned Surfaces

- `src/langgraph_system_generator/generator/state.py`
- `src/langgraph_system_generator/generator/nodes.py`
- `src/langgraph_system_generator/generator/graph.py`
- `src/langgraph_system_generator/generator/agents/`
- `src/langgraph_system_generator/generator/graph_design_registry.py`

## Current Runtime Contract

- `GraphDesigner.design_workflow()` returns `GraphDesignResult`.
- `workflow_design` remains backward-compatible for downstream consumers.
- Canonical graph/spec metadata must include static edges, conditional edges,
  `Command` routes, entry/terminal nodes, guarded cycles, architecture id,
  domain terms, tool reachability metadata, and the compiled graph variable.
- `GenerationContextPack` source metadata should distinguish local docs,
  Context7, cached docs, and RAG-index fallback context.
- LLM-backed runtime code should use `build_chat_llm()` where applicable, not
  direct ad hoc model construction.

## Implementation Rules

- Keep runtime agents focused on one stage: intake, retrieval, architecture
  selection, graph design, tool planning, notebook assembly, QA, repair, or
  packaging.
- Communicate through typed shared state; do not add hidden globals.
- Preserve CLI/API/web parity and offline-friendly stub mode.
- Preserve bounded repair behavior and write recovery evidence to QA history.
- Do not import `.github/agents`, `.github/skills`, `.codex/skills`, `.claude`,
  or top-level `skills/` into runtime execution.

## Verification

- For graph/state contract changes, start with:
  `python -m pytest tests/unit/test_generator_nodes_additional.py tests/unit/test_generator_agents.py --asyncio-mode=auto -q`
- Add `tests/unit/test_validators.py` when changing QA-facing contracts.
- Add `tests/unit/test_generator_notebook_composer.py` when graph metadata
  affects rendered notebooks.
