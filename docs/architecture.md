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

### `src/langgraph_system_generator/rag/`
- Handles retrieval against cached LangChain/LangGraph documentation and local
  vector indexes.

### `src/langgraph_system_generator/notebook/`
- Composes generated notebook cells and exports notebook artifacts to additional
  formats.

### `src/langgraph_system_generator/qa/`
- Performs static validation, bounded repair loops, and lightweight runtime QA
  reporting.

### `src/langgraph_system_generator/api/`
- Exposes the generation workflow through FastAPI plus SSE progress streaming.

## Shared workflow surfaces
1. CLI via `lnf`
2. FastAPI and web UI via `langgraph_system_generator.api.server:app`
3. Python package entry points under `src/langgraph_system_generator/`

## Maintenance notes
- Preserve parity between CLI and API generation flows.
- Keep stub mode offline-friendly.
- Treat contributor-facing AI assets in `.github/` and `memory-bank/` as a
  separate maintenance surface from runtime generator code.
<!-- repo-agent-bootstrap:managed:end -->
