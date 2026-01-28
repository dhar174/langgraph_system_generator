# AGENTS.md

Agent-focused guide for working on `langgraph_system_generator`.

## Project Overview
- Builds complete LangGraph-based multi-agent systems from a single prompt.
- Outputs runnable Jupyter/Colab notebooks plus JSON manifests (plan, cells, manifest) and optional HTML/DOCX/ZIP bundles.
- Supports stub mode (offline, no API key) and live mode (LLM-backed) via CLI, API, and web UI.
- Includes pattern library (Router, Subagents, Critique-Revise) with high test coverage and a QA/Repair system for notebooks.
- Uses cached LangGraph/LangChain docs and optional FAISS/Chroma vector store.

## Repository Layout (agent map)
- `src/langgraph_system_generator/`: core generator, API, pattern library, QA/repair system.
- `src/langgraph_system_generator/api/static/`: web UI assets (index.html, style.css, app.js).
- `examples/`: runnable pattern demos (router, subagents, critique_revise).
- `docs/`: deep guides (patterns, QA_REPAIR_SYSTEM, WEB_DEPLOYMENT, CI_CD_WORKFLOWS, dev quickstart).
- `spec/`: architecture, process, data-contract specs.
- `tests/`: unit/integration/pattern tests; QA validators/repair tests.
- `data/cached_docs/`: precached LangGraph/LangChain docs; `data/vector_store/` holds FAISS index.
- `scripts/`: helpers (build_index.py, demos).
- `output/`: generated artifacts (ignored); set via `--output` or `LNF_OUTPUT_BASE`.
- Top-level references: README.md, SYSTEM_SPEC.md, UPDATED_LANGGRAPH_GUIDE.md.

## Setup
- Python >= 3.9.
- Create venv and install deps:
  ```bash
  python -m venv .venv
  source .venv/bin/activate  # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  ```
- Optional extras: `pip install .[full]` for generation + API deps, `pip install .[dev]` for lint/type/test tooling.
- Environment:
  - `.env` based on `.env.example` (create manually if missing).
  - `OPENAI_API_KEY` required only for live generation.
  - `LNF_OUTPUT_BASE` (default `.`) to control output root for API/web.
  - `VECTOR_STORE_PATH` (default `./data/vector_store`) for retrieval cache.

## Development Workflow
- Quick paths for agents:
  - References: see [README.md](README.md), [SYSTEM_SPEC.md](SYSTEM_SPEC.md), [UPDATED_LANGGRAPH_GUIDE.md](UPDATED_LANGGRAPH_GUIDE.md), [docs/patterns.md](docs/patterns.md), [docs/QA_REPAIR_SYSTEM.md](docs/QA_REPAIR_SYSTEM.md), [docs/WEB_DEPLOYMENT.md](docs/WEB_DEPLOYMENT.md), [docs/CI_CD_WORKFLOWS.md](docs/CI_CD_WORKFLOWS.md), specs under [spec/](spec).
  - Examples to copy/run: [examples/router_pattern_example.py](examples/router_pattern_example.py), [examples/subagents_pattern_example.py](examples/subagents_pattern_example.py), [examples/critique_revise_pattern_example.py](examples/critique_revise_pattern_example.py).
  - Tests to inspect: [tests/unit/test_patterns.py](tests/unit/test_patterns.py), [tests/integration](tests/integration), [tests/patterns](tests/patterns), [tests/unit/test_validators.py](tests/unit/test_validators.py), [tests/unit/test_repair.py](tests/unit/test_repair.py).

- CLI generation (stub by default):
  ```bash
  lnf generate "Create a router-based chatbot" --output ./output/demo --mode stub --formats ipynb html docx zip
  # live mode (requires OPENAI_API_KEY)
  lnf generate "Create a chatbot" --mode live --output ./output/demo
  ```
- Build offline vector index from cached docs (only if you need a fresh FAISS store):
  ```bash
  python scripts/build_index.py
  # or
  lnf build-index --cache ./data/cached_docs --store ./data/vector_store
  ```
