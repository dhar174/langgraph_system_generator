# System Patterns

## Architecture Overview
- Generator produces LangGraph-based workflows as notebooks. Outer pipeline selects architecture, designs state, plans cells, composes notebook, runs QA/repair, and exports artifacts.
- Interfaces: CLI (`lnf generate`, `lnf build-index`), FastAPI (`/generate`, `/health`), web UI (served from FastAPI static assets).

## Patterns
- Router Pattern: classify requests and dispatch to specialized routes; supports structured outputs and customizable routing logic.
- Subagents Pattern: supervisor delegates to subagents, loops until completion; supports tool-enabled agents and iteration caps.
- Critique-Revise Pattern: generate → critique → revise loop with scoring, thresholds, and max revisions.

## Components & Relationships
- Core library under `src/langgraph_system_generator/` with pattern generators, QA validators/repair, docs retrieval, notebook composer/exporter.
- Data layer: cached docs (`data/cached_docs`), vector store (`data/vector_store`) used by retrieval helpers.
- API layer: FastAPI server exposes generation endpoints and serves web UI.
- Output handling: artifacts written under configurable output base; manifests list paths for downstream use.

## Quality Gates
- QA validators check JSON structure, placeholders, required sections/imports, and graph compilation; repair agent performs bounded fixes and re-validates.

## Design Considerations
- Stub mode avoids external calls; live mode requires OpenAI key.
- Outputs constrained to `LNF_OUTPUT_BASE` to reduce path traversal risk.
- Tests cover patterns and QA components; follow black/ruff/mypy for quality.
