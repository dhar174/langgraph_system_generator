"""Orchestration and registry layer for documentation source precedence."""

from __future__ import annotations

import asyncio
import importlib
import logging
import re
from threading import Lock
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from langgraph_system_generator.generator.state import DocSnippet
from langgraph_system_generator.rag.base import (
    DocsProviderResult,
    DocsSourceProvider,
    DocsSourceStatus,
)
from langgraph_system_generator.rag.mcp_transport import _sanitize_text_credentials
from langgraph_system_generator.rag.providers.cached_vector import (
    CachedVectorDocsProvider,
)
from langgraph_system_generator.rag.providers.context7 import Context7DocsProvider
from langgraph_system_generator.rag.providers.langchain_local import (
    LangChainDocsLocalProvider,
)
from langgraph_system_generator.utils.config import settings

logger = logging.getLogger(__name__)


def _sanitize_warning(msg: str, max_chars: int = 200) -> str:
    """Sanitize provider error messages by redacting secrets and bounding length."""
    if not msg:
        return ""
    cleaned = _sanitize_text_credentials(str(msg))
    compact = " ".join(cleaned.split())
    if len(compact) > max_chars:
        return compact[: max(0, max_chars - 3)].rstrip() + "..."
    return compact


def _add_warning(
    warnings_list: List[str], warning: str, max_warnings: int = 10, max_chars: int = 200
) -> None:
    """Safely append a bounded, deduplicated warning."""
    if len(warnings_list) >= max_warnings:
        return
    sanitized = _sanitize_warning(warning, max_chars=max_chars)
    if sanitized and sanitized not in warnings_list:
        warnings_list.append(sanitized)


def _normalize_snippets_provenance(
    snippets: List[DocSnippet], provider_id: str
) -> List[DocSnippet]:
    """Ensure missing snippet provenance is attributed to the provider that returned them."""
    normalized: List[DocSnippet] = []
    for snippet in snippets:
        if not snippet.source_kind:
            normalized.append(
                snippet.model_copy(update={"source_kind": provider_id})
            )
        else:
            normalized.append(snippet)
    return normalized


def _load_docs_source_plugin(module_name: str, registry: DocsSourceRegistry) -> None:
    """Load a documentation source plugin module into the registry.

    Supports canonical 'register_docs_source_plugins' and backward-compatible 'register_docs_sources'.
    """
    try:
        mod = importlib.import_module(module_name)
        for fn_name in ("register_docs_source_plugins", "register_docs_sources"):
            register_func = getattr(mod, fn_name, None)
            if callable(register_func):
                register_func(registry)
                break
    except Exception as exc:
        logger.warning(
            "Failed loading docs source plugin module '%s': %s", module_name, exc
        )


class DocsRetrievalResult(BaseModel):
    """Aggregate result from executing documentation source precedence."""

    snippets: List[DocSnippet] = Field(default_factory=list)
    attempted_sources: List[str] = Field(default_factory=list)
    used_sources: List[str] = Field(default_factory=list)
    source_statuses: Dict[str, str] = Field(default_factory=dict)
    fallback_used: bool = False
    warnings: List[str] = Field(default_factory=list)


class DocsSourceRegistry:
    """Registry maintaining ordered documentation source providers."""

    def __init__(self, providers: Optional[List[DocsSourceProvider]] = None):
        if providers is not None:
            self._providers = list(providers)
        else:
            self._providers = [
                LangChainDocsLocalProvider(),
                Context7DocsProvider(),
                CachedVectorDocsProvider(),
            ]
            self._load_plugin_modules()

    def _load_plugin_modules(self) -> None:
        """Load optional plugin modules from settings to register custom sources."""
        for module_name in settings.docs_source_plugin_modules:
            _load_docs_source_plugin(module_name, self)

    def list_providers(self) -> List[DocsSourceProvider]:
        return list(self._providers)

    def get_provider(self, source_id: str) -> Optional[DocsSourceProvider]:
        for p in self._providers:
            if p.source_id == source_id:
                return p
        return None

    def register(self, provider: DocsSourceProvider, prepend: bool = False) -> None:
        """Register or replace a provider by source_id.

        When registering a provider whose source_id already exists:
        - preserve the existing provider's index by default (in-place replacement)
        - if prepend=True, explicitly move the replacement to index 0
        When registering a genuinely new provider:
        - if prepend=True, insert at index 0
        - otherwise, append to the end
        """
        existing_index = next(
            (
                index
                for index, existing in enumerate(self._providers)
                if existing.source_id == provider.source_id
            ),
            None,
        )

        if existing_index is not None:
            self._providers.pop(existing_index)
            if prepend:
                self._providers.insert(0, provider)
            else:
                self._providers.insert(existing_index, provider)
        else:
            if prepend:
                self._providers.insert(0, provider)
            else:
                self._providers.append(provider)

    def registered_source_ids(self) -> List[str]:
        """Return list of all registered source IDs."""
        return [p.source_id for p in self._providers]

    def clone(self) -> DocsSourceRegistry:
        return DocsSourceRegistry(providers=list(self._providers))


