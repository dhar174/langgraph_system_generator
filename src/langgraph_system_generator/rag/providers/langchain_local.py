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
from langgraph_system_generator.rag.mcp_transport import (
    MCPTransportError,
    _sanitize_text_credentials,
    _sanitize_url_for_logging,
    call_mcp_tool,
)
from langgraph_system_generator.rag.normalizer import create_normalized_doc_snippet
from langgraph_system_generator.utils.config import settings

logger = logging.getLogger(__name__)


class LangChainDocsLocalProvider(DocsSourceProvider):
    """Primary live documentation provider querying local LangChain docs MCP/HTTP service."""

    source_id: str = "langchain-docs-local"
    stub_safe: bool = False

    def __init__(
        self, endpoint_url: Optional[str] = None, timeout_seconds: float = 5.0
    ):
        self._endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds

    @property
    def endpoint_url(self) -> Optional[str]:
        return self._endpoint_url or settings.langchain_docs_mcp_url

    @property
    def safe_endpoint_url(self) -> Optional[str]:
        return (
            _sanitize_url_for_logging(self.endpoint_url)
            if self.endpoint_url
            else None
        )

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
            status = (
                DocsSourceStatus.SKIPPED
                if mode == "stub"
                else DocsSourceStatus.UNAVAILABLE
            )
            return DocsProviderResult(
                source_id=self.source_id,
                status=status,
                latency_ms=0.0,
                error_message=(
                    "Live docs retrieval is disabled or unconfigured."
                    if mode != "stub"
                    else None
                ),
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
        candidate_tool_names = [
            "search",
            "search_docs_by_lang_chain",
            "query_docs_filesystem_docs_by_lang_chain",
        ]

        last_error: Optional[str] = None
        snippets: List[DocSnippet] = []

        safe_url = self.safe_endpoint_url or url
        try:
            for tool_name in candidate_tool_names:
                try:
                    data = await call_mcp_tool(
                        endpoint=url,
                        tool_name=tool_name,
                        arguments={"query": query},
                        timeout_seconds=self.timeout_seconds,
                    )
                except MCPTransportError as exc:
                    last_error = str(exc)
                    # Transport/HTTP/network/auth failures mean this provider cannot be reached.
                    # Stop compatibility-tool probing immediately instead of sending useless retries.
                    break

                if "error" in data:
                    err_obj = data["error"]
                    err_code = (
                        err_obj.get("code") if isinstance(err_obj, dict) else None
                    )
                    err_msg = (
                        err_obj.get("message", str(err_obj))
                        if isinstance(err_obj, dict)
                        else str(err_obj)
                    )
                    last_error = f"MCP error: {err_msg}"
                    is_tool_missing = (
                        err_code == -32601
                        or "not found" in err_msg.lower()
                        or "unknown tool" in err_msg.lower()
                        or "unknown method" in err_msg.lower()
                    )
                    # If JSON-RPC tool was not found or unknown, try the next compatibility candidate tool
                    if is_tool_missing:
                        continue
                    break

                snippets = self._extract_snippets_from_payload(data, fallback_url=safe_url)
                if snippets:
                    break

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            clean_err = _sanitize_text_credentials(str(exc))
            logger.warning("langchain-docs-local retrieval failed: %s", clean_err)
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.FAILED,
                latency_ms=elapsed_ms,
                error_message=clean_err,
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
            metadata={"endpoint": safe_url},
        )

    def _extract_nested_items(self, parsed: Any) -> List[Any]:
        """Extract item dictionaries or strings from a parsed JSON structure."""
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("results", "snippets", "documents", "content"):
                val = parsed.get(key)
                if isinstance(val, list):
                    return val

            # Check if parsed is a protocol / JSON-RPC envelope rather than a doc object
            is_protocol = (
                "jsonrpc" in parsed
                or "method" in parsed
                or ("id" in parsed and ("result" in parsed or "error" in parsed))
                or ("error" in parsed and isinstance(parsed.get("error"), (dict, str)))
                or (
                    "result" in parsed
                    and isinstance(parsed.get("result"), (dict, list))
                    and not any(
                        isinstance(parsed.get(k), str) and str(parsed[k]).strip()
                        for k in ("snippet", "content", "text", "page_content")
                    )
                )
            )
            if is_protocol:
                return []

            # Check if parsed itself is a single document/snippet object.
            # Recognized content fields: snippet, content, text, page_content.
            # Metadata is not required.
            has_content = any(
                isinstance(parsed.get(k), str) and str(parsed[k]).strip()
                for k in ("snippet", "content", "text", "page_content")
            )
            if has_content:
                return [parsed]
        return []

    def _normalize_result_item(
        self,
        item: Dict[str, Any],
        fallback_url: str,
    ) -> Optional[DocSnippet]:
        """Normalize a dictionary representing a doc snippet/result item into a DocSnippet."""
        content: Optional[str] = None
        for key in ("snippet", "content", "text", "page_content"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                content = val.strip()
                break

        if not content:
            return None

        source = item.get("url") or item.get("source") or fallback_url
        heading = item.get("title") or item.get("heading")

        score = item.get("score")
        if score is None:
            score = item.get("relevance_score")
        if score is None:
            score = 0.95

        return create_normalized_doc_snippet(
            content=content,
            source=str(source),
            source_kind=self.source_id,
            relevance_score=score,
            heading=str(heading).strip() if heading else None,
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
            elif "results" in result and isinstance(result["results"], list):
                items = result["results"]
            elif "documents" in result and isinstance(result["documents"], list):
                items = result["documents"]
            elif "snippets" in result and isinstance(result["snippets"], list):
                items = result["snippets"]
        elif isinstance(result, list):
            items = result

        for item in items:
            if isinstance(item, dict):
                raw_str = ""
                for k in ("text", "content", "page_content", "snippet"):
                    v = item.get(k)
                    if isinstance(v, str) and v.strip():
                        raw_str = v.strip()
                        break

                if raw_str and raw_str.startswith(("[", "{")):
                    try:
                        sub_parsed = json.loads(raw_str)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        sub_parsed = None

                    if sub_parsed is not None:
                        nested_items = self._extract_nested_items(sub_parsed)
                        for sub_item in nested_items:
                            if isinstance(sub_item, dict):
                                snippet = self._normalize_result_item(
                                    sub_item, fallback_url=fallback_url
                                )
                                if snippet:
                                    snippets.append(snippet)
                            elif isinstance(sub_item, str) and sub_item.strip():
                                snippets.append(
                                    create_normalized_doc_snippet(
                                        content=sub_item.strip(),
                                        source=fallback_url,
                                        source_kind=self.source_id,
                                        relevance_score=0.9,
                                    )
                                )
                        # If parsing as JSON succeeded, do not emit the raw JSON string
                        # as fallback document content
                        continue

                snippet = self._normalize_result_item(item, fallback_url=fallback_url)
                if snippet:
                    snippets.append(snippet)

            elif isinstance(item, str) and item.strip():
                raw_str = item.strip()
                if raw_str.startswith(("[", "{")):
                    try:
                        sub_parsed = json.loads(raw_str)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        sub_parsed = None

                    if sub_parsed is not None:
                        nested_items = self._extract_nested_items(sub_parsed)
                        for sub_item in nested_items:
                            if isinstance(sub_item, dict):
                                snippet = self._normalize_result_item(
                                    sub_item, fallback_url=fallback_url
                                )
                                if snippet:
                                    snippets.append(snippet)
                            elif isinstance(sub_item, str) and sub_item.strip():
                                snippets.append(
                                    create_normalized_doc_snippet(
                                        content=sub_item.strip(),
                                        source=fallback_url,
                                        source_kind=self.source_id,
                                        relevance_score=0.9,
                                    )
                                )
                        continue

                snippets.append(
                    create_normalized_doc_snippet(
                        content=raw_str,
                        source=fallback_url,
                        source_kind=self.source_id,
                        relevance_score=0.9,
                    )
                )

        return snippets
