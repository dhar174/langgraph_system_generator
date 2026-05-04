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
- The current full release-readiness verification command is `python -m pytest
  --asyncio-mode=auto`; the latest branch run reported 625 passed and 4 skipped.
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
