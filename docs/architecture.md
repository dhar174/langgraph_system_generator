<!-- repo-agent-bootstrap:file-kind=architecture-doc -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# Architecture

## Overview
`langgraph_system_generator` turns a natural-language prompt into notebook-based
LangGraph system artifacts through shared CLI, API, and package entry points.

This file is the deeper architecture companion to `AGENTS.md`. Keep always-on
contributor rules in root guidance and use this document for subsystem
relationships and maintenance notes.

## Core subsystems

### `src/langgraph_system_generator/generator/`
- Owns the outer generation graph, typed state, node orchestration, and
  generator agents.
- `GeneratorState` uses bounded reducers for accumulated constraints and docs
  context, plus bounded QA-history helpers for attempt evidence.
- `GraphDesigner` emits backward-compatible `workflow_design` plus canonical
  `graph_exports.schema` metadata for node IDs, edges, conditional branches,
  `Command` destinations, terminal nodes, guarded cycles, tool reachability,
  and compiled graph variable naming.

### `src/langgraph_system_generator/rag/`
- Handles retrieval against cached LangChain/LangGraph documentation and local
  vector indexes.
- Retriever/vector-store construction is process-local cached by vector-store
  path and shared by retrieval and architecture selection paths.

### `src/langgraph_system_generator/notebook/`
- Composes generated notebook cells and exports notebook artifacts to additional
  formats.
- Notebook graph cells render from canonical graph/spec metadata when present;
  architecture pattern templates remain the fallback when no canonical schema is
  available.
- Standalone pattern snippets stay self-contained with direct `ChatOpenAI(...)`
  initialization. Notebook-composed pattern cells explicitly opt into the
  generated `make_llm(...)` helper so model and API-base settings stay
  centralized in the config cell.

### `src/langgraph_system_generator/qa/`
- Performs static validation, bounded repair loops, and lightweight runtime QA
  reporting.
- Notebook validation can run in memory before repaired candidates are
  persisted.
- Static QA checks generated graph code against the embedded/exported graph
  contract and rejects node-cell LLM configuration that bypasses the centralized
  notebook helper.

### `src/langgraph_system_generator/api/`
- Exposes the generation workflow through FastAPI plus SSE progress streaming.
- Artifact manifests distinguish serialized notebook cell counts from raw
  generated cell specs, standalone files from ZIP-only members, and static
  validation from runtime smoke-test scope.

## Shared workflow surfaces
1. CLI via `lnf`
2. FastAPI and web UI via `langgraph_system_generator.api.server:app`
3. Python package entry points under `src/langgraph_system_generator/`

## Maintenance notes
- Preserve parity between CLI and API generation flows.
- Keep stub mode offline-friendly.
- Treat contributor-facing AI assets in `.github/` and `memory-bank/` as a
  separate maintenance surface from runtime generator code.
- Keep graph/spec truth aligned across generated notebook code, Mermaid/schema
  exports, manifests, and QA whenever graph design or notebook composition
  changes.
<!-- repo-agent-bootstrap:managed:end -->
