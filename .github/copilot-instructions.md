# Copilot Instructions

## Start every task with repository context

Before substantial work, read `.github/instructions/memory-bank.instructions.md`
and then review the active files under `memory-bank/` (`projectbrief.md`,
`productContext.md`, `activeContext.md`, `systemPatterns.md`, `techContext.md`,
`progress.md`, and `memory-bank/tasks/_index.md`). The MemoryBank is this
repository's persistent project context, so use it to recover architecture
history, active work, and task-level decisions across sessions.

Use `AGENTS.md` as the canonical reference for contributor-facing assets,
LangChain/LangGraph resources, skill mirrors, and runtime-agent workflow.

## LangChain, LangGraph, and LangSmith documentation workflow

For LangChain-, LangGraph-, and LangSmith-specific questions, start with the
built-in LangChain docs MCP entry point:
`docs-langchain-search_docs_by_lang_chain`.

Use it first for official examples, API surface discovery, troubleshooting, and
pattern lookup. For Python implementation details, follow
`.github/instructions/langchain-python.instructions.md`. Use Context7 or web
search when the topic is outside the LangChain ecosystem or needs broader
package/version research.

## Relevant repository skills and mirrors

Prefer these repository skills when applicable:

- `langchain`
- `langgraph-agent-patterns`
- `langgraph-error-handling`
- `langgraph-project-setup`
- `langgraph-state-management`
- `langgraph-testing-evaluation`
- `langsmith-dataset`
- `langsmith-evaluator`
- `langsmith-fetch`
- `langsmith-trace`

Mirrored top-level `skills/` entries currently exist for `langchain`,
`langsmith-dataset`, `langsmith-evaluator`, and `langsmith-trace`.

## Reference links

- LangChain docs: https://python.langchain.com/docs/
- LangChain API reference: https://python.langchain.com/docs/api_reference
- LangGraph docs (legacy redirect): https://langchain-ai.github.io/langgraph/
- LangGraph API reference (legacy redirect): https://langchain-ai.github.io/langgraph/reference/
- Current LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- Current LangGraph "Use the Graph API" guide: https://docs.langchain.com/oss/python/langgraph/use-graph-api
- Current unified LangChain ecosystem API reference:
  https://reference.langchain.com/python/
- LangSmith docs: https://docs.langchain.com/langsmith
- MCP docs: https://modelcontextprotocol.io/docs
- VS Code MCP server guide:
  https://code.visualstudio.com/docs/copilot/chat/mcp-servers
