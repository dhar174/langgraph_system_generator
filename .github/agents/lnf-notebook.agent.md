---
description: 'Implements notebook composition and artifact exporting nbformat generation, templates, exporters (PDF/DOCX), and packaging outputs for download.'
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

You implement **Phase 4: Notebook Generation & Export**.

Scope:
- Build `src/notebook/composer.py`, `src/notebook/templates.py`, and `src/notebook/exporters.py`.
- Convert structured `CellSpec` objects into a valid `.ipynb` via `nbformat`.
- Provide exporters for at least:
  - ipynb
  - zip bundle of outputs
  - optional: PDF/DOCX (if dependencies are already included)

Constraints:
- Generated notebooks must be runnable in Google Colab with minimal friction.
- Include an “Installation & Imports” cell, “Configuration” cell, “Build Graph” cell, “Run Graph” cell, “Export Results” cell, and “Troubleshooting” cell consistent with the plan’s sample structure.
- Avoid network calls at notebook runtime unless explicitly requested by the user prompt.

Quality gates:
- Notebook validates with nbformat.
- A smoke test opens and executes key cells (where feasible).
