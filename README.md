# langgraph_system_generator

Prompt -> Full Agentic System. Generates entire multiagent systems based on user constraints in a simple text prompt.

## Features

- **Pre-cached Documentation**: LangGraph and LangChain documentation is pre-fetched and cached locally in `data/docs_cache/` for offline use and faster access
- **RAG-based System Generation**: Uses retrieval-augmented generation to create systems based on best practices from official documentation

## Quickstart

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and add your API keys.

3. Run the test scaffold to verify imports:
   ```bash
   python -m pytest
   ```

## Scripts

### Pre-fetch Documentation

To refresh the cached documentation:

```bash
python scripts/precache_docs.py
```

This will fetch the latest documentation from configured URLs and save them to `data/docs_cache/`. See `scripts/README.md` for more details.

## Additional Information

See `docs/dev.md` for additional setup details.
