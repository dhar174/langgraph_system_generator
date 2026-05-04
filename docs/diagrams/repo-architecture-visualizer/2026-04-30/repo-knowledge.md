# langgraph_system_generator Codebase Knowledge

Generated: 2026-04-30

This docs-owned generated snapshot maps the current repository checkout. It is
grounded in the repo docs, MemoryBank files, source inspection, and the
generated architecture diagrams in this folder. It is checked in as maintainer
documentation, not as a one-off ignored output artifact.

Use `docs/diagrams/README.md` as the regeneration entry point when package,
module, or environment-variable relationships change.

## Evidence Sources

- `README.md`
- `docs/architecture.md`
- `docs/wiki/Architecture-Deep-Dive.md`
- `docs/diagrams/generator-stage-state-map.md`
- `memory-bank/projectbrief.md`
- `memory-bank/systemPatterns.md`
- `memory-bank/techContext.md`
- `memory-bank/progress.md`
- `setup.py`
- `requirements.txt`
- `.github/workflows/python-app.yml`
- `src/langgraph_system_generator/generator/graph.py`
- `src/langgraph_system_generator/generator/nodes.py`
- `src/langgraph_system_generator/generator/state.py`
- `src/langgraph_system_generator/api/server.py`
- `src/langgraph_system_generator/utils/config.py`
- `src/langgraph_system_generator/constants.py`

## Stack

- Primary language: Python, packaged from `src/` with `setuptools` in `setup.py`.
- Supported Python versions: `setup.py` declares `python_requires=">=3.10"` and
  classifiers for Python 3.10, 3.11, and 3.12.
- Console entry point: `lnf=langgraph_system_generator.cli:main`.
- Core dependencies: `pydantic`, `pydantic-settings`, and `python-dotenv`.
- Full generator dependencies: `langgraph`, `langchain`, `langchain-openai`,
  `langchain-community`, `nbformat`, `nbconvert`, `jupyter_client`,
  `nbclient`, `ipykernel`, `python-docx`, `reportlab`, `faiss-cpu`, `chromadb`,
  `sentence-transformers`, `aiohttp`, `beautifulsoup4`, `httpx`, FastAPI,
  Uvicorn, and SSE Starlette.
- Developer/test dependencies: `pytest`, `pytest-asyncio`, `pytest-cov`,
  `httpx-sse`, `black`, `ruff`, and `mypy`.
- CI parity: `.github/workflows/python-app.yml` installs Python 3.10,
  `requirements.txt`, `flake8`, `pytest-asyncio`, then runs flake8 syntax/error
  checks and `pytest --asyncio-mode=auto`.

## Structure

- `src/langgraph_system_generator/generator/`: outer LangGraph generator graph,
  node orchestration, typed state, registries, and runtime generator agents.
- `src/langgraph_system_generator/api/`: FastAPI app, static web UI mounting,
  artifact download guards, async generation, and SSE progress streaming.
- `src/langgraph_system_generator/notebook/`: notebook composition, runtime
  execution support, templates, and format exporters.
- `src/langgraph_system_generator/qa/`: static validation, deterministic repair
  registry, and repair engine.
- `src/langgraph_system_generator/rag/`: cached docs retrieval and vector-store
  access.
- `src/langgraph_system_generator/patterns/`: reusable generated LangGraph
  architecture patterns including router, subagents, hybrid, autoagent,
  critique loop, and explicit opt-in deepagents support.
- `src/langgraph_system_generator/repo_agent_bootstrap/`: contributor-facing
  AI guidance bootstrap implementation, separate from runtime product agents.
- `docs/`, `docs/wiki/`, and `memory-bank/`: public docs, wiki-style docs, and
  persistent repository context.
- `tests/`: pytest-based unit and integration coverage. `pytest.ini` sets
  `testpaths = tests` and `asyncio_mode = auto`.

## Architecture

- The product centers on a staged outer LangGraph workflow built by
  `create_generator_graph()` in `generator/graph.py`.
- The graph uses `GeneratorState` from `generator/state.py` as its shared
  integration contract.
- The current graph order is:
  prompt/config input -> intake -> RAG retrieval -> architecture selection ->
  graph design -> tooling plan -> notebook assembly -> static QA -> runtime QA
  -> optional repair -> package outputs -> graph end.
- `generator/nodes.py` bridges graph state to the specialized subsystems:
  runtime agents, RAG, notebook construction/export, and QA/repair.
- `package_outputs_node` writes final manifest state; the CLI/API export layer
  later uses `NotebookExporter` to emit artifact files.
- `generated_cells` is the authoritative notebook payload for a pass and is
  replaced by accepted repairs. `constraints` and `docs_context` accumulate;
  `qa_history` preserves attempt-by-attempt evidence.
- Runtime agents exported from `generator/agents/__init__.py` are
  `RequirementsAnalyst`, `ArchitectureSelector`, `GraphDesigner`,
  `ToolchainEngineer`, `NotebookComposer`, and `QARepairAgent`.

