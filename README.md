# langgraph_system_generator

Prompt -> Full Agentic System. Generates entire multiagent systems based on user constraints in a simple text prompt.

## Features

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

# Build the FAISS index from cached docs with fake embeddings (no API key needed)
lnf build-index --cache ./data/cached_docs --store ./data/vector_store
```

Pass `--mode live` to `lnf generate` when you have `OPENAI_API_KEY` configured and want to invoke the full generator graph.

## API

A lightweight FastAPI server is available:

```bash
uvicorn langgraph_system_generator.api.server:app --reload
```

Endpoints:

- `GET /health` – health check
- `POST /generate` – generate artifacts (supports `stub`/`live` modes; defaults to `stub`)

You can also containerize the API:

```bash
docker build -t lnf .
docker run -p 8000:8000 lnf
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
