"""Secondary live documentation provider querying Context7."""

from __future__ import annotations

import json
import logging
import re
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
        self._resolved_libraries: Dict[str, str] = {}

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
            and (self.api_key or self._endpoint_url or settings.context7_mcp_url)
        )

    def _extract_library_id(self, payload: Dict[str, Any]) -> Optional[str]:
        result = payload.get("result") or payload
        if isinstance(result, dict):
            if result.get("libraryId"):
                return str(result["libraryId"]).strip()
            if result.get("library_id"):
                return str(result["library_id"]).strip()
            content = result.get("content") or []
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("text"):
                        text = str(c["text"]).strip()
                        if text.startswith("{"):
                            try:
                                parsed = json.loads(text)
                                if isinstance(parsed, dict):
                                    if parsed.get("libraryId"):
                                        return str(parsed["libraryId"]).strip()
                                    if parsed.get("library_id"):
                                        return str(parsed["library_id"]).strip()
                                    libs = parsed.get("libraries") or parsed.get("results")
                                    if isinstance(libs, list) and libs:
                                        first = libs[0]
                                        if isinstance(first, dict):
                                            val = first.get("library_id") or first.get("libraryId") or first.get("id")
                                            if val:
                                                return str(val).strip()
                                        elif isinstance(first, str):
                                            return first.strip()
                            except Exception:
                                pass
                        match = re.search(r"(/[A-Za-z0-9_\-\.]+(?:/[A-Za-z0-9_\-\.]+)+)", text)
                        if match:
                            return match.group(1)
                        if "/" in text and " " not in text:
                            return text
            elif isinstance(content, str) and "/" in content:
                return content.strip()
        elif isinstance(result, str) and "/" in result:
            return result.strip()
        return None

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

        target_lib = "langgraph" if "langchain" not in query.lower() else "langchain"
        resolved_lib_id = self._resolved_libraries.get(target_lib)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                data: Optional[Dict[str, Any]] = None

                # Protocol step 1: resolve library ID if not yet resolved
                if not resolved_lib_id:
                    resolve_payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "resolve-library-id",
                            "arguments": {"libraryName": target_lib, "query": query},
                        },
                    }
                    resolve_resp = await client.post(
                        self.endpoint_url,
                        json=resolve_payload,
                        headers=headers,
                    )
                    if resolve_resp.status_code == 200:
                        try:
                            resolve_json = resolve_resp.json()
                            if "result" in resolve_json and not resolve_json.get("error"):
                                resolved_lib_id = self._extract_library_id(resolve_json)
                                if resolved_lib_id:
                                    self._resolved_libraries[target_lib] = resolved_lib_id
                        except Exception:
                            pass

                # Protocol step 2: query-docs if library ID resolved
                if resolved_lib_id:
                    docs_payload = {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "query-docs",
                            "arguments": {"libraryId": resolved_lib_id, "query": query},
                        },
                    }
                    docs_resp = await client.post(
                        self.endpoint_url,
                        json=docs_payload,
                        headers=headers,
                    )
                    if docs_resp.status_code == 200:
                        data = docs_resp.json()

                # Fallback to compatibility search tool if query-docs was not run or returned error
                if data is None or ("error" in data and ("not found" in str(data["error"]).lower() or "unknown tool" in str(data["error"]).lower())):
                    search_payload = {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "search",
                            "arguments": {"query": query},
                        },
                    }
                    search_resp = await client.post(
                        self.endpoint_url,
                        json=search_payload,
                        headers=headers,
                    )
                    if search_resp.status_code != 200:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        return DocsProviderResult(
                            source_id=self.source_id,
                            status=DocsSourceStatus.FAILED,
                            latency_ms=elapsed_ms,
                            error_message=f"Context7 HTTP {search_resp.status_code}: {search_resp.text[:200]}",
                        )
                    data = search_resp.json()

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
        if not data:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.EMPTY,
                latency_ms=elapsed_ms,
            )

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
                if isinstance(text, str) and (text.strip().startswith("[") or text.strip().startswith("{")):
                    try:
                        sub_parsed = json.loads(text.strip())
                        if isinstance(sub_parsed, dict):
                            sub_items = (
                                sub_parsed.get("snippets")
                                or sub_parsed.get("documents")
                                or sub_parsed.get("content")
                            )
                            if isinstance(sub_items, list):
                                for sub_item in sub_items:
                                    if isinstance(sub_item, dict):
                                        sub_score = sub_item.get("score")
                                        if sub_score is None:
                                            sub_score = sub_item.get("relevance_score")
                                        if sub_score is None:
                                            sub_score = 0.9
                                        snippets.append(
                                            create_normalized_doc_snippet(
                                                content=sub_item.get("content") or sub_item.get("snippet") or sub_item.get("text") or "",
                                                source=sub_item.get("url") or sub_item.get("source") or fallback_source,
                                                source_kind=self.source_id,
                                                relevance_score=sub_score,
                                                heading=sub_item.get("title") or sub_item.get("heading"),
                                            )
                                        )
                                continue
                        elif isinstance(sub_parsed, list):
                            for sub_item in sub_parsed:
                                if isinstance(sub_item, dict):
                                    sub_score = sub_item.get("score")
                                    if sub_score is None:
                                        sub_score = sub_item.get("relevance_score")
                                    if sub_score is None:
                                        sub_score = 0.9
                                    snippets.append(
                                        create_normalized_doc_snippet(
                                            content=sub_item.get("content") or sub_item.get("snippet") or sub_item.get("text") or "",
                                            source=sub_item.get("url") or sub_item.get("source") or fallback_source,
                                            source_kind=self.source_id,
                                            relevance_score=sub_score,
                                            heading=sub_item.get("title") or sub_item.get("heading"),
                                        )
                                    )
                            continue
                    except Exception:
                        pass
                source = item.get("url") or item.get("source") or fallback_source
                heading = item.get("title") or item.get("heading")
                score = item.get("score")
                if score is None:
                    score = item.get("relevance_score")
                if score is None:
                    score = 0.9
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
