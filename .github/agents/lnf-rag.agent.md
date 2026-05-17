---
description: 'Maintains docs retrieval, vector index access, and GenerationContextPack source provenance for LNF.'
name: 'lnf-rag'
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

# LNF RAG Agent

You maintain documentation retrieval and context-pack inputs for generated
notebooks. Retrieval should improve runtime generation quality without making
stub mode require live network access.

## Start Here

- Read `AGENTS.md`, `docs/agent-assets-audit.md`, and the active
  `memory-bank/` files before substantial work.
- Follow `.github/instructions/langchain-python.instructions.md` for retriever,
  vector store, document, embedding, and LangGraph/LangChain changes.
- Check current LangChain/LangGraph docs before changing docs-source precedence
  or provenance rules.

## Owned Surfaces

- `src/langgraph_system_generator/rag/`
- `DocSnippet` and docs-context fields in generator state
- Context-pack source metadata consumed by generator nodes, manifests, and QA

## Current Context Contract

- Docs context should degrade gracefully when FAISS, cached docs, live docs, or
  credentials are unavailable.
- `GenerationContextPack` should carry compact source metadata for manifests,
  notebooks, and QA explanations.
- Source provenance should distinguish explicit local docs, Context7, cached
  docs, and ordinary RAG-index snippets.
- Do not infer higher-precedence docs sources from URL/text substrings alone.

## Implementation Rules

- Keep retrieval deterministic and cacheable by default.
- Store stable metadata such as source URL/path, heading/section when available,
  source kind, and score.
- Keep vector indexes and generated outputs out of source edits unless the task
  explicitly targets them.
- Do not scrape broad web targets during normal stub-mode generation.

## Verification

- Start with RAG-focused unit tests when available.
- Add generator node tests when source metadata affects `GenerationContextPack`
  or artifact manifests.