- Run API + web UI (hot reload):
  ```bash
  uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000 --reload
  ```
  Access http://localhost:8000 for the web UI; use `POST /generate` for API (stub or live).
- Patterns and codegen: pattern generators live in `src/langgraph_system_generator/patterns`; prefer `generate_complete_example` helpers and consult docs/patterns.md for usage notes.
- QA/Repair loop: validators/repair agents in `src/langgraph_system_generator/qa`; see docs/QA_REPAIR_SYSTEM.md and tests for expected behaviors and repair limits.
- Import usage example:
  ```python
  import langgraph_system_generator
  ```

## Testing
- Run full suite: `python -m pytest`
- Pattern-only tests: `pytest tests/unit/test_patterns.py --cov=src/langgraph_system_generator/patterns`
- QA validators/repair: `pytest tests/unit/test_validators.py tests/unit/test_repair.py`
- Coverage: `pytest --cov=src/langgraph_system_generator --cov-report=term-missing`
- Tests live under `tests/unit`, `tests/integration`, and `tests/patterns`.

## Code Style & Quality
- Format: `black .`
- Lint: `ruff check .` (CI uses flake8 equivalent in python-app workflow).
- Type check: `mypy src`
- Keep generated artifacts out of git (`output/` is ignored). Favor small, targeted changes; preserve existing structure.

## Build & Deployment
- Local web/API: `uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000`
- Docker:
  ```bash
  docker build -t langgraph-system-generator .
  docker run -p 8000:8000 -e OPENAI_API_KEY=your_key -v $(pwd)/output:/app/output langgraph-system-generator
  ```
- Serverless option (Mangum) available; see docs/WEB_DEPLOYMENT.md for Heroku, AWS EC2, Render, Kubernetes, Compose, and Codespaces setups.

## Security & Secrets
- Never commit keys; use environment variables. Stub mode requires no external calls.
- Constrain output paths via `LNF_OUTPUT_BASE`; avoid arbitrary write locations.
- For production API/web, add auth, TLS, and optional rate limiting (see WEB_DEPLOYMENT.md example).

## CI/CD Expectations
- Workflows: CodeQL security scan, python-app (lint + pytest), diagram generation, wiki-from-code, PyPI publish on release.
- Jobs that modify `main` depend on CodeQL. Expect minimum permissions and pinned actions.

## PR Guidelines
- Run `ruff check .`, `black .`, `mypy src`, and `python -m pytest` before pushing.
- Keep outputs and large artifacts out of commits; ensure `output/` remains untracked.
- Align with existing CLI/API contracts; update docs when changing behavior.

## Troubleshooting
- Missing outputs: ensure `--output` directory exists and is writable; set `LNF_OUTPUT_BASE` for API/web.
- Live mode failures: verify `OPENAI_API_KEY` and provider limits.
- Vector store missing: rebuild with `python scripts/build_index.py`.
- Port conflicts: change `--port` for uvicorn or stop existing process on 8000.

## Key References
- README.md: feature overview, CLI examples.
- SYSTEM_SPEC.md and UPDATED_LANGGRAPH_GUIDE.md: system intent and architecture.
- docs/: pattern library, QA & repair system, web deployment, CI/CD workflows.
- Cached docs & retrieval:
  - Offline LangGraph/LangChain docs cached under `data/cached_docs/`; vector store at `data/vector_store/` (FAISS index).
  - To rebuild the FAISS store (only if needed): `lnf build-index --cache ./data/cached_docs --store ./data/vector_store` (stub embeddings, no API key) or `python scripts/build_index.py`.
  - At runtime, the generator’s RAG retrieves from the cached corpus; live internet fetches are not required, but can be found at `github.com/langchain-ai/docs`. For updated upstream docs, re-scrape externally, drop new files into `data/cached_docs/`, then rebuild the index.
  - Pattern-specific retrieval helpers live in `src/langgraph_system_generator/docs_retrieval/` (if present) and are wired via the generator state; inspect `docs_retriever` usage in `src/langgraph_system_generator` for query examples.
