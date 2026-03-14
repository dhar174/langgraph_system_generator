# AGENTS.md

## Overview

This repository turns a plain-language prompt into a runnable LangGraph-based multi-agent system. It combines prompt analysis, architecture selection, workflow design, notebook generation, QA repair, export pipelines, and a FastAPI web UI, while also bundling cached LangGraph/LangChain docs for offline-friendly retrieval.

## Folder Structure

- `src/langgraph_system_generator/api/`: FastAPI server, request/response models, and web entrypoints.
- `src/langgraph_system_generator/generator/`: Core generation pipeline that analyzes prompts and plans the system.
- `src/langgraph_system_generator/patterns/`: Reusable LangGraph architecture patterns such as routers and supervisor/subagent flows.
- `src/langgraph_system_generator/notebook/`: Notebook composition plus HTML, DOCX, PDF, and ZIP export helpers.
- `src/langgraph_system_generator/qa/`: Validation and repair logic for generated notebooks and artifacts.
- `src/langgraph_system_generator/rag/`: Cached-doc indexing and retrieval logic used to ground generation.
- `examples/`: Small runnable pattern demos.
- `tests/`: Regression coverage for patterns, generation, and export behavior.
- `docs/`: Human-facing implementation notes and feature guides.
- `.github/skills/`: Repo-local agent skills. Prefer these first when a task matches one of them.
- `.github/agents/`, `.github/instructions/`, `.github/prompts/`: Additional repo-local agent guidance and prompt assets.

## Core Behaviors and Patterns

- Preserve the distinction between `stub` mode and `live` mode. Changes to generation flow should not accidentally force live LLM calls in offline/stub workflows.
- Prefer existing pattern modules and cached docs over inventing new graph structures from scratch.
- Treat the generator as a pipeline: prompt analysis, architecture selection, workflow design, tool planning, notebook composition, QA validation/repair, and export.
- When changing RAG or retrieval behavior, keep offline-friendly cached-doc behavior intact and avoid introducing unnecessary network assumptions.
- When changing generation or pattern code, think through downstream effects on notebook validation, exports, the CLI, and the FastAPI app.

## Conventions

- Use repo-local skills from `.github/skills/` before falling back to global skills.
- Do not edit vendored skill contents unless the task is specifically about maintaining or improving a skill.
- Prefer targeted changes in existing modules over adding parallel implementations.
- Keep docs in sync when behavior changes in generation, QA, exports, or skill usage.
- When adding new project skills, place them under `.github/skills/<skill-name>/` and make the description specific enough for auto-discovery.

## Skill Guide

Use these repo-local skills when the request matches their scope:

- [`langgraph-project-setup`](./.github/skills/langgraph-project-setup/SKILL.md): creating a new LangGraph project, configuring `langgraph.json`, wiring provider settings, or fixing project scaffolding/config issues.
- [`langgraph-agent-patterns`](./.github/skills/langgraph-agent-patterns/SKILL.md): choosing or implementing supervisor/subagent, router, orchestrator-worker, or handoff coordination patterns.
- [`langgraph-state-management`](./.github/skills/langgraph-state-management/SKILL.md): designing graph state, reducers, persistence, checkpointing, or debugging state merge/update behavior.
- [`langgraph-error-handling`](./.github/skills/langgraph-error-handling/SKILL.md): retries, recovery loops, interrupt/resume flows, escalation, or `ToolNode` failure handling.
- [`langgraph-testing-evaluation`](./.github/skills/langgraph-testing-evaluation/SKILL.md): unit/integration tests, mocked runs, trajectory evaluation, regression checks, or LangSmith-backed evaluation.
- [`deepagents-setup-configuration`](./.github/skills/deepagents-setup-configuration/SKILL.md): Deep Agents setup, migration, validation, or configuration for LangChain/LangGraph-based deep-agent workflows.
- [`deepagents-planning-todos`](./.github/skills/deepagents-planning-todos/SKILL.md): `write_todos` planning, task decomposition, todo lifecycle debugging, or trace-based todo analysis.
- [`langsmith-fetch`](./.github/skills/langsmith-fetch/SKILL.md): quickly debugging LangGraph/LangChain runs by pulling recent LangSmith traces into the terminal.
- [`langsmith-trace`](./.github/skills/langsmith-trace/SKILL.md): adding tracing to code, querying/exporting traces, or instrumenting runs for diagnosis.
- [`langsmith-evaluator`](./.github/skills/langsmith-evaluator/SKILL.md): evaluator design, offline/online evaluation setup, or grading model/graph behavior.
- [`langsmith-dataset`](./.github/skills/langsmith-dataset/SKILL.md): creating, curating, or updating LangSmith datasets used for testing and evaluation.

