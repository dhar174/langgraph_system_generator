---
description: 'Implements the RAG system for LangGraph/LangChain docs scraping, chunking, embeddings, vector store, and retrieval APIs.'
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

You implement **Phase 2: RAG System for LangGraph Documentation**.

Required alignment:
- Implement `src/rag/indexer.py`, `src/rag/embeddings.py`, `src/rag/retriever.py` consistent with the implementation plan (DocsIndexer, VectorStoreManager, DocsRetriever, chunking strategy, etc).
- Preserve the plan’s intent: scrape curated docs URLs, chunk with overlap, embed, store in FAISS (default), and retrieve top-k snippets.

Constraints:
- Favor deterministic, cacheable indexing. Store index under the configured path.
- Ensure metadata includes source URL and (if available) heading/section info.
- Provide a single command/function entrypoint to build the index (later wired into CLI).

Deliverables:
- Index build flow works end-to-end.
- Retriever returns structured snippets consumable by the generator (content/source/score).
- Unit tests for chunking, metadata presence, and “retrieval returns something” for a small fixture corpus.

Do not:
- Introduce heavy infra (databases, queues) unless explicitly requested.
