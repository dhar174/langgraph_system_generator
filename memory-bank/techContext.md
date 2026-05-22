## Technology Stack

- Python package with source under `src/langgraph_system_generator/`
- Core workflow libraries: `langgraph`, `langchain`, `langchain-openai`,
  `langchain-community`
- API layer: `fastapi`, `uvicorn`, `sse-starlette`
- Notebook/export tooling: `nbformat`, `nbconvert`, `python-docx`, `reportlab`
- Retrieval/indexing: FAISS via LangChain vector store integrations,
  `aiohttp`, `beautifulsoup4`

## Development Setup

- Local setup is documented in `README.md` and `docs/dev.md`.
- Standard setup flow is:
  - create a virtual environment
  - install `requirements.txt`
  - install the package in editable mode, for example:
    - `pip install -e .` for core functionality, or
    - `pip install -e ".[full]"` to enable full API/RAG/export features
  - copy `.env.example` to `.env`
  - run `python -m pytest`
- The `lnf` console entry point defined in `setup.py` is available only after the package has been installed.
- Release-readiness packaging checks live in
  `tests/integration/test_packaging_install_smoke.py` and are opt-in with
  `RUN_PACKAGING_SMOKE=1`.
- The local deterministic release evaluation script is
  `scripts/run_release_eval.py`; it writes a JSON report and defaults to
  no-upload behavior for CI/release PR use.
- The current full verification command is `python -m pytest
  --asyncio-mode=auto`. The latest documented full run from the generated-output
  artifact-manifest branch reported 721 passed and 3 skipped; targeted PR #357
  unit verification reported 609 passed. PR #359 review-fix slices reported 96
  pattern tests, 102 composer/validator tests, and 142 generator/API-node tests
  passing; the post-refresh broad unit gate reported 622 passed and 4 warnings.
  Current Wave 4 focused slices report 111 composer/validator tests, 143
  generator/API-node tests, and 98 pattern tests passing. The Wave 4 broad unit
  gate reports 634 passed and 4 warnings, and the headed/live UI gate completed
  with `gpt-5.4-mini`, working notebook, HTML, and manifest downloads, no
  browser errors, and advisory-only generated-artifact QA.
- The CI fatal-error lint gate is `python -m flake8 . --count
  --select=E9,F63,F7,F82 --show-source --statistics`; the broader
  `--exit-zero` flake8 statistics command is informational and still reports
  pre-existing style findings.

## Configuration Model

- Environment-backed settings are defined in
  `src/langgraph_system_generator/utils/config.py`.
- Default model settings currently center on `gpt-5-mini`.
- Live generation relies on environment-provided API credentials, while stub
  mode avoids external LLM calls.
- Output-path behavior is constrained by the base-output helpers in
  `src/langgraph_system_generator/constants.py`.

## Technical Constraints

- Live generation currently requires `OPENAI_API_KEY`.
- Semantic retrieval depends on a local vector index existing at the configured
  vector store path.
- SSE job tracking is in-memory and therefore best suited to single-process or
  single-server deployments.
- PDF export depends on local `jupyter nbconvert` tooling and a working webpdf
  or LaTeX environment.
