---
description: 'Maintains notebook composition, graph rendering, artifact exports, and runnable generated notebook contracts.'
name: 'lnf-notebook'
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

# LNF Notebook Agent

You maintain generated notebook assembly and artifact export behavior. Generated
notebooks are runtime product outputs; contributor-facing agents and skills may
document the contract but must not become runtime dependencies.

## Start Here

- Read `AGENTS.md`, `docs/agent-assets-audit.md`, and the active
  `memory-bank/` files before substantial work.
- Follow `.github/instructions/langchain-python.instructions.md` when notebook
  code includes LangChain, LangGraph, LangSmith, retrievers, tools, or
  evaluation examples.
- Check current LangGraph docs for `StateGraph`, reducers, `Command`, tool
  execution, persistence config, and invocation config semantics.

## Owned Surfaces

- `src/langgraph_system_generator/generator/agents/notebook_composer.py`
- `src/langgraph_system_generator/generator/notebook_composer_registry.py`
- `src/langgraph_system_generator/notebook/`
- Generated artifact manifest fields related to notebooks and exports

## Current Notebook Contract

- `NotebookComposer.compose_notebook()` returns `NotebookCompositionResult`.
- `generated_cells` remains the authoritative backward-compatible cell payload.
- Generated notebooks standardize on compiled variable `graph`.
- Invocation examples should use config shaped like
  `{"configurable": {"thread_id": "lnf-demo-thread"}, "recursion_limit": 25}`.
- State examples should preserve reducer semantics, especially messages through
  `MessagesState` or `Annotated[..., add_messages]`.
- Nodes should return partial state updates unless a full overwrite is
  intentional and explicitly justified.
- Tool claims must match a reachable execution path: deterministic node call,
  `ToolNode`, manual tool loop, `langchain.agents.create_agent`, or explicit
  demo-only omission. Treat `create_react_agent` as legacy compatibility, not
  the default for new generated notebooks.
- Configuration cells should centralize `ChatOpenAI` construction through the
  generated `make_llm(...)` helper and avoid hardcoded credentials.
- Prose, Mermaid/schema exports, Python graph construction, manifests, and QA
  explanations should render from the same validated graph/spec metadata.

## Implementation Rules

- Keep deterministic pattern builders ordered and synchronous.
- Preserve stable final cell ordering even when async helper generation is used.
- Surface fallbacks through notebook comments and composition feedback instead
  of silent placeholder behavior.
- Preserve notebook portability for local Jupyter and Google Colab.
- Avoid network calls at notebook runtime unless explicitly requested by the
  generated system prompt and represented honestly in tool metadata.

## Verification

- Start with:
  `python -m pytest tests/unit/test_generator_notebook_composer.py --asyncio-mode=auto -q`
- Add `tests/patterns/ -v` when pattern rendering changes.
- Use `nbformat` validation or existing notebook smoke helpers for export-shape
  changes.
