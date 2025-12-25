# Scripts

This directory contains utility scripts for the LangGraph System Generator project.

## precache_docs.py

Pre-fetches and caches documentation locally in the repository.

### Purpose

This script uses the `DocsIndexer` class to scrape documentation from configured URLs and saves the content to local files in `data/docs_cache/`. This allows:

- Documentation to be pre-cached in the repository for offline use
- Avoiding repeated network requests during development
- Ensuring documentation is available even if source URLs are temporarily unavailable

### Usage

```bash
# From the repository root
python scripts/precache_docs.py
```

### Requirements

The script requires the project dependencies to be installed. Install them with:

```bash
pip install -r requirements.txt
```

Or install the package in development mode:

```bash
pip install -e .
```

### Output

The script will:
1. Fetch documentation from URLs configured in `DocsIndexer.DOCS_URLS`
2. Save each document as a text file in `data/docs_cache/`
3. Include metadata (source URL, title, heading) at the top of each file
4. Print progress and summary information

### Cached Files

Each cached file includes:
- A metadata header with source URL, title, and heading
- The extracted text content from the documentation page
- A sanitized filename derived from the source URL

Example output structure:
```
data/docs_cache/
├── oss_python_langgraph_use-graph-api.txt
├── oss_python_langchain_multi-agent_subagents.txt
├── oss_python_langchain_agents.txt
├── oss_javascript_langchain_multi-agent_router.txt
└── oss_javascript_langgraph_persistence.txt
```

### Customization

To fetch different URLs, modify the `DOCS_URLS` in `src/langgraph_system_generator/rag/indexer.py` or create a custom instance of `DocsIndexer` with your desired URLs.
