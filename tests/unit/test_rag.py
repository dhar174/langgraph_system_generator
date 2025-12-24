import pytest
from langchain_community.embeddings import FakeEmbeddings
from langchain_core.documents import Document

from langgraph_system_generator.rag.embeddings import VectorStoreManager
from langgraph_system_generator.rag.indexer import DocsIndexer, build_docs_index
from langgraph_system_generator.rag.retriever import DocsRetriever


def test_chunking_overlaps_and_preserves_metadata():
    base_doc = Document(
        page_content=("A" * 70) + ("B" * 70),
        metadata={"source": "https://example.com/doc", "heading": "Example Heading"},
    )
    indexer = DocsIndexer(chunk_size=50, chunk_overlap=10)

    chunks = indexer.chunk_documents([base_doc])

    assert len(chunks) >= 2
    max_overlap = indexer.chunk_overlap
    first_content = chunks[0].page_content
    second_content = chunks[1].page_content
    actual_overlap = 0
    for i in range(1, max_overlap + 1):
        if first_content.endswith(second_content[:i]):
            actual_overlap = i
    assert 0 < actual_overlap <= max_overlap
    assert chunks[0].metadata["source"] == "https://example.com/doc"
    assert chunks[0].metadata.get("heading") == "Example Heading"


@pytest.mark.asyncio
async def test_build_index_and_retrieve_from_fixture_corpus(tmp_path):
    docs = [
        Document(
            page_content="LangGraph routers decide which agent should handle a request.",
            metadata={"source": "local://router"},
        ),
        Document(
            page_content="Subagents can work in parallel within a LangGraph workflow.",
            metadata={"source": "local://subagents"},
        ),
    ]

    await build_docs_index(
        documents=docs,
        store_path=str(tmp_path),
        embeddings=FakeEmbeddings(size=32),
        force_rebuild=True,
        chunk_size=200,
        chunk_overlap=0,
    )

    # Ensure persistence round-trip works.
    fresh_manager = VectorStoreManager(
        store_path=str(tmp_path), embeddings=FakeEmbeddings(size=32)
    )
    fresh_manager.load_index()

    retriever = DocsRetriever(fresh_manager)
    results = retriever.retrieve("router", k=1)

    assert results
    assert results[0]["content"]
    assert results[0]["source"]
    assert "relevance_score" in results[0]


def test_chunk_documents_empty_input_returns_empty_list():
    indexer = DocsIndexer()
    assert indexer.chunk_documents([]) == []


def test_vector_store_manager_errors(tmp_path):
    manager = VectorStoreManager(
        store_path=str(tmp_path), embeddings=FakeEmbeddings(size=32)
    )
    with pytest.raises(ValueError):
        manager.create_index([])

    with pytest.raises(FileNotFoundError):
        manager.load_index()


def test_retriever_handles_missing_index(tmp_path):
    manager = VectorStoreManager(
        store_path=str(tmp_path), embeddings=FakeEmbeddings(size=32)
    )
    retriever = DocsRetriever(manager)
    assert retriever.retrieve("anything") == []


@pytest.mark.asyncio
async def test_scrape_docs_handles_errors(monkeypatch):
    indexer = DocsIndexer(urls=["https://example.com/fail"])

    async def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(indexer, "_fetch", _raise)
    docs = await indexer.scrape_docs()
    assert docs == []
