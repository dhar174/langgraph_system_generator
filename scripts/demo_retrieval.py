#!/usr/bin/env python
"""Example: Using cached documentation for retrieval without API keys.

This example demonstrates how to build a searchable index from cached
documentation using fake embeddings (for demo/testing purposes).
"""

import asyncio
from pathlib import Path

from langchain_community.embeddings import FakeEmbeddings

from langgraph_system_generator.rag.cache import DocumentCache
from langgraph_system_generator.rag.indexer import build_index_from_cache
from langgraph_system_generator.rag.retriever import DocsRetriever


async def main():
    """Demo retrieval from cached docs."""
    print("=" * 70)
    print("Cached Documentation Retrieval Demo")
    print("=" * 70)
    
    # Check if cached docs exist
    cache = DocumentCache("./data/cached_docs")
    if not cache.exists():
        print("ERROR: No cached documents found!")
        print("Run 'python scripts/build_index.py' to scrape documentation.")
        return
    
    docs = cache.load_documents()
    print(f"\n1. Loaded {len(docs)} cached documents")
    
    # Build index with fake embeddings (for demo - no API key needed)
    print("\n2. Building search index with fake embeddings...")
    print("   (In production, use OpenAI embeddings)")
    
    temp_index_path = "./data/demo_index"
    Path(temp_index_path).mkdir(parents=True, exist_ok=True)
    
    manager = await build_index_from_cache(
        cache_path="./data/cached_docs",
        store_path=temp_index_path,
        embeddings=FakeEmbeddings(size=384),
    )
    print(f"✓ Index built at: {manager.store_path}")
    
    # Create retriever
    retriever = DocsRetriever(manager)
    
    # Test queries
    queries = [
        "LangGraph state management",
        "multi-agent supervisor pattern",
        "async streaming",
    ]
    
    print("\n3. Testing retrieval:")
    for query in queries:
        print(f"\n   Query: '{query}'")
        results = retriever.retrieve(query, k=2)
        
        for i, result in enumerate(results, 1):
            source = result['source'].split('/')[-2:]  # Last 2 parts of URL
            source_short = '/'.join(source)
            content_preview = result['content'][:80].replace('\n', ' ')
            
            print(f"      {i}. {source_short}")
            print(f"         {content_preview}...")
    
    print("\n" + "=" * 70)
    print("Note: This demo uses FakeEmbeddings for illustration.")
    print("For real semantic search, set OPENAI_API_KEY and run:")
    print("  python scripts/build_index.py")
    print("=" * 70)
    
    # Cleanup demo index
    import shutil
    shutil.rmtree(temp_index_path, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
