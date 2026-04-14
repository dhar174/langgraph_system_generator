---
title: Architecture Specification - LangGraph System Generator
version: 1.0
date_created: 2026-01-28
last_updated: 2026-01-28
owner: LangGraph System Generator Team
tags: [architecture, langgraph, generator, notebook]
---

# Introduction

This document defines the architecture specification for the LangGraph System Generator (LNF), a pipeline that transforms a user prompt into a fully runnable, production-grade LangGraph workflow packaged as a Jupyter notebook and supporting artifacts.

## 1. Purpose & Scope

Describe the required architecture, quality bars, and interfaces for generating LangGraph-based multi-agent workflows. Scope includes generator behavior (outer graph), produced workflow characteristics (inner graph), packaging formats, and quality gates. Assumes operation in both stub (offline) and live (LLM-enabled) modes.

## 2. Definitions

- LNF: LangGraph Notebook Foundry, the system generator.
- Outer graph: The LangGraph workflow that performs generation (planning, retrieval, assembly, QA, packaging).
- Inner graph: The LangGraph workflow emitted into the generated notebook.
- Stub mode: Deterministic, offline generation using cached docs and fake embeddings (no remote LLM calls).
- Live mode: Full generation using provider LLM APIs and embeddings.
- Pattern library: Reusable graph topologies (router, subagents, critique-revise, map-reduce, etc.).
- Artifacts: Generated outputs (ipynb, html, docx, pdf, zip, manifest, plan, cells).

## 3. Requirements, Constraints & Guidelines

- **REQ-001**: Accept a single project prompt plus optional constraints (formats, mode, budgets, environment) and persist them in generator state.
- **REQ-002**: Select graph pattern(s) using RAG over LangGraph/LangChain docs; justify chosen architecture in generated outputs.
- **REQ-003**: Produce a runnable notebook that builds and executes the inner graph end-to-end, including a smoke-test cell that compiles and runs the graph.
- **REQ-004**: Emit structured artifacts: `notebook.ipynb`, `manifest.json`, `notebook_plan.json`, `generated_cells.json`, `notebook.html`, `notebook.docx`, optional `notebook.pdf`, and `notebook_bundle.zip`.
- **REQ-005**: Include citations or rationale snippets for design choices sourced from the docs retrieval stage.
- **REQ-006**: Support stub and live modes; default to stub when API keys are absent.
- **REQ-007**: Enforce quality gates: static validation (structure, required sections) and runtime QA (compile and minimal invoke) before packaging.
- **REQ-008**: Outer state schema must capture prompt, constraints, selected patterns, docs_context, plan, generated_cells, qa_reports, artifacts_manifest, repair_attempts.
- **REQ-009**: Provide pattern coverage for router, subagents supervisor, critique→revise loop, map-reduce fan-out, and human-in-the-loop approval edges.
- **REQ-010**: Use nbformat to assemble notebooks programmatically; avoid deprecated LangGraph APIs by preferring current `StateGraph`/`Command`/`Send` primitives and `create_agent` where advised.
- **REQ-011**: Package outputs to a user-specified directory and ensure paths in manifests are relative to that directory.
- **REQ-012**: Provide CLI (`lnf generate`, `lnf build-index`) and FastAPI endpoints (`POST /generate`) with equivalent capabilities.
- **REQ-013**: Render web UI that mirrors CLI/API options for mode, formats, model selection, and advanced parameters.
- **REQ-014**: Guardrails: fail fast on missing required inputs, invalid formats, or unsupported mode combinations; return structured error payloads.
- **REQ-015**: Persistence options: default `InMemorySaver` for dev; expose pluggable checkpointing for SQLite/Postgres in inner graphs when requested.
- **SEC-001**: Do not log secrets (API keys); load from environment and redact in outputs.
- **CON-001**: Maintain offline operation in stub mode without network calls; rely solely on cached docs and fake embeddings.
- **CON-002**: Generated notebooks must remain provider-agnostic except for explicitly selected model/tool integrations.
- **GUD-001**: Prefer additive reducers and TypedDict/Pydantic state definitions for clarity; document state keys in notebook.
- **GUD-002**: Keep generated code deterministic in stub mode to support repeatable tests.
- **GUD-003**: Document configuration knobs (temperature, max tokens, retries, checkpointing) in the notebook introduction.

## 4. Interfaces & Data Contracts

- **CLI**: `lnf generate <prompt> [--mode stub|live] [--output DIR] [--formats ipynb html docx pdf zip] [--model MODEL] [--temperature FLOAT] [--max-tokens INT] [--agent-type router|subagents|hybrid] [--memory checkpoint|none]`.
- **API**: `POST /generate` with JSON body `{ prompt: str, mode: str, output_dir: str, formats: list[str], model?: str, temperature?: float, max_tokens?: int, agent_type?: str, memory?: str }`. Response includes success flag, mode, prompt echo, and manifest paths.
- **Outputs Manifest**: JSON with keys `notebook_path`, `html_path`, `docx_path`, `pdf_path?`, `zip_path`, `plan_path`, `cells_path`, `metadata` (model, mode, timestamp, seed, citations).
- **Notebook Structure**: Intro/context, requirements parsing, docs retrieval record, architecture plan, state schema, tool definitions, graph construction, smoke test, troubleshooting, export helpers.
- **State Schema**: Outer generator state keys in REQ-008; inner graph state must be defined per pattern with reducers and type hints.

