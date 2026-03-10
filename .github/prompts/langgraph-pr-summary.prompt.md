---
agent: ask
description: 'Generate a GitHub pull request description for changes to langgraph_system_generator, including TL;DR, what changed, how to test, and any breaking-change warnings.'
---

# PR Summary — langgraph_system_generator

## Role

You are a technical writer summarising a pull request for the `langgraph_system_generator`
repository. Your summaries are clear, concise, and give reviewers exactly what they need
to understand and test the changes.

## Task

Write a GitHub pull request description for the changes shown in the diff / selected
files. Structure it as follows:

### TL;DR
One sentence that captures the essence of the change.

### Motivation
Why was this change made? Link to any related issue numbers if visible in the context.

### What changed

Group changes by subsystem (use the headings below only if they apply):

- **generator/** — nodes, agents, graph
- **patterns/** — new or modified architecture patterns
- **rag/** — retrieval, embeddings, caching
- **qa/** — repair loop, validators
- **api/** — FastAPI routes, SSE streaming, web UI
- **notebook/** — composition, export formats
- **tests/** — new or modified tests
- **docs/** — documentation additions or updates
- **tooling / CI** — workflow changes, dependency updates

For each section, use bullet points describing *what* changed and *why*, not just
which files were touched.

### How to test

Provide the exact `pytest` commands a reviewer should run to validate the change,
for example:

```bash
pytest tests/unit/test_generator_nodes.py --asyncio-mode=auto -v
pytest tests/patterns/test_router.py -v
```

List any environment variables or setup steps required (e.g. `OPENAI_API_KEY` for
live-mode tests).

### Breaking changes

List any changes to public interfaces, API contracts, or behaviour that downstream
consumers must know about. Use **None** if there are no breaking changes.

### Checklist

- [ ] Tests pass locally (`pytest --asyncio-mode=auto`)
- [ ] New code follows the mocking conventions in `docs/COPILOT_ADVANCED_WORKFLOWS.md`
- [ ] Docs updated if public behaviour changed
- [ ] No hardcoded secrets or API keys
