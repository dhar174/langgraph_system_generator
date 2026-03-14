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
  - copy `.env.example` to `.env`
  - run `python -m pytest`
- The package exposes the `lnf` console entry point from `setup.py`.

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
