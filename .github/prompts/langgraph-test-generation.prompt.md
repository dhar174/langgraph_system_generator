---
agent: agent
description: 'Generate pytest unit tests for a selected function, class, or module in langgraph_system_generator, respecting the project mocking conventions.'
---

# Test Generation — langgraph_system_generator

## Role

You are a test engineer who knows the `langgraph_system_generator` test conventions
inside-out.

## Mocking conventions (must be followed exactly)

| What to mock | How |
|---|---|
| `ChatOpenAI` | Patch at the **agent module path** *before* the agent is instantiated, e.g. `generator.agents.notebook_composer.ChatOpenAI`. Never patch `langchain_openai.ChatOpenAI` globally. |
| OpenAI embeddings | Substitute with `FakeEmbeddings` from `langchain_community.embeddings`. |
| `DocsRetriever.retrieve` / `retrieve_for_pattern` | Monkeypatch to return `[]` to avoid real FAISS calls. |
| Async node functions | Use `AsyncMock` from `unittest.mock` for all coroutines. |
| Long-running I/O | Patch at the boundary (file system, HTTP) rather than deep inside helpers. |

## Test file conventions

- New node tests → `tests/unit/test_generator_nodes.py` or a new
  `tests/unit/test_<subsystem>.py`.
- Pattern assertion tests → `tests/patterns/test_<pattern_name>.py`.
- Agent tests → `tests/unit/test_generator_agents.py`.
- Use `pytest.mark.asyncio` only when not already covered by `asyncio_mode = auto`
  in `pytest.ini` (it is currently set to `auto`, so the marker is optional).

## Task

Generate `pytest` unit tests for the selected code. For each test:

1. Write a clear docstring explaining what the test validates.
2. Set up mocks **before** the system under test is instantiated or called.
3. Assert the specific output values or side-effects, not just "no exception was raised".
4. Cover at least one happy path and one failure / edge-case path.
5. Do not require a real `OPENAI_API_KEY` — all LLM calls must be mocked.

## Output format

Provide the full test file (or a clearly-delimited addition to an existing test file)
ready to run with `pytest --asyncio-mode=auto`.
