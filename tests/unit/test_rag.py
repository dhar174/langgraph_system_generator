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
    assert chunks[0].page_content.endswith(chunks[1].page_content[:10])
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

    manager = await build_docs_index(
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
