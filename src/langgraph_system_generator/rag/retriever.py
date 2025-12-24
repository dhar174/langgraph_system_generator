"""Documentation retriever for LangGraph references."""

from __future__ import annotations

from typing import List, Optional, TypedDict

from langgraph_system_generator.rag.embeddings import VectorStoreManager


class RetrievedSnippet(TypedDict):
    content: str
    source: str
    heading: Optional[str]
    relevance_score: float


class DocsRetriever:
    """Retrieves relevant documentation snippets."""

    def __init__(self, vector_store_manager: VectorStoreManager):
        self.vector_store_manager = vector_store_manager

    def retrieve(self, query: str, k: int = 5) -> List[RetrievedSnippet]:
        """Retrieve top-k relevant documents."""

        store = self.vector_store_manager.vector_store
        if store is None:
            try:
                store = self.vector_store_manager.load_index()
            except FileNotFoundError:
                return []

        if store is None:
            return []

        docs_with_scores = store.similarity_search_with_score(query, k=k)

        results: List[RetrievedSnippet] = []
        for doc, score in docs_with_scores:
            results.append(
                RetrievedSnippet(
                    content=doc.page_content,
                    source=doc.metadata.get("source", ""),
                    heading=doc.metadata.get("heading") or doc.metadata.get("title"),
                    relevance_score=score,
                )
            )
        return results

    def retrieve_for_pattern(self, pattern_name: str) -> List[RetrievedSnippet]:
        """Retrieve docs specific to a pattern (router, subagents, etc)."""

        query = f"LangGraph {pattern_name} pattern implementation best practices"
        return self.retrieve(query, k=10)
