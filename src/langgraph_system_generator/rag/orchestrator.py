"""Orchestration and registry layer for documentation source precedence."""

from __future__ import annotations

import asyncio
import importlib
import logging
from threading import Lock
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from langgraph_system_generator.generator.state import DocSnippet
from langgraph_system_generator.rag.base import (
    DocsProviderResult,
    DocsSourceProvider,
    DocsSourceStatus,
)
from langgraph_system_generator.rag.providers.cached_vector import CachedVectorDocsProvider
from langgraph_system_generator.rag.providers.context7 import Context7DocsProvider
from langgraph_system_generator.rag.providers.langchain_local import LangChainDocsLocalProvider
from langgraph_system_generator.utils.config import settings

logger = logging.getLogger(__name__)


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
            try:
                mod = importlib.import_module(module_name)
                register_func = getattr(mod, "register_docs_source_plugins", None)
                if callable(register_func):
                    register_func(self)
            except Exception as exc:
                logger.warning("Failed loading docs source plugin module '%s': %s", module_name, exc)

    def list_providers(self) -> List[DocsSourceProvider]:
        return list(self._providers)

    def get_provider(self, source_id: str) -> Optional[DocsSourceProvider]:
        for p in self._providers:
            if p.source_id == source_id:
                return p
        return None

    def register(self, provider: DocsSourceProvider, prepend: bool = False) -> None:
        """Register or replace a provider by source_id."""
        self._providers = [p for p in self._providers if p.source_id != provider.source_id]
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
                try:
                    mod = importlib.import_module(module_name)
                    for fn_name in ("register_docs_sources", "register_docs_source_plugins"):
                        fn = getattr(mod, fn_name, None)
                        if callable(fn):
                            fn(self.registry)
                except Exception as exc:
                    logger.warning("Failed loading docs source plugin module '%s': %s", module_name, exc)
        self.precedence = list(precedence) if precedence is not None else [
            "langchain-docs-local",
            "context7",
            "cached_repo_docs",
            "rag_index",
        ]

    async def aretrieve(
        self,
        query: str,
        k: int = 10,
        mode: str = "live",
    ) -> DocsRetrievalResult:
        """Execute documentation retrieval following declared source precedence.

        Precedence in live mode:
            1. langchain-docs-local
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
        fallback_used = False

        ordered_source_ids = list(self.precedence)
        for p in self.registry.list_providers():
            if p.source_id not in ordered_source_ids:
                ordered_source_ids.append(p.source_id)

        if mode == "stub":
            # Stub mode: strictly bypass live providers
            for source_id in ordered_source_ids:
                provider = self.registry.get_provider(source_id)
                if provider is None:
                    continue
                if source_id in ("langchain-docs-local", "context7"):
                    statuses[source_id] = DocsSourceStatus.SKIPPED.value
                else:
                    if provider.is_available(mode=mode):
                        attempted.append(source_id)
                        res = await provider.aretrieve(query, k=k, mode=mode)
                        statuses[source_id] = res.status.value
                        if res.status == DocsSourceStatus.SUCCESS and res.snippets:
                            used.append(source_id)
                            accumulated_snippets.extend(res.snippets)
                            fallback_used = True
                            break
                        elif res.status == DocsSourceStatus.FAILED and res.error_message:
                            warnings.append(f"Cached docs retrieval failed: {res.error_message}")
                            fallback_used = True
                    else:
                        statuses[source_id] = DocsSourceStatus.UNAVAILABLE.value

            return DocsRetrievalResult(
                snippets=accumulated_snippets[:k],
                attempted_sources=attempted,
                used_sources=used,
                source_statuses=statuses,
                fallback_used=fallback_used or not bool(accumulated_snippets),
                warnings=warnings,
            )

        # Live mode: execute precedence order
        found_useful_live = False

        for source_id in ordered_source_ids:
            provider = self.registry.get_provider(source_id)
            if provider is None:
                continue

            attempted.append(source_id)

            if not provider.is_available(mode=mode):
                statuses[source_id] = DocsSourceStatus.UNAVAILABLE.value
                continue

            res = await provider.aretrieve(query, k=k, mode=mode)
            statuses[source_id] = res.status.value

            if res.status == DocsSourceStatus.SUCCESS and res.snippets:
                used.append(source_id)
                accumulated_snippets.extend(res.snippets)

                if source_id == "langchain-docs-local":
                    found_useful_live = True
                    if settings.docs_context7_crosscheck:
                        continue
                    break
                elif source_id == "context7":
                    found_useful_live = True
                    break
                else:
                    fallback_used = True
                    break

            elif res.status == DocsSourceStatus.EMPTY:
                continue
            elif res.status == DocsSourceStatus.FAILED:
                if res.error_message:
                    warnings.append(f"{source_id} retrieval failed: {res.error_message}")
                continue

        if any(s in ("cached_repo_docs", "rag_index") for s in used):
            fallback_used = True
        if not accumulated_snippets and attempted:
            fallback_used = True

        # Mark any remaining unattempted providers as skipped
        for source_id in ordered_source_ids:
            if source_id not in statuses:
                statuses[source_id] = DocsSourceStatus.SKIPPED.value

        # Cap and deduplicate snippets
        deduped: Dict[str, DocSnippet] = {}
        for s in accumulated_snippets:
            key = f"{s.source}#{s.heading or ''}#{s.content[:60]}"
            if key not in deduped:
                deduped[key] = s

        final_snippets = list(deduped.values())[:k]

        return DocsRetrievalResult(
            snippets=final_snippets,
            attempted_sources=attempted,
            used_sources=used,
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
                future = executor.submit(asyncio.run, self.aretrieve(query, k=k, mode=mode))
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
