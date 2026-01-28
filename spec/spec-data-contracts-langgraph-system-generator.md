---
title: Data Contracts - LangGraph System Generator
version: 1.0
date_created: 2026-01-28
last_updated: 2026-01-28
owner: LangGraph System Generator Team
tags: [contracts, api, manifest, schema]
---

## Purpose

Define canonical payloads and artifact schemas for the LangGraph System Generator (LNF) across CLI, API, manifests, and generated notebook assets to ensure stability, compatibility, and testability.

## API Contract

- **Endpoint**: POST /generate
- **Request Body**
  - `prompt` (string, required)
  - `mode` (enum: "stub" | "live", required)
  - `output_dir` (string, required, writable path)
  - `formats` (array<string>, optional; default excludes pdf)
  - `model` (string, optional)
  - `temperature` (number, optional)
  - `max_tokens` (integer, optional)
  - `agent_type` (enum: router | subagents | hybrid | auto, optional)
  - `memory` (enum: none | checkpoint, optional)
- **Response 200**
  - `success` (bool)
  - `mode` (string)
  - `prompt` (string echo)
  - `manifest` (Manifest object)
  - `qa_reports?` (array<QAReport>)
- **Error Envelope (4xx/5xx)**
  - `success`: false
  - `error`: { `code`: string, `message`: string, `details?`: object }
  - `manifest?`: may be omitted or partial; never misleading paths.

## CLI Contract

- Command: `lnf generate "<prompt>" --output <dir> [--mode stub|live] [--formats ...] [--model ...] [--temperature ...] [--max-tokens ...] [--agent-type ...] [--memory ...]`
- Exit codes: 0 success; non-zero on validation/QA/packaging failure. Stdout prints manifest path; stderr prints structured error.

## Manifest Schema (manifest.json)

- `success` (bool)
- `mode` (string)
- `prompt` (string)
- `output_dir` (string, relative or absolute as provided)
- `artifacts` (object)
  - `notebook_path` (string, relative to output_dir)
  - `html_path` (string)
  - `docx_path` (string)
  - `pdf_path?` (string)
  - `zip_path` (string)
  - `plan_path` (string)
  - `cells_path` (string)
- `metadata` (object)
  - `timestamp` (ISO8601)
  - `model` (string)
  - `temperature?` (number)
  - `max_tokens?` (integer)
  - `agent_type?` (string)
  - `memory?` (string)
  - `citations?` (array<{ source: string, url?: string, snippet?: string }>)
  - `qa_status` (enum: pass | fail | partial)
  - `qa_reports_path?` (string)
  - `seed?` (integer when deterministic)

## Notebook Plan Schema (notebook_plan.json)

- `sections` (array)
  - Each: { `id`: string, `title`: string, `type`: markdown|code, `purpose`: string, `depends_on?`: array<string> }
- `ordering` (array<string>) referencing section ids
- `patterns` (array<string>) used (router, subagents, critique_loop, map_reduce, hil_approval)

## Generated Cells Schema (generated_cells.json)

- `cells` (array)
  - Each: { `cell_type`: markdown|code, `source`: string, `metadata`: object, `execution_count?`: integer }
- `nbformat` (integer)
- `nbformat_minor` (integer)
- `lint` (object): { `structure_valid`: bool, `required_sections_present`: bool, `notes`: array<string> }

## QA Report Contract (qa_reports)

- Array of:
  - `stage` (enum: static | runtime)
  - `status` (enum: pass | fail)
  - `details` (string or object)
  - `logs_path?` (string)
  - `timestamp` (ISO8601)

## Notebook Structural Requirements (embedded contract)

- Required sections (by title or tag): Intro, Configuration, State Schema, Tools, Graph Construction, Smoke Test, Export/Packaging, Troubleshooting.
- Configuration cell must expose: output_dir, mode, formats, model, temperature, max_tokens, recursion_limit.
- Smoke test cell must compile graph and run minimal invocation; record result in qa_reports.

## Vector Store Manifest (data/vector_store/manifest.json)

- `index_path` (string)
- `embedding_model` (string)
- `dimension` (integer)
- `doc_count` (integer)
- `created_at` (ISO8601)
- `sources` (array<{ url: string, checksum?: string, license?: string }>)

## Error Codes (suggested)

- `ERR_VALIDATION` (input missing/invalid)
- `ERR_MODE_UNAVAILABLE` (live mode without keys)
- `ERR_RETRIEVAL` (docs retrieval failed)
- `ERR_QA_STATIC` (static gate failed)
- `ERR_QA_RUNTIME` (runtime gate failed)
- `ERR_PACKAGING` (artifact write/zip failed)

## Backward/Forward Compatibility

- Add new manifest fields as optional with defaults; do not rename existing keys without version bump.
- Include `version` in manifest metadata when contracts change; update tests accordingly.
- Maintain stub-mode determinism for regression tests; changes must update golden files or fixtures.

## Validation Strategy

- JSON schema validation for manifest, plan, cells, and QA report objects during QA stage.
- Contract tests in CI: generate sample artifacts in stub mode, validate against schemas, ensure required sections exist in notebook.
- API contract tests: request/response shape validation including error envelopes.
