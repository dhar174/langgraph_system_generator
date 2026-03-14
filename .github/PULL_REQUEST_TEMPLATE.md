## TL;DR

<!-- One sentence describing what this PR does. -->

## Motivation

<!-- Why was this change necessary? Link to issue(s) if applicable: Closes #NNN -->

## What changed

<!-- Describe the change per subsystem. Delete headings that don't apply. -->

### generator/ (nodes, agents, graph)

### patterns/ (Router, Subagents, Critique-Revise, new patterns)

### rag/ (retrieval, embeddings, caching)

### qa/ (repair loop, validators)

### api/ (FastAPI routes, SSE streaming, web UI)

### notebook/ (composition, export formats)

### tests/

### docs/

### tooling / CI

## How to test

```bash
# Run the relevant tests — adjust paths as needed
pytest tests/unit/ --asyncio-mode=auto -v
```

<!-- List any required environment variables or setup steps, e.g.:
  - OPENAI_API_KEY is required for live-mode integration tests only.
  - Run `python scripts/build_index.py` if RAG index files changed. -->

## Breaking changes

<!-- List public interface or behaviour changes. Write "None" if there are none. -->

None

## Checklist

- [ ] Tests pass locally (`pytest --asyncio-mode=auto`)
- [ ] ChatOpenAI is patched at the **agent module level** in any new tests
- [ ] `DocsRetriever.retrieve_for_pattern` is stubbed in tests that touch RAG
- [ ] New code follows conventions in `docs/COPILOT_ADVANCED_WORKFLOWS.md`
- [ ] Documentation updated if public behaviour changed
- [ ] No hardcoded secrets or API keys

---

<!-- 💡 Copilot tip: run the `.github/prompts/langgraph-pr-summary.prompt.md` prompt
     to auto-generate a first draft of this description from your diff. -->