Supporting repo-local skills that are often useful alongside the LangGraph set:

- [`langchain`](./.github/skills/langchain/SKILL.md): framework-level LangChain guidance and agent/reference material.
- [`openai-docs`](./.github/skills/openai-docs/SKILL.md): current OpenAI API and product documentation workflows.
- [`jupyter-notebook`](./.github/skills/jupyter-notebook/SKILL.md): notebook creation or cleanup when generated notebook artifacts need hands-on edits.
- [`webapp-testing`](./.github/skills/webapp-testing/SKILL.md): browser-based verification for the FastAPI web UI.

## Working Agreements

- Start by checking whether an existing repo-local skill already fits the task before improvising a workflow.
- For LangGraph runtime bugs, prefer `langsmith-fetch` or `langsmith-trace` plus the relevant LangGraph skill instead of debugging blind.
- For architecture questions, consult `langgraph-agent-patterns` before changing pattern implementations in `src/langgraph_system_generator/patterns/`.
- For generation regressions, pair code changes with `langgraph-testing-evaluation` and the relevant tests under `tests/`.
- If a task changes how agents or skills should be used in this repo, update this file and the relevant docs in `.github/instructions/` or `docs/`.
## Repository overview

LangGraph System Generator, also referred to in the docs as **LangGraph Notebook
Foundry (LNF)**, turns a natural-language prompt into a complete, runnable
LangGraph multi-agent system packaged as a Jupyter notebook plus supporting
artifacts.

The repository has three important surfaces:

- **CLI** via `lnf`
- **FastAPI + web UI** via `langgraph_system_generator.api.server:app`
- **Python package** under `src/langgraph_system_generator/`

The same core generation flow is reused across interfaces. In practice, both the
CLI and API route work through the shared generation/export path, and live mode
invokes the generator graph to assemble notebook artifacts.

## Agent types in this repository

There are two different "agent" concepts in this codebase. Keep them distinct
when making changes.

### Runtime product agents

These are the agents that participate in notebook/system generation and live
under `src/langgraph_system_generator/`.

Primary locations:

```text
src/langgraph_system_generator/generator/
src/langgraph_system_generator/generator/agents/
src/langgraph_system_generator/patterns/
src/langgraph_system_generator/rag/
src/langgraph_system_generator/qa/
src/langgraph_system_generator/notebook/
```

Examples include:

- `RequirementsAnalyst`
- `ArchitectureSelector`
- `GraphDesigner`
- `ToolchainEngineer`
- `NotebookComposer`
- `QARepairAgent`

These runtime agents move a request through the generation pipeline:

```text
prompt
  -> requirements analysis
  -> RAG retrieval
  -> architecture selection
  -> workflow design / tool planning
  -> notebook composition
  -> static QA
  -> runtime QA
  -> repair loop
  -> packaged artifacts
```

### Contributor-facing Copilot agents

These are repository instructions for AI coding assistants and live under:

```text
.github/agents/
.github/prompts/
.github/instructions/
.github/skills/
skills/
```

Use these when you are adding repository guidance, custom agent behavior, or
specialized contributor workflows.

Examples already present in this repo:

- `.github/agents/lnf-rag.agent.md`
- `.github/agents/lnf-generator.agent.md`
- `.github/agents/lnf-notebook.agent.md`
- `.github/agents/lnf-qa.agent.md`
- `.github/agents/lnf-docs.agent.md`

## Architecture map

Source code is organized under `src/langgraph_system_generator/`:

```text
src/langgraph_system_generator/
├── api/         FastAPI app, SSE/progress handling, web UI assets
├── cli.py       `lnf` entrypoint and shared generation/export logic
├── generator/   outer graph, state, nodes, sub-agents
├── notebook/    notebook composition and exporters
├── patterns/    reusable Router / Subagents / Critique-Revise patterns
├── qa/          validators and repair logic
├── rag/         doc caching, indexing, embeddings, retrieval
└── utils/       configuration and shared helpers
```

Key relationships to preserve:

- `setup.py` exposes `lnf=langgraph_system_generator.cli:main`
- CLI and API should remain aligned on outputs and mode behavior
- `stub` mode must stay offline-friendly
- `live` mode may depend on `OPENAI_API_KEY`
- generated notebooks should remain runnable in local Jupyter and Google Colab

## Setup commands

Use the documented local setup from `README.md`, `CONTRIBUTING.md`, and
`docs/wiki/Getting-Started.md`.

