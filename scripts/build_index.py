#!/usr/bin/env python
"""Build and cache LangGraph/LangChain documentation index.

This script scrapes documentation, caches the raw content, and optionally
builds a vector index for retrieval.
"""

import asyncio
import os

from dotenv import load_dotenv

from langgraph_system_generator.rag.cache import DocumentCache
from langgraph_system_generator.rag.indexer import DocsIndexer, build_docs_index

# Load environment variables (OPENAI_API_KEY for embeddings)
load_dotenv()


async def scrape_and_cache_docs(cache_path: str = "./data/cached_docs"):
    """Scrape documentation and cache it for later indexing."""
    print("=" * 70)
    print("STEP 1: Scraping documentation from LangGraph/LangChain sources")
    print("=" * 70)
    
    indexer = DocsIndexer()
    print(f"Scraping {len(indexer.urls)} documentation URLs...")
    print(f"This may take a few minutes...")
    
    documents = await indexer.scrape_docs()
    print(f"\n✓ Successfully scraped {len(documents)} documents")
    
    # Show some stats
    total_chars = sum(len(doc.page_content) for doc in documents)
    print(f"  Total content size: {total_chars:,} characters")
    
    # Save to cache
    cache = DocumentCache(cache_path)
    cache.save_documents(documents)
    print(f"✓ Cached documents to: {cache.cache_file}")
    
    return documents


async def build_vector_index(
    documents=None,
    store_path: str = "./data/vector_store",
    cache_path: str = "./data/cached_docs"
):
    """Build vector index from documents."""
    print("\n" + "=" * 70)
    print("STEP 2: Building vector index for semantic search")
    print("=" * 70)
    
    # Load from cache if documents not provided
    if documents is None:
        cache = DocumentCache(cache_path)
        if cache.exists():
            print(f"Loading documents from cache: {cache.cache_file}")
            documents = cache.load_documents()
            print(f"✓ Loaded {len(documents)} documents from cache")
        else:
            print("ERROR: No cached documents found. Run scraping first.")
            return None
    
    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n⚠ WARNING: OPENAI_API_KEY not set in environment")
        print("   The vector index requires OpenAI embeddings.")
        print("   Set OPENAI_API_KEY in your .env file and run again.")
        print("\n   Skipping index build...")
        return None
    
    print(f"Building vector index with OpenAI embeddings...")
    manager = await build_docs_index(
        documents=documents,
        force_rebuild=True,
        store_path=store_path
    )
    
    print(f"✓ Successfully built vector index at: {manager.store_path}")
    return manager


async def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("LangGraph/LangChain Documentation Indexer")
    print("=" * 70)
    
    # Step 1: Scrape and cache documentation
    documents = await scrape_and_cache_docs()
    
    # Step 2: Build vector index (if API key available)
    await build_vector_index(documents=documents)
    
    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70)
    print("\nCached documentation is ready to use.")
    print("If you have an OPENAI_API_KEY, the vector index has been built.")
    print("Otherwise, set the key and run this script again to build the index.")


if __name__ == "__main__":
    asyncio.run(main())
