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
from langgraph_system_generator.rag.mcp_transport import _sanitize_text_credentials
from langgraph_system_generator.rag.normalizer import create_normalized_doc_snippet
from langgraph_system_generator.rag.retriever import DocsRetriever

logger = logging.getLogger(__name__)


class CachedVectorDocsProvider(DocsSourceProvider):
    """Documentation provider backed by local/cached vector store index."""

    source_id: str = "cached_repo_docs"
    stub_safe: bool = False

    def __init__(
        self,
        docs_retriever: Optional[DocsRetriever] = None,
        vector_store_path: Optional[str | Path] = None,
        stub_safe: Optional[bool] = None,
    ):
        self._injected_retriever = docs_retriever
        self._vector_store_path = vector_store_path
        is_offline = docs_retriever is not None and getattr(
            docs_retriever, "is_offline_safe", False
        )
        if stub_safe is True and not is_offline:
            logger.warning(
                "CachedVectorDocsProvider stub_safe=True ignored: injected retriever is not offline-safe."
            )
            self.stub_safe = False
        elif is_offline:
            self.stub_safe = True if stub_safe is None else bool(stub_safe)
        else:
            self.stub_safe = False

    def _resolve_retriever(self) -> DocsRetriever:
        if self._injected_retriever is not None:
            return self._injected_retriever
        from langgraph_system_generator.generator.nodes import get_cached_docs_retriever

        return get_cached_docs_retriever(self._vector_store_path)

    def is_available(self, mode: str = "live") -> bool:
        """Check availability. In stub mode, only available if offline-safe."""
        if mode == "stub":
            return bool(self.stub_safe)
        return True

    async def aretrieve(
        self,
        query: str,
        k: int = 5,
        mode: str = "live",
    ) -> DocsProviderResult:
        """Retrieve documentation from local vector store off the event loop."""
        if mode == "stub" and not self.stub_safe:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.SKIPPED,
                latency_ms=0.0,
            )
        start_time = time.perf_counter()
        retriever_name = "DocsRetriever"
        raw_results: List[Any]
        try:
            if self._injected_retriever is not None or self._vector_store_path is not None:
                retriever = self._resolve_retriever()
                retriever_name = type(retriever).__name__
                raw_results = await asyncio.to_thread(retriever.retrieve, query, k)
            else:
                from langgraph_system_generator.generator import nodes

                raw_results = await nodes.asyncio.to_thread(
                    nodes._retrieve_docs_for_prompt, query
                )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            safe_exc = _sanitize_text_credentials(str(exc))
            logger.warning("Cached vector store retrieval failed: %s", safe_exc)
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.FAILED,
                latency_ms=elapsed_ms,
                error_message=safe_exc,
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
                if not item.content or not item.content.strip():
                    continue
                if not item.source_kind:
                    item = create_normalized_doc_snippet(
                        content=item.content,
                        source=item.source,
                        source_kind=self.source_id,
                        relevance_score=item.relevance_score,
                        heading=item.heading,
                    )
                snippets.append(item)
            elif isinstance(item, dict):
                raw_content = item.get("content", "")
                if not raw_content or not str(raw_content).strip():
                    continue
                score_kind = item.get("score_kind")
                if score_kind == "distance":
                    is_dist = True
                    raw_score = item.get("distance", item.get("relevance_score", 0.0))
                elif score_kind == "similarity":
                    is_dist = False
                    raw_score = item.get("relevance_score", item.get("score", 0.0))
                elif "distance" in item and "relevance_score" not in item:
                    is_dist = True
                    raw_score = item["distance"]
                else:
                    is_dist = False
                    raw_score = item.get("relevance_score", item.get("score", 0.0))
                score = float(raw_score) if raw_score is not None else 0.0
                snippets.append(
                    create_normalized_doc_snippet(
                        content=str(raw_content).strip(),
                        source=item.get("source", ""),
                        source_kind=self.source_id,
                        relevance_score=score,
                        heading=item.get("heading"),
                        is_distance=is_dist,
                    )
                )
            else:
                content = getattr(item, "page_content", getattr(item, "content", str(item)))
                if not content or not str(content).strip():
                    continue
                metadata = getattr(item, "metadata", {})
                source = metadata.get("source", "") if isinstance(metadata, dict) else ""
                heading = metadata.get("heading") or metadata.get("title") if isinstance(metadata, dict) else None
                score_kind = getattr(item, "score_kind", None)
                if score_kind == "distance":
                    is_dist = True
                    raw_score = getattr(item, "distance", getattr(item, "relevance_score", 0.0))
                elif score_kind == "similarity":
                    is_dist = False
                    raw_score = getattr(item, "relevance_score", getattr(item, "score", 0.0))
                elif hasattr(item, "distance") and not hasattr(item, "relevance_score"):
                    is_dist = True
                    raw_score = getattr(item, "distance")
                else:
                    is_dist = False
                    raw_score = getattr(item, "relevance_score", getattr(item, "score", 0.0))
                score = float(raw_score) if raw_score is not None else 0.0
                snippets.append(
                    create_normalized_doc_snippet(
                        content=str(content).strip(),
                        source=source,
                        source_kind=self.source_id,
                        relevance_score=score,
                        heading=heading,
                        is_distance=is_dist,
                    )
                )

        if not snippets:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.EMPTY,
                snippets=[],
                latency_ms=elapsed_ms,
                metadata={"retriever_type": retriever_name},
            )

        return DocsProviderResult(
            source_id=self.source_id,
            status=DocsSourceStatus.SUCCESS,
            snippets=snippets[:k],
            latency_ms=elapsed_ms,
            metadata={"retriever_type": retriever_name},
        )
