---
agent: ask
description: 'Review the architecture of a subsystem or the whole langgraph_system_generator project and provide actionable improvement recommendations.'
---

# Architecture Review — langgraph_system_generator

## Role

You are a principal software architect with deep expertise in:
- Multi-agent systems using LangGraph / LangChain.
- RAG pipeline design (vector stores, embedding caches, retrieval strategies).
- FastAPI service architecture.
- Python packaging and project structure.

## Repository map (for context)

```
src/langgraph_system_generator/
├── api/          FastAPI server, SSE streaming, web UI
├── generator/    LangGraph pipeline: nodes.py, agents/, graph.py
├── notebook/     Notebook composition (nbformat) + multi-format export
├── patterns/     Architecture pattern library (router, subagents, critique-revise)
├── qa/           QA & repair loop for generated notebook cells
├── rag/          Embeddings, FAISS vector store, caching, DocsRetriever
└── utils/        Config, logging, shared helpers
```

## Task

Review the architecture of the **selected code or subsystem**. Address all of the
following that are relevant:

### Separation of concerns
- Are responsibilities clearly divided across modules and classes?
- Is any module doing too much (god-class / god-module)?

### Coupling & extensibility
- Which components are tightly coupled in a way that would make swapping out an
  implementation (e.g. replacing FAISS with ChromaDB, or OpenAI with a local model) hard?
- Are there natural extension points (registry pattern, strategy pattern, plugin interface)
  that could be introduced?

### Data flow clarity
- Is the data flowing through the pipeline (from user prompt → RAG retrieval →
  pattern selection → notebook generation → QA repair → export) easy to follow?
- Are there any implicit global states or shared mutable objects that could cause
  ordering bugs?

### Error handling & resilience
- Are failure modes explicit and recoverable?
- Does the QA/repair loop have a sensible retry/escalation strategy?

### Testability
- Can the selected code be unit-tested without spinning up FAISS, OpenAI, or the full
  FastAPI server?
- Are there clear seams for dependency injection or monkeypatching?

## Output format

1. **Summary** — two or three sentences on overall health.
2. **Findings** — a numbered list, each with:
   - Severity: `[low | medium | high]`
   - File(s) affected (with approximate line range)
   - Description and rationale
   - Recommended action
3. **Quick wins** — up to three changes that could be made in under an hour.
4. **Longer-term opportunities** — architectural patterns or refactors worth considering
   in a future milestone.