## Public Surfaces

- CLI: `lnf generate` and `lnf build-index`.
- API/web: `langgraph_system_generator.api.server:app` exposes `/`,
  `/health`, `/generate`, `/generate-async`, `/stream/{job_id}`, and
  `/artifacts`.
- Python package: reusable imports under `src/langgraph_system_generator/`.
- The same generation flow is intended to stay aligned across CLI, API/web, and
  package usage.

## Conventions

- Runtime generation changes should preserve stub-mode offline behavior.
- Live generation uses OpenAI-compatible model configuration; request-scoped
  overrides are represented by `GenerationConfig`.
- Runtime stage feedback is typed and advisory. Examples include
  `requirements_feedback`, `architecture_feedback`, `graph_design_feedback`,
  `tool_planning_feedback`, `notebook_composition_feedback`,
  `notebook_dependency_plan`, and `qa_repair_feedback`.
- Registries are favored over hardcoded branches for architecture selection,
  graph design, tool planning, notebook composition, and QA/repair extensions.
- Contributor-facing Copilot assets live under `.github/agents/`,
  `.github/skills/`, `.github/prompts/`, and `.github/instructions/`, and are
  separate from runtime product agents.

## Integrations And Configuration

- `Settings` in `utils/config.py` reads environment-backed project settings.
- Common live/run configuration includes `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`,
  `VECTOR_STORE_TYPE`, `VECTOR_STORE_PATH`, `DEFAULT_MODEL`, and
  `MAX_REPAIR_ATTEMPTS`.
- Internal plugin hooks include `GRAPH_DESIGNER_PLUGIN_MODULES`,
  `NOTEBOOK_COMPOSER_PLUGIN_MODULES`, `TOOLCHAIN_ENGINEER_PLUGIN_MODULES`, and
  `QA_REPAIR_PLUGIN_MODULES`.
- Output path safety is centralized in `constants.py`: `BASE_OUTPUT_DIR` is
  mainly for test isolation; production-facing `LNF_OUTPUT_BASE` must stay
  under the current working directory.
- API generation concurrency is bounded by `LNF_MAX_CONCURRENT_GENERATIONS`.
- SSE replay history is bounded by `LNF_MAX_EVENTS_PER_JOB`.
- Generated notebook templates can read notebook/runtime variables such as
  `WORKDIR`, `MODEL`, `OPENAI_API_KEY`, and `ANTHROPIC_API_KEY`.
- Deep Agents pattern code reads `DEEP_AGENTS_MODEL` and keeps the SDK optional
  through lazy notebook-facing imports.

## Testing

- Repository default: `pytest --asyncio-mode=auto`.
- CI test command: `pytest --asyncio-mode=auto`.
- Narrow unit loop documented in README: `python -m pytest tests/unit
  --asyncio-mode=auto -q`.
- Docs-only coverage path documented in README:
  `python -m pytest tests/unit/test_documentation_coverage.py -q`.
- Additional local checks documented by the repo include `black src/ tests/`,
  `ruff check src/ tests/`, and `mypy src/`.

## Known Concerns

- Live mode requires credentials unless a compatible custom endpoint/model path
  is provided.
- RAG retrieval is designed to degrade to empty context when the vector store is
  unavailable; this keeps generation running but can lower generation quality.
- SSE job state is in-memory and suited to single-server development rather
  than distributed production coordination.
- PDF export depends on local notebook conversion tooling and either webpdf or
  LaTeX support.
- Public docs and onboarding have historically needed active alignment with the
  runtime contract.
- `deepagents` is explicitly experimental and optional; core package imports
  should remain offline-friendly.

## Generated Diagram Inventory

All generated diagrams live in this docs folder and were emitted from
`<repo-architecture-visualizer-skill>/scripts/generate_repo_diagram.py`.

| Diagram | Scope | Kind | Granularity | Nodes | Edges | Files |
| --- | --- | --- | --- | ---: | ---: | --- |
| `repo-package-map` | `src` | mixed imports/env | package | 24 | 25 | `.mmd`, `.dot`, `.json`, `.figma.json` |
| `generator-module-map` | `src/langgraph_system_generator/generator` | mixed imports/env | module | 8 | 7 | `.mmd`, `.dot`, `.json`, `.figma.json` |
| `env-usage-map` | `src` | env reads | file | 21 | 15 | `.mmd`, `.dot`, `.json`, `.figma.json` |

Graphviz `dot` was not available on PATH during this run, so SVG rendering was
skipped. The Mermaid, DOT, JSON, and Figma-layout JSON sources are present and
editable.

## Regeneration Guidance

- Refresh this bundle with the local `repo-architecture-visualizer` skill after
  meaningful package, module, or environment-variable relationship changes.
- Keep refreshed outputs under
  `docs/diagrams/repo-architecture-visualizer/<date>/` so they remain part of
  the checked-in documentation set.
- Re-run the JSON count check after regeneration to confirm each emitted graph
  still contains nodes and edges.
