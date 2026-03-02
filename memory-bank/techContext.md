# Tech Context

## Stack
- Language: Python (>=3.9).
- Core libs: LangGraph, LangChain Core, FastAPI, uvicorn, nbformat/nbconvert, FAISS (vector store), ruff/black/mypy/pytest.
- Frontend: static HTML/CSS/JS served by FastAPI (no heavy framework noted).

## Environment & Config
- `.env` based on `.env.example`; `OPENAI_API_KEY` needed for live mode only.
- Key variables: `LNF_OUTPUT_BASE` (output root), `VECTOR_STORE_PATH` (default `./data/vector_store`), optional `DEFAULT_MODEL`.
- Output directory defaults to `./output` (ignored by git) and must exist/writable.

## Modes
- Stub mode (default): offline, uses cached docs and fake embeddings; no network calls.
- Live mode: set `OPENAI_API_KEY` and pass `--mode live` (CLI) or `"mode": "live"` (API). The generator will call the configured model for pattern selection, notebook composition, and other LLM steps. Outputs remain the same (ipynb/html/docx/zip/json), but generation quality may be higher due to real model responses. Cost and latency depend on the model; ensure budget limits via prompt constraints or model settings.

## Tooling
- CLI entrypoints: `lnf generate`, `lnf build-index`.
- API server: `uvicorn langgraph_system_generator.api.server:app --port 8000`.
- Docker: image builds with provided Dockerfile; run maps output volume and API key env vars.

## Constraints
- Live mode depends on OpenAI availability and costs; stub mode is offline.
- Keep secrets out of repo; prefer env vars.
- PDFs require extra dependencies (nbconvert webpdf or latex pipeline).

## Dependencies
- Requirements tracked in `requirements.txt`; optional extras via `.[full]` or `.[dev]` installs.
