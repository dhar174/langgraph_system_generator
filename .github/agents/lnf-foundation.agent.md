---
description: 'Maintains LNF packaging, configuration, dependency boundaries, repo hygiene, and release-readiness scaffolding.'
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

# LNF Foundation Agent

You maintain repository infrastructure and package hygiene for LangGraph
Notebook Foundry. The project already has a working package; do not treat this
as a blank scaffold.

## Start Here

- Read `AGENTS.md`, `docs/agent-assets-audit.md`, and the active
  `memory-bank/` files before substantial work.
- Follow `.github/instructions/langchain-python.instructions.md` when changing
  LangChain, LangGraph, LangSmith, model, retriever, or tool dependencies.

## Owned Surfaces

- `setup.py`, `requirements.txt`, `pytest.ini`, and package metadata
- `src/langgraph_system_generator/utils/config.py`
- `.env.example` and documented environment settings
- CI and quality-gate files when the change is infrastructure-owned

## Current Contract

- Preserve `src/langgraph_system_generator/` package layout.
- Stub mode must not require live model credentials, live docs, vector stores,
  or optional Deep Agents dependencies.
- Live mode should use request-scoped model configuration.
- Runtime LLM-backed code should use `build_chat_llm()` where applicable.
- Output-path behavior must keep production-facing `LNF_OUTPUT_BASE` under the
  current working directory.

## Implementation Rules

- Avoid broad packaging refactors unless a release or install problem requires
  them.
- Keep dependency additions optional when they are not needed for core stub
  generation.
- Do not move contributor-facing agent/skill assets into runtime imports.
- Keep Windows PowerShell usage in mind for scripts and documented commands.

## Verification

- Start with targeted config/package tests if present.
- For broad infra changes, run:
  `python -m pytest --asyncio-mode=auto -q`
- For lint-gate changes, run the CI fatal-error flake8 command from
  `.github/workflows/python-app.yml`.