## 5. Acceptance Criteria

- **AC-001**: Given a prompt and `--mode stub`, when `lnf generate` runs, then a notebook and JSON artifacts are produced without external API calls and the smoke-test cell executes successfully.
- **AC-002**: Given a prompt and `--mode live` with valid API keys, when generation completes, then the notebook builds an inner graph that compiles and invokes with real LLM calls, and the manifest lists all requested formats.
- **AC-003**: Given a request for router pattern, when the notebook is opened, then the inner graph uses `StateGraph` with conditional edges or `Command`/`Send` nodes for routing and includes documented state keys.
- **AC-004**: Given missing required input (e.g., prompt is empty), when CLI or API is called, then the system returns a structured error and no artifacts are written.
- **AC-005**: Given a generated notebook, when linting/structure validation runs, then required sections (intro, state schema, pattern rationale, QA steps, troubleshooting) are present.

## 6. Test Automation Strategy

- **Test Levels**: Unit (state reducers, planners, serializers), Integration (generator workflow, manifest production), End-to-End (CLI/API invocation producing artifacts), UI smoke (web form submission in stub mode).
- **Frameworks**: pytest for Python; Playwright for UI smoke (optional); nbformat checks for notebook integrity.
- **Test Data Management**: Use cached docs and fake embeddings for deterministic stub-mode fixtures; isolate output directories per test run.
- **CI/CD Integration**: Run `python -m pytest` in CI; add job to compile generated notebook from a sample prompt and run its smoke-test cell in stub mode.
- **Coverage Requirements**: ≥80% for generator modules; critical paths (state assembly, notebook writer, manifest builder) must be covered.
- **Performance Testing**: Monitor generation time for stub mode (<60s for sample prompt) and artifact sizes; ensure memory use remains bounded when building indexes.

## 7. Rationale & Context

The generator must stay aligned with the latest LangGraph guidance; RAG over official docs ensures recommended APIs (`StateGraph`, `Command`, `Send`, `create_agent`) are used instead of deprecated patterns. Stub mode guarantees offline repeatability and safer CI. Packaging multiple formats enables varied consumption (execution, review, print). QA gates catch structural/runtime issues before distribution.

## 8. Dependencies & External Integrations

### External Systems
- **EXT-001**: LLM providers (OpenAI/Anthropic/etc.) for live-mode generation and evaluation calls.

### Third-Party Services
- **SVC-001**: LangSmith (optional) for tracing and evaluation if configured.

### Infrastructure Dependencies
- **INF-001**: FAISS (or equivalent) vector store for cached docs retrieval; stored under `data/vector_store`.
- **INF-002**: Optional checkpointing backends (SQLite/Postgres) for inner graphs when persistence is requested.

### Data Dependencies
- **DAT-001**: Cached documentation chunks (`data/cached_docs/documents.json`) and vector index manifest.

### Technology Platform Dependencies
- **PLT-001**: Python 3.10+; nbformat for notebook assembly; FastAPI/Uvicorn for API; LangGraph/LangChain libraries.

### Compliance Dependencies
- **COM-001**: Redaction of secrets and adherence to data handling guidelines; no PII persisted in artifacts unless explicitly provided by user.

## 9. Examples & Edge Cases

```code
# Stub-mode CLI invocation
lnf generate "Create a router-based customer support agent" --mode stub --output ./output/demo --formats ipynb html docx zip

# Live-mode API request (requires API key set in environment)
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarize research papers with critique loop", "mode": "live", "output_dir": "./output/live_demo", "formats": ["ipynb", "html", "zip"]}'
```

Edge cases: missing prompt (reject request), unsupported format flag (error), no API key in live mode (fallback or explicit failure), large prompt (enforce truncation/validation), doc cache missing (instruct user to rebuild index).

## 10. Validation Criteria

- Specification sections are complete and traceable to requirements IDs.
- Generated sample notebook in stub mode compiles and passes smoke-test cell.
- Manifests reference existing files and relative paths under the output directory.
- QA reports are stored in generator state when failures occur.
- Pattern selection rationale includes citations from retrieved docs.

## 11. Related Specifications / Further Reading

- SYSTEM_SPEC.md (overall product goals)
- UPDATED_LANGGRAPH_GUIDE.md (latest LangGraph guidance)
- docs/wiki/Architecture-Deep-Dive.md (internal architecture details)
- LangChain docs: https://docs.langchain.com
- LangChain Python API reference: https://reference.langchain.com/python
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
