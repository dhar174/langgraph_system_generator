"""Test that cached documentation works correctly."""

import pytest
from langchain_community.embeddings import FakeEmbeddings

from langgraph_system_generator.rag.cache import DocumentCache
from langgraph_system_generator.rag.indexer import build_index_from_cache
from langgraph_system_generator.rag.retriever import DocsRetriever


def test_cached_docs_exist():
    """Test that precached documentation exists."""
    cache = DocumentCache("./data/cached_docs")
    assert cache.exists(), "Cached documentation should exist"
    
    docs = cache.load_documents()
    assert len(docs) > 0, "Should have at least some cached documents"
    assert len(docs) >= 20, f"Expected at least 20 cached docs, got {len(docs)}"
    
    # Check that documents have proper structure
    for doc in docs[:5]:
        assert doc.page_content, "Document should have content"
        assert "source" in doc.metadata, "Document should have source metadata"


@pytest.mark.asyncio
async def test_build_index_from_cached_docs(tmp_path):
    """Test building index from cached documents."""
    # Use fake embeddings for fast testing
    manager = await build_index_from_cache(
        cache_path="./data/cached_docs",
        store_path=str(tmp_path),
        embeddings=FakeEmbeddings(size=32),
    )
    
    assert manager.vector_store is not None
    assert manager.index_exists()


@pytest.mark.asyncio
async def test_retrieval_from_cached_docs(tmp_path):
    """Test that retrieval works with cached documents."""
    # Build index from cached docs
    manager = await build_index_from_cache(
        cache_path="./data/cached_docs",
        store_path=str(tmp_path),
        embeddings=FakeEmbeddings(size=32),
    )
    
    # Test retrieval
    retriever = DocsRetriever(manager)
    results = retriever.retrieve("LangGraph state management", k=3)
    
    assert len(results) > 0, "Should retrieve some results"
    assert all("content" in r for r in results), "Results should have content"
    assert all("source" in r for r in results), "Results should have source"
    assert all("relevance_score" in r for r in results), "Results should have score"


def test_cached_docs_content():
    """Test that cached documents contain expected content."""
    cache = DocumentCache("./data/cached_docs")
    docs = cache.load_documents()
    
    # Check that we have documents from different sources
    sources = set(doc.metadata.get("source", "") for doc in docs)
    
    # Should have langgraph docs
    langgraph_sources = [s for s in sources if "langgraph" in s.lower()]
    assert len(langgraph_sources) > 0, "Should have LangGraph documentation"
    
    # Should have langchain docs
    langchain_sources = [s for s in sources if "langchain" in s.lower()]
    assert len(langchain_sources) > 0, "Should have LangChain documentation"
    
    # Check that documents have reasonable content length
    content_lengths = [len(doc.page_content) for doc in docs]
    avg_length = sum(content_lengths) / len(content_lengths)
    assert avg_length > 1000, f"Average doc length too short: {avg_length}"
