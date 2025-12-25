# Scripts

This directory contains utility scripts for the LangGraph System Generator project.

## precache_docs.py

Pre-fetches and caches documentation locally for faster access and offline usage.

### Usage

Basic usage (fetches default documentation URLs):
```bash
python scripts/precache_docs.py
```

Specify a custom output directory:
```bash
python scripts/precache_docs.py --output-dir /path/to/cache
```

Fetch specific URLs:
```bash
python scripts/precache_docs.py --urls https://example.com/doc1 https://example.com/doc2
```

### Output

By default, documentation is cached in `data/docs_cache/`. Each document is saved as a text file with:
- A metadata header containing source URL, title, and other information
- The full extracted content from the page

### Dependencies

The script requires the following packages. The easiest way to install everything is:

```bash
pip install -e ".[full]"
```

If you prefer to install only what's needed for the script:
```bash
pip install aiohttp beautifulsoup4 langchain-core langchain-text-splitters langchain-community langchain-openai faiss-cpu openai
```

**Note**: The script depends on the RAG module which requires these packages to be installed.

### Notes

- The script uses the existing `DocsIndexer` class from `src/langgraph_system_generator/rag/indexer.py`
- By default, cached `.txt` files are tracked in git. To exclude them, uncomment the line in `.gitignore`:
  ```
  # data/docs_cache/*.txt
  ```
- Files are named based on document titles, headings, or URLs
- Duplicate filenames are automatically handled with numeric suffixes
