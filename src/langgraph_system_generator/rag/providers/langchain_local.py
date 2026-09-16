"""Primary live documentation provider for local/MCP LangChain docs."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from langgraph_system_generator.generator.state import DocSnippet
from langgraph_system_generator.rag.base import (
    DocsProviderResult,
    DocsSourceProvider,
    DocsSourceStatus,
)
from langgraph_system_generator.rag.normalizer import create_normalized_doc_snippet
from langgraph_system_generator.utils.config import settings

logger = logging.getLogger(__name__)


class LangChainDocsLocalProvider(DocsSourceProvider):
    """Primary live documentation provider querying local LangChain docs MCP/HTTP service."""

    source_id: str = "langchain-docs-local"

    def __init__(self, endpoint_url: Optional[str] = None, timeout_seconds: float = 5.0):
        self._endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds

    @property
    def endpoint_url(self) -> Optional[str]:
        return self._endpoint_url or settings.langchain_docs_mcp_url

    def is_available(self, mode: str = "live") -> bool:
        """Return True if enabled in live mode and an endpoint URL is configured."""
        if mode == "stub":
            return False
        return bool(settings.docs_live_sources_enabled and self.endpoint_url)

    async def aretrieve(
        self,
        query: str,
        k: int = 5,
        mode: str = "live",
    ) -> DocsProviderResult:
        """Retrieve documentation from local LangChain docs MCP service."""
        start_time = time.perf_counter()
        if not self.is_available(mode=mode):
            status = DocsSourceStatus.SKIPPED if mode == "stub" else DocsSourceStatus.UNAVAILABLE
            return DocsProviderResult(
                source_id=self.source_id,
                status=status,
                latency_ms=0.0,
                error_message="Live docs retrieval is disabled or unconfigured." if mode != "stub" else None,
            )

        try:
            import httpx
        except ImportError:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.UNAVAILABLE,
                error_message="Optional dependency 'httpx' is required for live docs retrieval.",
            )

        url = self.endpoint_url
        if not url:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.UNAVAILABLE,
                error_message="Missing endpoint URL for langchain-docs-local.",
            )

        # Standard Mintlify documentation MCP call, with fallback compatibility names
        candidate_tool_calls = [
            {"name": "search", "arguments": {"query": query}},
            {"name": "search_docs_by_lang_chain", "arguments": {"query": query}},
            {"name": "query_docs_filesystem_docs_by_lang_chain", "arguments": {"query": query}},
        ]

        last_error: Optional[str] = None
        snippets: List[DocSnippet] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                for tool_call in candidate_tool_calls:
                    json_rpc_payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": tool_call,
                    }
                    try:
                        response = await client.post(
                            url,
                            json=json_rpc_payload,
                            headers={"Content-Type": "application/json"},
                        )
                    except httpx.RequestError as req_err:
                        last_error = f"HTTP request failed: {req_err}"
                        break

                    if response.status_code != 200:
                        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                        continue

                    try:
                        data = response.json()
                    except Exception:
                        last_error = f"Invalid JSON response from {url}"
                        continue

                    if "error" in data:
                        err_obj = data["error"]
                        err_msg = err_obj.get("message", str(err_obj)) if isinstance(err_obj, dict) else str(err_obj)
                        last_error = f"MCP error: {err_msg}"
                        # If tool was not found, try the next compatibility candidate tool
                        if "not found" in err_msg.lower() or "unknown tool" in err_msg.lower():
                            continue
                        break

                    snippets = self._extract_snippets_from_payload(data, fallback_url=url)
                    if snippets:
                        break

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning("langchain-docs-local retrieval failed: %s", exc)
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.FAILED,
                latency_ms=elapsed_ms,
                error_message=str(exc),
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        if not snippets:
            if last_error:
                return DocsProviderResult(
                    source_id=self.source_id,
                    status=DocsSourceStatus.FAILED,
                    latency_ms=elapsed_ms,
                    error_message=last_error,
                )
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.EMPTY,
                latency_ms=elapsed_ms,
            )

        return DocsProviderResult(
            source_id=self.source_id,
            status=DocsSourceStatus.SUCCESS,
            snippets=snippets[:k],
            latency_ms=elapsed_ms,
            metadata={"endpoint": url},
        )

    def _extract_snippets_from_payload(
        self,
        payload: Dict[str, Any],
        fallback_url: str,
    ) -> List[DocSnippet]:
        """Extract and normalize DocSnippet instances from an MCP or HTTP JSON payload."""
        snippets: List[DocSnippet] = []
        result = payload.get("result") or payload

        items: List[Any] = []
        if isinstance(result, dict):
            content_items = result.get("content")
            if isinstance(content_items, list):
                items = content_items
            elif "documents" in result and isinstance(result["documents"], list):
                items = result["documents"]
            elif "snippets" in result and isinstance(result["snippets"], list):
                items = result["snippets"]
        elif isinstance(result, list):
            items = result

        for item in items:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("page_content") or ""
                # If text is JSON serialized string
                if isinstance(text, str) and (text.strip().startswith("[") or text.strip().startswith("{")):
                    try:
                        sub_parsed = json.loads(text.strip())
                        if isinstance(sub_parsed, list):
                            for sub_item in sub_parsed:
                                if isinstance(sub_item, dict):
                                    sub_score = sub_item.get("score")
                                    if sub_score is None:
                                        sub_score = sub_item.get("relevance_score")
                                    if sub_score is None:
                                        sub_score = 0.95
                                    snippets.append(
                                        create_normalized_doc_snippet(
                                            content=sub_item.get("content") or sub_item.get("text") or "",
                                            source=sub_item.get("url") or sub_item.get("source") or fallback_url,
                                            source_kind=self.source_id,
                                            heading=sub_item.get("title") or sub_item.get("heading"),
                                            relevance_score=sub_score,
                                        )
                                    )
                            continue
                    except Exception:
                        pass

                source = item.get("url") or item.get("source") or fallback_url
                heading = item.get("title") or item.get("heading")
                score = item.get("score")
                if score is None:
                    score = item.get("relevance_score")
                if score is None:
                    score = 0.95
                if text:
                    snippets.append(
                        create_normalized_doc_snippet(
                            content=str(text),
                            source=str(source),
                            source_kind=self.source_id,
                            relevance_score=score,
                            heading=heading,
                        )
                    )
            elif isinstance(item, str) and item.strip():
                snippets.append(
                    create_normalized_doc_snippet(
                        content=item.strip(),
                        source=fallback_url,
                        source_kind=self.source_id,
                        relevance_score=0.9,
                    )
                )

        return snippets
