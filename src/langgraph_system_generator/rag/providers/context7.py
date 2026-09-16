"""Secondary live documentation provider querying Context7."""

from __future__ import annotations

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


class Context7DocsProvider(DocsSourceProvider):
    """Secondary live documentation provider connecting to Context7 MCP / HTTP API."""

    source_id: str = "context7"

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout_seconds: float = 5.0,
    ):
        self._api_key = api_key
        self._endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds

    @property
    def api_key(self) -> Optional[str]:
        return self._api_key or settings.context7_api_key

    @property
    def endpoint_url(self) -> str:
        return self._endpoint_url or settings.context7_mcp_url or "https://mcp.context7.com/mcp"

    def is_available(self, mode: str = "live") -> bool:
        """Return True if enabled in live mode and either an API key or custom endpoint is configured."""
        if mode == "stub":
            return False
        return bool(
            settings.docs_live_sources_enabled
            and settings.context7_docs_enabled
            and (self.api_key or settings.context7_mcp_url)
        )

    async def aretrieve(
        self,
        query: str,
        k: int = 5,
        mode: str = "live",
    ) -> DocsProviderResult:
        """Retrieve documentation from Context7 asynchronously."""
        start_time = time.perf_counter()
        if not self.is_available(mode=mode):
            status = DocsSourceStatus.SKIPPED if mode == "stub" else DocsSourceStatus.UNAVAILABLE
            return DocsProviderResult(
                source_id=self.source_id,
                status=status,
                latency_ms=0.0,
                error_message="Context7 is disabled or unconfigured." if mode != "stub" else None,
            )

        try:
            import httpx
        except ImportError:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.UNAVAILABLE,
                error_message="Optional dependency 'httpx' is required for Context7 docs retrieval.",
            )

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {"query": query},
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                )
                if response.status_code != 200:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                    return DocsProviderResult(
                        source_id=self.source_id,
                        status=DocsSourceStatus.FAILED,
                        latency_ms=elapsed_ms,
                        error_message=f"Context7 HTTP {response.status_code}: {response.text[:200]}",
                    )
                data = response.json()
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning("Context7 retrieval failed: %s", exc)
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.FAILED,
                latency_ms=elapsed_ms,
                error_message=str(exc),
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        if "error" in data:
            err_msg = str(data["error"].get("message", data["error"])) if isinstance(data["error"], dict) else str(data["error"])
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.FAILED,
                latency_ms=elapsed_ms,
                error_message=f"Context7 MCP error: {err_msg}",
            )

        snippets = self._parse_snippets(data, fallback_source=self.endpoint_url)
        if not snippets:
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
            metadata={"endpoint": self.endpoint_url},
        )

    def _parse_snippets(self, payload: Dict[str, Any], fallback_source: str) -> List[DocSnippet]:
        snippets: List[DocSnippet] = []
        result = payload.get("result") or payload
        items: List[Any] = []

        if isinstance(result, dict):
            if "content" in result and isinstance(result["content"], list):
                items = result["content"]
            elif "documents" in result and isinstance(result["documents"], list):
                items = result["documents"]
            elif "snippets" in result and isinstance(result["snippets"], list):
                items = result["snippets"]
        elif isinstance(result, list):
            items = result

        for item in items:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                source = item.get("url") or item.get("source") or fallback_source
                heading = item.get("title") or item.get("heading")
                score = item.get("score") or item.get("relevance_score") or 0.9
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
                        source=fallback_source,
                        source_kind=self.source_id,
                        relevance_score=0.9,
                    )
                )

        return snippets