### Recommended environment setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

### Full and development installs

```bash
pip install -e ".[full]"
pip install -e ".[full,dev]"
```

### Environment configuration

```bash
cp .env.example .env
```

Common settings:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT`
- `VECTOR_STORE_TYPE`
- `VECTOR_STORE_PATH`
- `DEFAULT_MODEL`
- `MAX_REPAIR_ATTEMPTS`
- `DEFAULT_BUDGET_TOKENS`

Output paths are validated against the configured base directory. Prefer
repo-relative paths such as `./output/demo`.

- `LNF_OUTPUT_BASE` is a production-facing override for the base output
  directory, but it must still resolve **under the current working directory**
  or the application will reject it.
- `BASE_OUTPUT_DIR` is the broader override used primarily for test isolation;
  it is not a normal contributor setting and is mainly intended for pytest
  `tmp_path` workflows.

## Local development workflow

Use small, reviewable changes and keep docs, tests, and examples aligned with
public behavior.

### Common commands

Generate artifacts in stub mode:

```bash
lnf generate "Create a router-based chatbot" --output ./output/demo --mode stub
```

Generate in live mode:

```bash
lnf generate "Create a research assistant with multiple specialized agents" \
  --output ./output/research_system \
  --mode live
```

Build the documentation index:

```bash
python scripts/build_index.py
lnf build-index --cache ./data/cached_docs --store ./data/vector_store
```

Run the server locally:

```bash
export LNF_OUTPUT_BASE=$(pwd)
uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000 --reload
```

Basic API smoke test:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a customer support chatbot with routing",
    "mode": "stub",
    "output_dir": "./output/my_system",
    "formats": ["ipynb", "html", "docx", "zip"]
  }'
```

## Testing instructions

Run the smallest relevant test subset first.

### Common test commands

```bash
pytest tests/unit/ --asyncio-mode=auto -q
pytest tests/unit/ --asyncio-mode=auto -v
pytest tests/patterns/ -v
pytest --asyncio-mode=auto
pytest --cov=src --cov-report=annotate:cov_annotate --asyncio-mode=auto
```

### CI-parity checks

