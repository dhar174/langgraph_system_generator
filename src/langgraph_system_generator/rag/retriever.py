"""Documentation retriever for LangGraph references."""

from __future__ import annotations

from typing import Dict, List

from langgraph_system_generator.rag.embeddings import VectorStoreManager


class DocsRetriever:
    """Retrieves relevant documentation snippets."""

    def __init__(self, vector_store_manager: VectorStoreManager):
        self.vsm = vector_store_manager

    def retrieve(self, query: str, k: int = 5) -> List[Dict[str, object]]:
        """Retrieve top-k relevant documents."""

        store = self.vsm.vector_store or self.vsm.load_index()
        docs_with_scores = store.similarity_search_with_score(query, k=k)

        results = []
        for doc, score in docs_with_scores:
            results.append(
                {
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", ""),
                    "heading": doc.metadata.get("heading")
                    or doc.metadata.get("title"),
                    "relevance_score": score,
                }
            )
        return results

    def retrieve_for_pattern(self, pattern_name: str) -> List[Dict[str, object]]:
        """Retrieve docs specific to a pattern (router, subagents, etc)."""

        query = f"LangGraph {pattern_name} pattern implementation best practices"
        return self.retrieve(query, k=10)
