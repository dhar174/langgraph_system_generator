# Copilot Instructions

## Start every task with repository context

Before substantial work, read `.github/instructions/memory-bank.instructions.md`
and then review the active files under `memory-bank/` (`projectbrief.md`,
`productContext.md`, `activeContext.md`, `systemPatterns.md`, `techContext.md`,
`progress.md`, and `memory-bank/tasks/_index.md`). The MemoryBank is this
repository's persistent project context, so use it to recover architecture
history, active work, and task-level decisions across sessions.

On `/update memory bank`, refresh `activeContext.md` and `progress.md`.

Use `AGENTS.md` as the canonical reference for contributor-facing assets,
LangChain/LangGraph resources, skill mirrors, and runtime-agent workflow.

---

## Build, test, and lint commands

```bash
# Install (full + dev extras required for tests)
pip install -r requirements.txt
pip install -e ".[full,dev]"

# Run all tests
pytest --asyncio-mode=auto

# Unit tests only (fastest feedback)
pytest tests/unit/ --asyncio-mode=auto -q

# Single test
pytest tests/unit/test_generator_agents.py::TestRequirementsAnalyst -v --asyncio-mode=auto

# Pattern tests
pytest tests/patterns/ -v

# Format (run before committing)
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

`pytest.ini` sets `testpaths = tests` and `asyncio_mode = auto` — the `--asyncio-mode=auto`
flag is already covered when running from the repo root but is required if you
pass a single file path directly.

---

## Architecture overview

This is a **LangGraph-based notebook generator**. A natural-language prompt enters
a 9-stage linear pipeline and exits as a runnable Jupyter notebook plus exported
artifacts (HTML, DOCX, PDF, zip).

### Pipeline (defined in `generator/graph.py`)

```
intake → rag_retrieval → architecture_selection → graph_design →
tooling_plan → notebook_assembly → static_qa → runtime_qa
                                                      ↓ (conditional)
                                                  repair ←→ static_qa  (loop, max 3)
                                                      ↓ (exhausted or pass)
                                               package_outputs → END
```

Node functions live in `generator/nodes.py`. The graph is compiled by
`create_generator_graph()` in `generator/graph.py`. Conditional routing after
`runtime_qa` is handled by `should_repair()` and after `repair` by
`should_retry_after_repair()`.

### Shared state

All nodes communicate through `GeneratorState` (a `TypedDict` in
`generator/state.py`). Key behaviors:

- `constraints` and `docs_context` use named bounded reducers — they
  **accumulate** latest unique values across node calls without unbounded
  growth.
- `qa_history` is appended through bounded node helpers that preserve
  current-attempt blocking failures.
- `generated_cells` has **no reducer** (intentional last-write-wins). The repair
  loop replaces cells wholesale; never append to it from a node.
- `repair_attempts` counts loop iterations; the graph halts when it reaches
  `settings.max_repair_attempts` (default 3).

### Three surfaces

The same generation pipeline is exposed via:

- **CLI**: `lnf` entry-point (`src/langgraph_system_generator/cli.py`)
- **FastAPI**: `langgraph_system_generator.api.server:app` (run with uvicorn)
- **Python package**: import `generate_artifacts` from `cli.py` directly

### Two operating modes

- **Stub mode** (`--stub` / `mode="stub"`): fully offline, no `OPENAI_API_KEY`
  needed, uses deterministic patterns from the `patterns/` module.
- **Live mode**: requires `OPENAI_API_KEY`; calls real LLM; full pipeline runs.

### Three architecture types

`router` | `subagents` | `hybrid` — selectable via `generation_config.agent_type`
or inferred from prompt keywords in stub mode.

---

## Key conventions

### Agent construction pattern

Every runtime agent uses `build_chat_llm()` from
`generator/agents/_llm.py` and accepts `chat_openai_class` so tests can patch it:

```python
from langchain_openai import ChatOpenAI
from langgraph_system_generator.generator.agents._llm import build_chat_llm

class MyAgent:
    def __init__(self, model=None, model_config=None):
        self.llm = build_chat_llm(
            model=model,
            model_config=model_config,
            chat_openai_class=ChatOpenAI,   # module-local import — required for patching
        )
```

### Mocking rules (CI-enforced)

1. **Patch `ChatOpenAI` at the module-local path of the agent under test**, not globally:
   ```python
   @patch("langgraph_system_generator.generator.agents.requirements_analyst.ChatOpenAI")
   ```
2. Use `FakeEmbeddings` from `langchain_community.embeddings` — never call real embeddings.
3. Stub `DocsRetriever.retrieve` (node tests) or `DocsRetriever.retrieve_for_pattern`
   (ArchitectureSelector tests) — never hit real FAISS or live docs.
4. Use `AsyncMock` for any coroutine.

### Output path env vars

- `BASE_OUTPUT_DIR`: for test isolation with `tmp_path`; trusted directly, can be
  anywhere on disk. Set via `monkeypatch.setenv("BASE_OUTPUT_DIR", str(tmp_path))`.
- `LNF_OUTPUT_BASE`: production override; must resolve **under the current working
  directory** (enforced in `constants.py`). Do not use for tests.
- Default (neither set): `./output/` relative to CWD.

### Settings / dotenv behavior in tests

`utils/config.py` detects `"pytest" in sys.modules` and **skips dotenv loading**.
Unit tests never need `OPENAI_API_KEY`; all LLM calls are mocked. Do not add a
`.env` file to unblock tests — mock properly instead.

### Runtime QA pass-through

In `nodes.py`, runtime QA failures whose message starts with
`"Runtime validation unavailable"` are set to `passed=True`. This prevents
generation from blocking in environments without a running Jupyter kernel; treat
it as a warning, not an error.

### API server constraints

Supported advanced generation options: `model`, `temperature`, `max_tokens`,
`custom_endpoint`, `agent_type`. Unsupported roadmap fields such as
`memory_config`, `preset`, and `graph_style` are not part of the public API
contract and are rejected by request validation as unknown inputs.
Concurrency is capped at `LNF_MAX_CONCURRENT_GENERATIONS` (default 5, env-configurable).
All user-supplied `output_dir` values are resolved relative to the base output
directory (path-traversal protection).

### Code style

- **Formatter**: `black` — run `black src/ tests/` before committing.
- **Linter**: `ruff check src/ tests/`.
- **Types**: `mypy src/` — new code must be fully typed.
- **Imports**: stdlib → third-party → local, each group separated by a blank line.
- **Docstrings**: Google style for public functions and classes.

---

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
- `repo-agent-bootstrap` for repo-wide Copilot/Codex/Claude bootstrap or maintenance work

Mirrored top-level `skills/` entries currently exist for `langchain`,
`langsmith-dataset`, `langsmith-evaluator`, `langsmith-trace`, and
`repo-agent-bootstrap`.

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
