# Getting Started

This guide helps you install LangGraph System Generator and run your first
generation through the CLI, web UI, or REST API.

## Prerequisites

- **Python**: Version 3.10 or higher.
- **OpenAI-compatible API key**: Required for `--mode live`; optional for
  `--mode stub`.
- **Operating system**: Linux, macOS, or Windows.

## Installation

### 1. Clone The Repository

```bash
git clone https://github.com/dhar174/langgraph_system_generator.git
cd langgraph_system_generator
```

### 2. Create A Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

Choose the profile that matches what you want to run:

```bash
# Core package, settings, and shared types only
pip install -e .

# FastAPI/web server only
pip install -e ".[api]"

# CLI generation, notebook export, runtime QA, and live-mode dependencies
pip install -e ".[full]"

# Contributor/test tooling
pip install -e ".[full,dev]"
```

If you are using this repository directly, `pip install -r requirements.txt` is
also supported and installs the broad dependency set used by CI.

### 4. Configure Environment Variables

Copy the example file:

```bash
cp .env.example .env
```

Typical live-mode settings:

```bash
OPENAI_API_KEY=sk-your-openai-key-here
LANGSMITH_API_KEY=your-langsmith-key-here
LANGSMITH_PROJECT=langgraph-notebook-foundry
VECTOR_STORE_TYPE=faiss
VECTOR_STORE_PATH=./data/vector_store
DEFAULT_MODEL=gpt-5-mini
MAX_REPAIR_ATTEMPTS=3
DEFAULT_BUDGET_TOKENS=100000
```

Stub mode does not require provider credentials.

### 5. Optionally Build The Vector Index

The repository includes precached documentation in `data/cached_docs/`.

```bash
# Offline-friendly test index using fake embeddings
lnf build-index --cache ./data/cached_docs --store ./data/vector_store

# OpenAI-backed semantic index
lnf build-index --use-openai
```

Vector search is optional. Stub mode works without a vector store.

### 6. Verify Installation

```bash
python -m pytest --asyncio-mode=auto
```

## Your First Generation

Generate a simple system in stub mode:

```bash
lnf generate "Create a customer support chatbot with routing" \
  --output ./output/first_system \
  --mode stub
```

This writes a subset of the following artifacts, depending on requested formats:

- `notebook.ipynb`: Runnable Jupyter notebook.
- `notebook.html`: HTML export.
- `notebook.md`: Markdown export.
- `notebook.docx`: Word document export.
- `notebook_bundle.zip`: Bundle with notebook, requested exports, and JSON data.
- `notebook_plan.json`: Notebook structure plan.
- `generated_cells.json`: Raw generated cell specs.
- `manifest.json`: Metadata, warning entries, and structured feedback.

The default CLI formats are `ipynb html markdown docx zip`; PDF is generated
only when explicitly requested.

## Live Mode

For full LLM-backed generation:

```bash
lnf generate "Create a research assistant with multiple specialized agents" \
  --output ./output/research_system \
  --mode live
```

Live mode uses the configured model to analyze requirements, select an
architecture, design the graph, plan tools, and compose notebook cells. Runtime
QA and deterministic repair still use the shared validator/repair engine.

## Web Interface

Start the web server:

```bash
uvicorn langgraph_system_generator.api.server:app --reload
```

Open `http://localhost:8000`.

The web interface provides:

- Natural-language prompt input.
- Stub/live mode selection.
- Advanced live options for model, temperature, max tokens, agent type, and
  custom endpoint.
- Progress tracking.
- Download links for generated artifacts.
- Dark/light theme support.

## REST API

Synchronous generation:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a data analysis agent with report generation",
    "mode": "stub",
    "output_dir": "./output/api_test",
    "formats": ["ipynb", "html", "markdown", "docx", "zip"]
  }'
```

Async generation:

```bash
curl -X POST http://localhost:8000/generate-async \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a router chatbot", "mode": "stub"}'
```

Then connect to the returned `stream_url`, for example
`/stream/{job_id}`, to receive Server-Sent Events progress updates.

## Customizing Generation

CLI controls:

```bash
lnf generate "Create a chatbot" \
  --output ./output/custom \
  --mode live \
  --formats ipynb html \
  --agent-type router
```

Supported `--agent-type` values are `router`, `subagents`, `hybrid`, and
`autoagent`.

Use the REST API for request-scoped `model`, `custom_endpoint`, `temperature`,
or `max_tokens` overrides.

## Understanding The Generated Notebook

Open the generated notebook in Jupyter:

```bash
jupyter notebook output/first_system/notebook.ipynb
```

Generated notebooks typically include:

1. Introduction and graph overview.
2. Dependency installation.
3. Runtime configuration.
4. State schema.
5. Tool implementations.
6. Node implementations.
7. Graph construction.
8. Execution examples.
9. QA and repair summary, when repairs were attempted.

## Running In Google Colab

Generated notebooks are Colab-ready:

1. Upload `notebook.ipynb` to Google Drive.
2. Open it with Google Colaboratory.
3. Run the generated setup/install cell. It is based on the notebook dependency
   plan and only installs required packages.
4. Add only the provider keys referenced by the notebook.
5. Run all cells.

See [Colab Usage Guide](Colab-Usage.md) for details.

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError: No module named 'langgraph_system_generator'`:

```bash
pip install -e ".[full]"
```

### Missing API Key

If live generation fails with credential errors:

1. Confirm `.env` has a valid `OPENAI_API_KEY`, or use an API request with both
   `custom_endpoint` and `model`.
2. Try stub mode with `--mode stub` to verify local generation.

### Vector Store Errors

If FAISS or retrieval fails:

1. Install the full extras: `pip install -e ".[full]"`.
2. Rebuild the index with `lnf build-index`.
3. Continue in stub mode if retrieval is not needed.

### Notebook Execution Fails

1. Check `manifest.json` for warnings and feedback.
2. Review `qa_repair_feedback` and any notebook `QA and Repair Summary` cell.
3. Confirm provider keys are set before running live notebook cells.

## Getting Help

- **Examples**: See `examples/`.
- **Documentation**: Browse the wiki pages in `docs/wiki/`.
- **Issues**: Report problems on [GitHub Issues](https://github.com/dhar174/langgraph_system_generator/issues).
- **Tests**: Review `tests/` for usage patterns.

---

**Next**: [Architecture Deep Dive](Architecture-Deep-Dive.md) | [Pattern Library Guide](Pattern-Library-Guide.md)
