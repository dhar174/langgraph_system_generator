---
title: Process Specification - LangGraph System Generator
version: 1.0
date_created: 2026-01-28
last_updated: 2026-01-28
owner: LangGraph System Generator Team
tags: [process, governance, qa, workflow]
---

## Purpose

Define the standard operating process for the LangGraph System Generator (LNF) from intake to packaged artifacts, including roles, checkpoints, quality gates, and fallback procedures for stub and live modes.

## Scope

Covers the outer generation workflow only (intake → RAG → planning → notebook assembly → QA → packaging). Excludes inner-graph business logic of generated notebooks except where QA/packaging requirements apply.

## Process Flow (happy path)

1. **Intake & Validation**
   - Inputs: prompt, mode (stub|live), formats, output_dir, optional model/temperature/agent_type/memory.
   - Validate required fields, allowed formats, output_dir writability; fail fast with structured errors.
2. **Constraint Parsing**
   - Extract goals, deliverables, constraints, runtime limits into structured state.
3. **Docs Retrieval (RAG)**
   - Query cached docs/vector index; capture citations for later embedding in rationale cells.
4. **Pattern & Architecture Selection**
   - Choose router/subagents/hybrid/critique-map-reduce pattern; record rationale and citations.
5. **State & Tool Plan**
   - Define outer and inner state schemas, reducers, tool lists, persistence choice (`InMemorySaver` for dev; SQLite/Postgres optional).
6. **Notebook Assembly**
   - Programmatically emit cells: intro, config, state/tools, graph build, demo/smoke, export helpers, troubleshooting.
7. **Static QA**
   - Validate notebook structure, required sections present, manifests consistent, formats list honored.
8. **Runtime QA**
   - Compile graph and execute smoke test (stub: deterministic; live: minimal invoke). Capture qa_reports with pass/fail and logs.
9. **Packaging**
   - Write artifacts (ipynb, html, docx, pdf optional, zip, manifest, plan, generated_cells) under output_dir with relative paths.
10. **Reporting**
    - Return manifest and QA status; include citations/rationale in manifest metadata when available.

## Roles & RACI (logical, may be automated agents)

- **Requirements Analyst**: Intake, validation, constraint parsing (R/A).
- **Docs Researcher**: Retrieval and citation capture (R/A).
- **Architecture Selector**: Pattern decision and rationale (R/A).
- **Graph Designer**: State, nodes, edges definition (R/A).
- **Notebook Composer**: Cell assembly and formatting (R/A).
- **QA & Repair Agent**: Static/runtime QA, repair loop (R/A).
- **Packager**: Artifact bundling and manifest generation (R/A).

## Quality Gates & Exit Criteria

- **Entry**: Valid input, writable output_dir, supported mode/format.
- **Static Gate**: Notebook sections present, manifests reference existing files, no placeholder TODOs, citations attached when retrieval ran.
- **Runtime Gate**: Graph compiles and smoke test completes; failures trigger repair loop up to configured limit.
- **Exit**: Manifest emitted with success flag, QA reports attached, artifacts written; on failure, structured error plus partial artifacts (logs, QA reports) may persist for debugging.

## Modes & Branching

- **Stub Mode**: No external LLM calls; use fake embeddings and cached docs; deterministic outputs; skip live-only steps.
- **Live Mode**: Use provider LLMs; require API keys; may run reduced smoke path on rate-limit or quota errors with explicit warning.
- **Fallbacks**: If live mode lacks keys, either fail fast or downgrade to stub (configurable, default fail fast to avoid silent behavior changes).

## Error Handling & Recovery

- Input errors: return structured error envelope with code, message, and invalid fields; no artifacts written.
- Retrieval failures: surface warning; proceed with last-known docs if available; mark rationale as partial.
- QA failures: invoke repair loop; if still failing, emit QA report and fail the run.
- Packaging failures: abort packaging, return error envelope and partial QA logs; never emit misleading manifest.

## Performance & SLAs (target)

- Stub mode end-to-end: <= 60s for reference prompt on standard dev machine.
- Live mode: bounded by provider latency; still run static QA even if runtime QA skipped due to quota.
- Resource caps: configurable recursion_limit for graph execution; bounded memory use when loading vector index.

## Audit & Observability

- Log structured events per phase with timestamps and mode.
- Optional LangSmith tracing when keys provided; redact secrets in logs and artifacts.
- Persist QA reports in generator state and manifest metadata.

## Deliverables

- Required artifacts: notebook.ipynb, manifest.json, notebook_plan.json, generated_cells.json, notebook.html, notebook.docx, notebook_bundle.zip; pdf optional.
- Manifest must include: success flag, mode, prompt echo, output_dir-relative paths, timestamps, model/config used, citations summary, QA status.

## Dependencies & Preconditions

- Cached docs present for stub mode; vector_store manifest readable.
- Output directory exists or is creatable.
- Environment variables for live mode (e.g., OPENAI_API_KEY) if selected.

## Change Management

- Any process change must update this spec and the architecture spec; accompany with tests or validation updates.
- Record deviations in release notes and QA reports.
