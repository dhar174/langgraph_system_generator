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

## Precached Documentation

This repository includes precached LangGraph and LangChain documentation (31+ pages, ~317KB) 
in `data/cached_docs/`. This enables:

- **Offline use** without needing to scrape documentation
- **Faster startup** times
- **Consistent** documentation across environments

See `data/cached_docs/README.md` for more details.

See `docs/dev.md` for additional setup details.
