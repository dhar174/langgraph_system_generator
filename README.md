# langgraph_system_generator

Prompt -> Full Agentic System. Generates entire multiagent systems based on user constraints in a simple text prompt.

## Features

- **Web Interface**: Modern, user-friendly web UI for generating systems without code
- **RAG-Powered Documentation**: Includes precached LangGraph and LangChain documentation for offline use
- **Pattern Library**: Built-in support for common multi-agent patterns
- **Production-Ready**: Generates complete, runnable Jupyter notebooks

## Quickstart

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and add your API keys.

3. (Optional) Build the vector index from precached docs:
   ```bash
   python scripts/build_index.py
   ```
   
   Note: The documentation has already been scraped and cached in `data/cached_docs/`. 
   You only need to run this if you have an OpenAI API key and want to build the 
   vector index for semantic search.

4. Run the test scaffold to verify imports:
   ```bash
   python -m pytest
   ```

## CLI

Use the bundled CLI (stub mode by default) to generate scaffold artifacts or rebuild the vector index:

```bash
# Generate offline-friendly artifacts from a prompt
lnf generate "Create a router-based chatbot" --output ./output/demo --mode stub

# Generate specific output formats (default: all formats)
lnf generate "Create a chatbot" --output ./output/demo --formats ipynb html docx

# Build the FAISS index from cached docs with fake embeddings (no API key needed)
lnf build-index --cache ./data/cached_docs --store ./data/vector_store
```

Pass `--mode live` to `lnf generate` when you have `OPENAI_API_KEY` configured and want to invoke the full generator graph.

### Output Formats

The generator produces the following artifacts:

- **JSON artifacts**: `manifest.json`, `notebook_plan.json`, `generated_cells.json` for programmatic access
- **Jupyter Notebook** (`.ipynb`): Fully functional notebook ready to run in Jupyter or Google Colab
- **HTML** (`.html`): Web-ready notebook export for viewing and sharing
- **DOCX** (`.docx`): Microsoft Word document for documentation and editing
- **PDF** (`.pdf`): Print-ready PDF document (requires additional dependencies)
- **ZIP Bundle** (`.zip`): Complete package with notebook and all JSON artifacts

Use the `--formats` option to select specific formats (default: generates all except PDF):

```bash
lnf generate "Create a chatbot" --formats ipynb html docx zip
```

## Web Interface

A modern web interface is available for easy system generation:

```bash
uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000
```

Then open your browser to `http://localhost:8000` to access the web UI.

### Features

- **Interactive Form**: Enter your system requirements in natural language
- **Mode Selection**: Choose between stub mode (fast, no API key) or live mode (full LLM generation)
- **Real-time Status**: See server health and generation progress
- **Results Display**: View generated artifacts with download links
- **Responsive Design**: Works on desktop and mobile devices

![Web Interface](https://github.com/user-attachments/assets/29cdc1ce-d458-4296-8f50-dde4c3ff1717)

![Generation Results](https://github.com/user-attachments/assets/4b1fc082-5fa6-46ca-9b48-161c90e1987d)

## API

The FastAPI server also exposes REST endpoints:

Endpoints:

- `GET /` – web interface
- `GET /health` – health check
- `POST /generate` – generate artifacts (supports `stub`/`live` modes; defaults to `stub`)

Example API usage:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a customer support chatbot with routing",
    "mode": "stub",
    "output_dir": "./output/my_system",
    "formats": ["ipynb", "html", "docx", "zip"]
  }'
```

The API response includes paths to all generated artifacts in the manifest:

```json
{
  "success": true,
  "mode": "stub",
  "prompt": "Create a customer support chatbot with routing",
  "manifest": {
    "notebook_path": "./output/my_system/notebook.ipynb",
    "html_path": "./output/my_system/notebook.html",
    "docx_path": "./output/my_system/notebook.docx",
    "zip_path": "./output/my_system/notebook_bundle.zip",
    "plan_path": "./output/my_system/notebook_plan.json",
    "cells_path": "./output/my_system/generated_cells.json"
  }
}
```

You can also containerize the application:

```bash
docker build -t lnf .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -v $(pwd)/output:/app/output \
  lnf
```

## Precached Documentation

This repository includes precached LangGraph and LangChain documentation (19+ pages, ~300KB) 
in `data/cached_docs/`. All redirect pages and minimal content are automatically filtered 
to ensure high-quality documentation. This enables:

- **Offline use** without needing to scrape documentation
- **Faster startup** times
- **Consistent** documentation across environments

See `data/cached_docs/README.md` for more details.

See `docs/dev.md` for additional setup details.
