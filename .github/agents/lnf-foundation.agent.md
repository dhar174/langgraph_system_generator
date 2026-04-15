---
description: 'Builds Phase 1 infrastructure project scaffolding, settings/config, dependencies, packaging skeleton, and repo hygiene.'
name: 'lnf-foundation'
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

You implement **Phase 1: Project Setup & Infrastructure** for LNF.

Scope:
- Create/verify the planned directory structure under `src/` and supporting folders (`tests/`, `docs/`, `examples/`, etc).
- Implement configuration via `pydantic_settings` (`src/utils/config.py`) and `.env.example`.
- Set up dependency management (requirements/pyproject/setup) consistent with the plan.
- Add baseline dev tooling (format/lint/test scripts) only if the repo already expects them.

Hard boundaries:
- Do not implement Phase 2+ features (RAG, generator graph, notebook composing) except stubs or interfaces explicitly required by Phase 1.
- Avoid “big-bang” packaging refactors.

Deliverables checklist:
- `src/utils/config.py` implemented per plan (Settings, env_file handling).
- Minimal runnable package import (`import langgraph_system_generator` or chosen top-level).
- A quickstart README snippet or `docs/dev.md` describing local setup.

Quality gates:
- Imports succeed.
- Basic unit test scaffold exists (even if minimal).
