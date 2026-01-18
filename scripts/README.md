# Scripts

This directory contains utility scripts for the LangGraph System Generator project.

## precache_docs.py

Pre-fetches and caches documentation locally from configured URLs.

### Purpose

This script allows you to:
- Download documentation from LangChain/LangGraph URLs
- Store the documentation as text files in the repository
- Keep documentation available for offline access
- Speed up initial indexing by using cached content

### Usage

Basic usage (uses default URLs from DocsIndexer):
```bash
python scripts/precache_docs.py
```

Specify custom output directory:
```bash
python scripts/precache_docs.py --output-dir /path/to/cache
```

Fetch specific URLs:
```bash
python scripts/precache_docs.py --urls https://docs.langchain.com/oss/python/langgraph/use-graph-api https://example.com/other-doc
```

### Output

The script creates:
- `data/docs_cache/*.txt` - Individual cached documentation files
- `data/docs_cache/cache_metadata.json` - Metadata index with URLs, titles, and file mappings

### Requirements

The script requires the following packages:
- `aiohttp` - For async HTTP requests
- `beautifulsoup4` - For HTML parsing
- `langchain-core` - For Document objects

These are included in the project's `requirements.txt`.

### Committing Cached Files

After running the script, you can commit the cached files to the repository:
```bash
git add data/docs_cache/
git commit -m "Add pre-cached documentation"
```

This allows other developers to use the cached documentation without fetching it from the web.
