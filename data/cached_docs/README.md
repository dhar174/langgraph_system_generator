# Precached LangGraph/LangChain Documentation

This directory contains precached documentation from LangGraph and LangChain that has been scraped and stored for offline use. This enables the RAG system to work without needing to fetch documentation on every run.

**Note:** Redirect pages and minimal content (< 100 characters) are automatically filtered during scraping to ensure only high-quality documentation is cached.

## Contents

The `documents.json` file contains scraped documentation from:

### LangGraph Documentation
- Core concepts and API
- Multi-agent patterns (supervisor, hierarchical teams, collaboration)
- State management and persistence
- Streaming and async operations
- How-to guides and tutorials

### LangChain Documentation
- Core concepts
- Agent architectures
- RAG and retrieval
- Chains and prompts
- Tools and integrations

## Statistics

- **Total Documents**: 19+
- **Content Size**: ~300KB (299,000+ characters)
- **Sources**: Official LangGraph and LangChain documentation sites
- **Quality**: All redirect pages and minimal content filtered out

## Usage

### Loading Cached Documents

```python
from langgraph_system_generator.rag.cache import DocumentCache

cache = DocumentCache("./data/cached_docs")
documents = cache.load_documents()
print(f"Loaded {len(documents)} documents")
```

### Building Index from Cache

To build a vector index from the cached documents (requires OpenAI API key):

```python
import asyncio
from langgraph_system_generator.rag.indexer import build_index_from_cache

async def main():
    manager = await build_index_from_cache(
        cache_path="./data/cached_docs",
        store_path="./data/vector_store"
    )
    print(f"Index built at: {manager.store_path}")

asyncio.run(main())
```

Or use the provided script:

```bash
python scripts/build_index.py
```

### Using the Retriever

```python
from langgraph_system_generator.rag.embeddings import VectorStoreManager
from langgraph_system_generator.rag.retriever import DocsRetriever

# Load existing index
manager = VectorStoreManager("./data/vector_store")
manager.load_index()

# Retrieve relevant documentation
retriever = DocsRetriever(manager)
results = retriever.retrieve("LangGraph state management", k=5)

for result in results:
    print(f"Source: {result['source']}")
    print(f"Content: {result['content'][:200]}...")
    print(f"Score: {result['relevance_score']}\n")
```

## Updating the Cache

To refresh the cached documentation:

```bash
# This will re-scrape all documentation URLs
python scripts/build_index.py
```

The script will:
1. Scrape documentation from all configured URLs
2. Save the raw documents to `data/cached_docs/documents.json`
3. Build a vector index (if OpenAI API key is available)

## Structure

```
data/cached_docs/
├── documents.json    # Cached documentation in JSON format
└── README.md         # This file
```

Each document in `documents.json` has:
- `page_content`: The text content of the documentation page
- `metadata`: Dictionary containing:
  - `source`: URL of the documentation page
  - `title`: Page title (if available)
  - `heading`: Main heading (if available)

## Benefits of Precaching

1. **Offline Use**: Works without internet connectivity
2. **Faster Startup**: No need to scrape docs on every run
3. **Consistency**: Same documentation across all environments
4. **Cost Savings**: Reduces API calls for scraping
5. **Version Control**: Documentation is versioned with the code