class DocsRetrievalService:
    """Orchestrates runtime documentation retrieval following source precedence."""

    def __init__(
        self,
        registry: Optional[DocsSourceRegistry] = None,
        precedence: Optional[List[str]] = None,
        plugin_modules: Optional[List[str]] = None,
    ):
        self.registry = registry or DocsSourceRegistry()
        if plugin_modules:
            for module_name in plugin_modules:
                _load_docs_source_plugin(module_name, self.registry)
        self._explicit_precedence = precedence is not None
        if precedence is not None:
            self.precedence = list(precedence)
        else:
            self.precedence = [p.source_id for p in self.registry.list_providers()]

    async def aretrieve(
        self,
        query: str,
        k: int = 10,
        mode: str = "live",
    ) -> DocsRetrievalResult:
        """Execute documentation retrieval following declared source precedence.

        Precedence in live mode:
            1. langchain-docs-local (or prepended plugins)
            2. context7
            3. cached / local vector store (cached_repo_docs / rag_index)

        In stub mode:
            Bypasses live sources, marks them SKIPPED, and executes only local/cached retrieval.
        """
        attempted: List[str] = []
        used: List[str] = []
        statuses: Dict[str, str] = {}
        warnings: List[str] = []
        accumulated_snippets: List[DocSnippet] = []

        if self._explicit_precedence:
            ordered_source_ids = list(self.precedence)
            for p in self.registry.list_providers():
                if p.source_id not in ordered_source_ids:
                    ordered_source_ids.append(p.source_id)
        else:
            ordered_source_ids = [p.source_id for p in self.registry.list_providers()]

        if mode == "stub":
            # Stub mode: strictly bypass live providers
            for source_id in ordered_source_ids:
                provider = self.registry.get_provider(source_id)
                if provider is None:
                    continue
                if not getattr(provider, "stub_safe", False):
                    statuses[source_id] = DocsSourceStatus.SKIPPED.value
                    continue

                try:
                    is_avail = provider.is_available(mode=mode)
                except Exception as exc:
                    statuses[source_id] = DocsSourceStatus.FAILED.value
                    _add_warning(
                        warnings, f"{source_id} availability check failed: {exc}"
                    )
                    continue

                if is_avail:
                    attempted.append(source_id)
                    try:
                        res = await provider.aretrieve(query, k=k, mode=mode)
                        statuses[source_id] = res.status.value
                        if res.status == DocsSourceStatus.SUCCESS and res.snippets:
                            used.append(source_id)
                            accumulated_snippets.extend(
                                _normalize_snippets_provenance(
                                    res.snippets, provider.source_id
                                )
                            )
                            break
                        elif (
                            res.status == DocsSourceStatus.FAILED
                            and res.error_message
                        ):
                            _add_warning(
                                warnings,
                                f"Cached docs retrieval failed: {res.error_message}"
                                if source_id == "cached_repo_docs"
                                else f"{source_id} retrieval failed: {res.error_message}",
                            )
                    except Exception as exc:
                        statuses[source_id] = DocsSourceStatus.FAILED.value
                        _add_warning(
                            warnings, f"{source_id} retrieval error: {exc}"
                        )
                else:
                    statuses[source_id] = DocsSourceStatus.UNAVAILABLE.value

            # Deduplicate and cap
            stub_deduped: Dict[str, DocSnippet] = {}
            for s in accumulated_snippets:
                key = f"{s.source}#{s.heading or ''}#{s.content[:60]}"
                if key not in stub_deduped:
                    stub_deduped[key] = s
            final_snippets = list(stub_deduped.values())[:k]

            final_used = [
                src
                for src in attempted
                if any(
                    s.source_kind == src
                    or s.source.startswith(f"{src}:")
                    or s.source == src
                    for s in final_snippets
                )
            ]
            fallback_used = any(
                src in ("cached_repo_docs", "rag_index") for src in final_used
            )

            for source_id in ordered_source_ids:
                if source_id not in statuses:
                    statuses[source_id] = DocsSourceStatus.SKIPPED.value

            return DocsRetrievalResult(
                snippets=final_snippets,
                attempted_sources=attempted,
                used_sources=final_used,
                source_statuses=statuses,
                fallback_used=fallback_used,
                warnings=warnings,
            )

        # Live mode: execute precedence order
        found_useful_live = False
        crosscheck_snippets: List[DocSnippet] = []

        for source_id in ordered_source_ids:
            provider = self.registry.get_provider(source_id)
            if provider is None:
                continue

            # If useful primary live docs were already found:
            if found_useful_live:
                # We only probe Context7 if crosscheck is enabled and source_id is context7
                if settings.docs_context7_crosscheck and source_id == "context7":
                    if source_id not in attempted:
                        attempted.append(source_id)
                    try:
                        is_avail = provider.is_available(mode=mode)
                    except Exception as exc:
                        statuses[source_id] = DocsSourceStatus.FAILED.value
                        _add_warning(
                            warnings, f"{source_id} availability check failed: {exc}"
                        )
                        break
                    if not is_avail:
                        statuses[source_id] = DocsSourceStatus.UNAVAILABLE.value
                        _add_warning(
                            warnings, f"{source_id} is unavailable for cross-check."
                        )
                        break

                    try:
                        res = await provider.aretrieve(query, k=k, mode=mode)
                        statuses[source_id] = res.status.value
                        if res.status == DocsSourceStatus.SUCCESS and res.snippets:
                            used.append(source_id)
                            crosscheck_snippets = _normalize_snippets_provenance(
                                res.snippets, provider.source_id
                            )
                        elif (
                            res.status == DocsSourceStatus.FAILED and res.error_message
                        ):
                            _add_warning(
                                warnings,
                                f"{source_id} cross-check failed: {res.error_message}",
                            )
                    except Exception as exc:
                        statuses[source_id] = DocsSourceStatus.FAILED.value
                        _add_warning(warnings, f"{source_id} cross-check error: {exc}")
                # STOP! Regardless of whether Context7 succeeded, failed, was empty, or unavailable,
                # we MUST break immediately and NEVER fall through to cached fallback!
                break

            # Normal precedence loop (found_useful_live is False)
            if source_id not in attempted:
                attempted.append(source_id)

            try:
                is_avail = provider.is_available(mode=mode)
            except Exception as exc:
                statuses[source_id] = DocsSourceStatus.FAILED.value
                _add_warning(warnings, f"{source_id} availability check failed: {exc}")
                continue

            if not is_avail:
                statuses[source_id] = DocsSourceStatus.UNAVAILABLE.value
                if source_id in ("langchain-docs-local", "context7"):
                    _add_warning(
                        warnings,
                        f"{source_id} is unavailable in live mode; proceeding to next source.",
                    )
                continue

            try:
                res = await provider.aretrieve(query, k=k, mode=mode)
            except Exception as exc:
                statuses[source_id] = DocsSourceStatus.FAILED.value
                _add_warning(warnings, f"{source_id} retrieval error: {exc}")
                continue

            statuses[source_id] = res.status.value

            if res.status == DocsSourceStatus.SUCCESS and res.snippets:
                used.append(source_id)
                accumulated_snippets.extend(
                    _normalize_snippets_provenance(
                        res.snippets, provider.source_id
                    )
                )

                if source_id == "langchain-docs-local":
                    found_useful_live = True
                    if settings.docs_context7_crosscheck:
                        continue
                    break
                elif source_id == "context7":
                    found_useful_live = True
                    break
                else:
                    break

            elif res.status == DocsSourceStatus.EMPTY:
                continue
            elif res.status == DocsSourceStatus.FAILED:
                if res.error_message:
                    _add_warning(
                        warnings, f"{source_id} retrieval failed: {res.error_message}"
                    )
                continue

        # Mark any remaining unattempted providers as skipped
        for source_id in ordered_source_ids:
            if source_id not in statuses:
                statuses[source_id] = DocsSourceStatus.SKIPPED.value

        # Cap and deduplicate snippets
        # If crosscheck_snippets exist, reserve quota so at least one Context7 snippet survives final cap (Finding 6)
        if crosscheck_snippets and accumulated_snippets:
            reserve_crosscheck = min(len(crosscheck_snippets), max(1, k // 3))
            primary_quota = max(1, k - reserve_crosscheck)
            candidate_snippets = (
                accumulated_snippets[:primary_quota]
                + crosscheck_snippets[:reserve_crosscheck]
            )
        elif crosscheck_snippets:
            candidate_snippets = crosscheck_snippets
        else:
            candidate_snippets = accumulated_snippets

        live_deduped: Dict[str, DocSnippet] = {}
        for s in candidate_snippets:
            key = f"{s.source}#{s.heading or ''}#{s.content[:60]}"
            if key not in live_deduped:
                live_deduped[key] = s

        final_snippets = list(live_deduped.values())[:k]

        # If crosscheck returned snippets and k >= 1, guarantee representation in final_snippets
        if crosscheck_snippets and not any(
            s.source_kind == "context7" for s in final_snippets
        ):
            if final_snippets:
                final_snippets[-1] = crosscheck_snippets[0]
            else:
                final_snippets.append(crosscheck_snippets[0])

        # Recompute used_sources strictly from final snippets (Finding 16)
        final_used = [
            src
            for src in attempted
            if any(
                s.source_kind == src
                or s.source.startswith(f"{src}:")
                or s.source == src
                for s in final_snippets
            )
        ]

        # fallback_used is True strictly if cached/local fallback actually contributed at least one final snippet
        fallback_used = any(s in ("cached_repo_docs", "rag_index") for s in final_used)

        return DocsRetrievalResult(
            snippets=final_snippets,
            attempted_sources=attempted,
            used_sources=final_used,
            source_statuses=statuses,
            fallback_used=fallback_used,
            warnings=warnings,
        )

    def retrieve(
        self,
        query: str,
        k: int = 5,
        mode: str = "live",
    ) -> List[Dict[str, Any]]:
        """Synchronous compatibility retrieve returning list of snippet dicts."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run, self.aretrieve(query, k=k, mode=mode)
                )
                res = future.result()
        else:
            res = asyncio.run(self.aretrieve(query, k=k, mode=mode))

        return [
            {
                "content": s.content,
                "source": s.source,
                "heading": s.heading,
                "relevance_score": s.relevance_score,
                "source_kind": s.source_kind,
            }
            for s in res.snippets
        ]

    def retrieve_for_pattern(
        self,
        pattern_name: str,
        k: int = 10,
        mode: str = "live",
    ) -> List[Dict[str, Any]]:
        """Synchronous compatibility method for pattern-specific documentation queries."""
        query = f"LangGraph {pattern_name} pattern implementation best practices"
        return self.retrieve(query, k=k, mode=mode)


_GLOBAL_SERVICE: Optional[DocsRetrievalService] = None
_GLOBAL_SERVICE_LOCK = Lock()


def get_default_docs_retrieval_service() -> DocsRetrievalService:
    """Return a process-local singleton DocsRetrievalService."""
    global _GLOBAL_SERVICE
    with _GLOBAL_SERVICE_LOCK:
        if _GLOBAL_SERVICE is None:
            _GLOBAL_SERVICE = DocsRetrievalService()
        return _GLOBAL_SERVICE


def _reset_docs_retrieval_service_for_tests() -> None:
    """Reset the global DocsRetrievalService instance for test isolation."""
    global _GLOBAL_SERVICE
    with _GLOBAL_SERVICE_LOCK:
        _GLOBAL_SERVICE = None
