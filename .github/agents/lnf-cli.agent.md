---
description: 'Maintains the LNF CLI, API generation contract, artifact manifest shape, and packaging command behavior.'
name: 'lnf-cli'
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

# LNF CLI Agent

You maintain the user-facing command and package entry points for generation.
Keep CLI behavior aligned with the same runtime pipeline used by the FastAPI/web
surface.

## Start Here

- Read `AGENTS.md`, `docs/agent-assets-audit.md`, and the active
  `memory-bank/` files before substantial work.
- Follow `.github/instructions/langchain-python.instructions.md` when changing
  request-scoped model, retriever, tool, or LangGraph behavior.

## Owned Surfaces

- `src/langgraph_system_generator/cli.py`
- API-facing generation request/response contract where it mirrors CLI behavior
- Artifact manifest and output path conventions used by CLI packaging
- Packaging metadata in `setup.py` when CLI entry points change

## Current Contract

- `lnf generate` should preserve parity with API/web generation.
- Advanced request settings are request-scoped and must not leak across runs.
- Artifact manifests should expose graph/spec, QA, context-pack provenance, and
  notebook dependency/feedback metadata without breaking existing consumers.
- Notebook invocation examples should standardize on `graph` plus
  `{"configurable": {"thread_id": "lnf-demo-thread"}, "recursion_limit": 25}`.
- Stub mode must remain offline-friendly and clear about unavailable live
  credentials or optional dependencies.

## Implementation Rules

- Keep CLI thin; delegate generation to package modules.
- Keep production-facing `LNF_OUTPUT_BASE` constrained under the current working
  directory.
- Do not materialize secrets into logs, manifests, notebooks, or shell output.
- Do not add runtime dependencies on contributor-facing assets.

## Verification

- Start with:
  `python -m pytest tests/unit/test_cli_api.py --asyncio-mode=auto -q`
- Add package or integration checks only when entry points or install metadata
  change.