The main workflow in `.github/workflows/python-app.yml` currently runs:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install flake8 pytest-asyncio
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
pytest
```

If local results differ from CI, reproduce those commands exactly.

### Test conventions for agent-related code

These rules are explicitly documented in `CONTRIBUTING.md` and should be treated
as mandatory:

- Patch `ChatOpenAI` at the **fully qualified module import path** used by the
  specific agent under test
- Use `FakeEmbeddings` from `langchain_community.embeddings`
- Stub `DocsRetriever` calls instead of hitting FAISS or live docs retrieval
- Use `AsyncMock` for async functions and coroutines
- Keep default tests independent from live credentials

Example:

```python
monkeypatch.setattr(
    "langgraph_system_generator.generator.agents.notebook_composer.ChatOpenAI",
    MockLLM,
)
```

## Code style and implementation conventions

Use the repository standards from `CONTRIBUTING.md`.

### Formatting and linting

```bash
black src/ tests/
ruff check src/ tests/
mypy src/
```

### Style expectations

- Prefer fully typed Python code
- Keep imports grouped as standard library, third-party, then local imports
- Use Google-style docstrings for public classes and functions
- Keep changes narrow and avoid unrelated refactors
- Preserve offline-friendly behavior in `stub` mode unless the task requires
  changing it

For runtime agent changes, prefer structured, explicit data flow and avoid
hidden side effects between pipeline stages.

## Creating or modifying runtime product agents

When you add or modify generation agents under
`src/langgraph_system_generator/generator/agents/` or related pipeline modules:

1. Keep the agent's responsibility narrow and named after a single stage or
   concern
2. Make inputs and outputs explicit through shared state or structured objects
3. Preserve compatibility with both `stub` and `live` modes where applicable
4. Update tests in `tests/unit/` or `tests/patterns/`
5. Update user-facing docs when public outputs, flags, or generated artifacts
   change

Best practices:

- prefer deterministic fallbacks for stub mode
- keep prompts/configuration close to the owning agent
- surface recoverable failures into QA/repair rather than silently swallowing
  them
- preserve Colab/Jupyter notebook portability

## Creating or modifying contributor-facing Copilot agents

Custom Copilot agents live in `.github/agents/*.agent.md`.

Use the existing guidance in `.github/instructions/agents.instructions.md`.
Typical frontmatter fields include:

```yaml
---
description: 'What the agent is for'
name: 'Display Name'
tools: ['read', 'edit', 'search']
model: 'Claude Sonnet 4.5'
target: 'vscode'
infer: true
---
```

Conventions:

- choose the smallest tool set that can do the job
- write focused instructions for one specialty, not a generic catch-all
- use handoffs only when the next agent is a natural follow-up
- keep prompts actionable and path-specific
- prefer editing repo files directly instead of emitting long copy/paste blocks

When adding prompts or instructions:

- prompts live in `.github/prompts/*.prompt.md`
- instructions live in `.github/instructions/*.instructions.md`
- skills live in `.github/skills/`
- the repo also contains a top-level `skills/` directory for shared/mirrored
  skill resources used by some workflows

## Agent communication and lifecycle management

For runtime system agents:

- pass forward only the state needed by downstream stages
- keep stage boundaries clear: retrieval, selection, design, composition, QA,
  repair, packaging
- treat repair as a bounded retry loop controlled by
  `MAX_REPAIR_ATTEMPTS`
- do not introduce credential or network requirements into stub paths

For contributor-facing coding agents:

- state the objective, subsystem, and file paths up front
- use the most specialized repo agent available for the subsystem
- report exact commands used for validation
- keep change scope minimal and document any follow-up work

Recommended subsystem mapping for specialized repo agents:

| Area | Preferred agent |
| --- | --- |
| RAG / vector store | `@lnf-rag` |
| Generator graph / nodes | `@lnf-generator` |
| Notebook composition/export | `@lnf-notebook` |
| QA and repair | `@lnf-qa` |
| CLI and packaging | `@lnf-cli` |
| Documentation | `@lnf-docs` |
| Security-sensitive changes | `@lnf-security` |
| Web UI | `@lnf-webui` |

## Example use cases

### Example: add a new runtime generator agent

Use this when inserting a new stage into the generator pipeline:

1. add the agent implementation under
   `src/langgraph_system_generator/generator/agents/`
2. wire it into `generator/nodes.py` or the graph definition
3. add targeted tests under `tests/unit/`
4. update docs if the generated output or inputs change

### Example: add a new Copilot specialist agent

Use this when contributors need a focused automation helper:

1. create `.github/agents/<name>.agent.md`
2. define frontmatter, tools, and instructions
3. ensure the scope is narrow and testable
4. cross-reference related prompts/instructions if needed

### Example: document a new prompt workflow

1. add `.github/prompts/<name>.prompt.md`
2. make commands concrete and repository-specific
3. reference the relevant tests, docs, or agent files

## Build and release notes

Local package build sanity check:

```bash
python -m pip install build
python -m build
```

Publishing is wired through `.github/workflows/python-publish.yml`. If you touch
packaging, version metadata, or release behavior, validate the build locally
before opening a PR.

## Security notes

- never commit API keys or secrets
- keep `.env` usage local and use CI/environment secrets in automation
- preserve output-path validation in the API when changing export behavior
- prefer mocks and fake embeddings in tests over live network calls
- review workflow permission changes carefully

## Pull request guidance

Use `.github/PULL_REQUEST_TEMPLATE.md` and keep PRs focused.

Before requesting review:

- run the relevant tests locally
- update docs for public-facing behavior changes
- confirm new agent-related tests follow the mocking rules
- confirm no secrets or environment-specific paths are committed

## Troubleshooting

Package import issue:

```bash
pip install -e .
```

Missing full dependencies:

```bash
pip install -e ".[full,dev]"
```

Live mode credential issue:

- verify `.env`
- verify `OPENAI_API_KEY`
- rerun in `--mode stub` if you only need structural validation

Server startup issue:

```bash
export LNF_OUTPUT_BASE=$(pwd)
uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000 --reload
```

CI disagreement:

- rerun the exact commands from `.github/workflows/python-app.yml`
- check for test mocking mistakes before assuming a production code regression

Output path rejected:

- use a relative output path like `./output/demo`
- if needed, set `LNF_OUTPUT_BASE=$(pwd)` before running CLI or server commands

## Working rules for automated coding agents

When operating in this repository:

1. prefer small, surgical changes
2. preserve CLI/API/output alignment
3. update tests with behavior changes
4. update docs when commands, flags, outputs, or architecture expectations change
5. prefer specialized repo agents over generic ones
6. avoid introducing hidden network, credential, or path assumptions

When unsure, use `README.md`, `CONTRIBUTING.md`, `docs/wiki/Getting-Started.md`,
`docs/wiki/Architecture-Deep-Dive.md`, `IMPLEMENTATION_PLAN.md`, and the GitHub
workflow files as the source of truth.
