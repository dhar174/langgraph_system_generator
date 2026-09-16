"""Cached vector store documentation provider."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, List, Optional

from langgraph_system_generator.generator.state import DocSnippet
from langgraph_system_generator.rag.base import (
    DocsProviderResult,
    DocsSourceProvider,
    DocsSourceStatus,
)
from langgraph_system_generator.rag.normalizer import create_normalized_doc_snippet
from langgraph_system_generator.rag.retriever import DocsRetriever
from langgraph_system_generator.utils.config import settings

logger = logging.getLogger(__name__)


class CachedVectorDocsProvider(DocsSourceProvider):
    """Documentation provider backed by local/cached vector store index."""

    source_id: str = "cached_repo_docs"

    def __init__(
        self,
        docs_retriever: Optional[DocsRetriever] = None,
        vector_store_path: Optional[str | Path] = None,
    ):
        self._injected_retriever = docs_retriever
        self._vector_store_path = vector_store_path

    def _resolve_retriever(self) -> DocsRetriever:
        if self._injected_retriever is not None:
            return self._injected_retriever
        from langgraph_system_generator.generator.nodes import get_cached_docs_retriever

        return get_cached_docs_retriever(self._vector_store_path)

    def is_available(self, mode: str = "live") -> bool:
        """The cached vector provider is the local fallback and is always available."""
        return True

    async def aretrieve(
        self,
        query: str,
        k: int = 5,
        mode: str = "live",
    ) -> DocsProviderResult:
        """Retrieve documentation from local vector store off the event loop."""
        start_time = time.perf_counter()
        retriever_name = "DocsRetriever"
        try:
            if self._injected_retriever is not None or self._vector_store_path is not None:
                retriever = self._resolve_retriever()
                retriever_name = type(retriever).__name__
                raw_results: List[Any] = await asyncio.to_thread(retriever.retrieve, query, k)
            else:
                from langgraph_system_generator.generator import nodes

                raw_results: List[Any] = await nodes.asyncio.to_thread(
                    nodes._retrieve_docs_for_prompt, query
                )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning("Cached vector store retrieval failed: %s", exc)
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.FAILED,
                latency_ms=elapsed_ms,
                error_message=str(exc),
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        if not raw_results:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.EMPTY,
                latency_ms=elapsed_ms,
            )

        snippets: List[DocSnippet] = []
        for item in raw_results:
            if isinstance(item, DocSnippet):
                snippets.append(item)
            elif isinstance(item, dict):
                score = item.get("relevance_score")
                is_dist = False
                if score is None:
                    score = item.get("distance", item.get("score", 0.0))
                    is_dist = "distance" in item
                snippets.append(
                    create_normalized_doc_snippet(
                        content=item.get("content", ""),
                        source=item.get("source", ""),
                        source_kind=self.source_id,
                        relevance_score=score,
                        heading=item.get("heading"),
                        is_distance=is_dist,
                    )
                )
            else:
                content = getattr(item, "page_content", getattr(item, "content", str(item)))
                metadata = getattr(item, "metadata", {})
                source = metadata.get("source", "") if isinstance(metadata, dict) else ""
                heading = metadata.get("heading") or metadata.get("title") if isinstance(metadata, dict) else None
                score = getattr(item, "relevance_score", None)
                is_dist = False
                if score is None:
                    score = getattr(item, "distance", getattr(item, "score", 0.0))
                    is_dist = hasattr(item, "distance")
                snippets.append(
                    create_normalized_doc_snippet(
                        content=content,
                        source=source,
                        source_kind=self.source_id,
                        relevance_score=score,
                        heading=heading,
                        is_distance=is_dist,
                    )
                )

        return DocsProviderResult(
            source_id=self.source_id,
            status=DocsSourceStatus.SUCCESS,
            snippets=snippets[:k],
            latency_ms=elapsed_ms,
            metadata={"retriever_type": retriever_name},
        )
