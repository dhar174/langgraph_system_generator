# Product Context

## Problem / Why
- Building multi-agent LangGraph systems from scratch is complex; users need guided scaffolding with best practices and documentation.
- Offline environments need cached docs and stub generation without external calls.

## How It Should Work
- Accept a natural-language prompt (CLI/API/web form).
- Select patterns and architecture via RAG over cached LangGraph/LangChain docs.
- Compose notebook cells (plan, code, QA) and export to ipynb/html/docx/zip (optional PDF) in the chosen output directory.
- Provide manifest JSON (plan, cells, manifest) for programmatic consumption.
- Optional live mode uses OpenAI key; stub mode avoids network calls.

## User Experience Goals
- Fast start: single command `lnf generate "prompt" --output ./output/demo` works offline.
- Clear visibility: web UI shows progress bar, history, and download links.
- Safety: outputs stay under `LNF_OUTPUT_BASE`; no secrets checked in.
- Reliability: QA/Repair loop validates notebooks and fixes common issues.
