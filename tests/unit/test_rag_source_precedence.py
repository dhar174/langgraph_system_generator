"""Unit tests for runtime documentation source precedence (Issue #375).

Tests:
1. Primary live provider succeeds (langchain-docs-local).
2. Primary unavailable, secondary (Context7) succeeds.
3. Primary fails with error, secondary (Context7) succeeds.
4. Both live providers unavailable/fail, fallback to cached vector docs.
5. Provider returns empty, continues to next provider in precedence chain.
6. Stub mode isolation canary (live providers never called).
7. Bounded oversized live results (character cap, score normalization).
8. ArchitectureSelector bypass regression (consumes live docs via provider-neutral service).
9. Cache reuse preserved across repeated cached fallback calls.
10. Truthful static/stub context pack provenance (no false claims of live attempts).
11. Custom provider registration via docs_source_plugin_modules.
12. Import isolation (no mandatory live MCP dependencies).
"""

from __future__ import annotations

import asyncio
from typing import Any, List
from unittest.mock import AsyncMock, patch

import pytest

from langgraph_system_generator.generator.agents.architecture_selector import (
    ArchitectureSelector,
)
from langgraph_system_generator.generator.nodes import (
    _build_generation_context_pack,
    _reset_docs_retriever_cache_for_tests,
    architecture_selection_node,
    get_cached_docs_retriever,
    rag_retrieval_node,
)
from langgraph_system_generator.generator.state import (
    Constraint,
    DocSnippet,
    DocsRetrievalFeedback,
)
from langgraph_system_generator.rag.base import (
    DocsProviderResult,
    DocsSourceProvider,
    DocsSourceStatus,
)
from langgraph_system_generator.rag.normalizer import (
    create_normalized_doc_snippet,
    normalize_relevance_score,
    normalize_snippet_content,
)
from langgraph_system_generator.rag.orchestrator import (
    DocsRetrievalService,
    DocsSourceRegistry,
    _reset_docs_retrieval_service_for_tests,
    get_default_docs_retrieval_service,
)
from langgraph_system_generator.rag.providers.cached_vector import (
    CachedVectorDocsProvider,
)
from langgraph_system_generator.rag.providers.context7 import (
    Context7DocsProvider,
)
from langgraph_system_generator.rag.providers.langchain_local import (
    LangChainDocsLocalProvider,
)
from langgraph_system_generator.utils.config import settings


class StubProvider(DocsSourceProvider):
    """Test stub provider with configurable behavior."""

    def __init__(
        self,
        source_id: str,
        available: bool = True,
        snippets: List[DocSnippet] | None = None,
        status: DocsSourceStatus = DocsSourceStatus.SUCCESS,
        error: str | None = None,
        raise_on_call: bool = False,
    ):
        self.source_id = source_id
        self.available = available
        self.snippets = snippets or []
        self.status = status
        self.error = error
        self.raise_on_call = raise_on_call
        self.call_count = 0
        self.last_query: str | None = None

    def is_available(self, mode: str = "live") -> bool:
        if mode == "stub" and self.source_id in ("langchain-docs-local", "context7"):
            return False
        return self.available

    async def aretrieve(
        self,
        query: str,
        k: int = 5,
        mode: str = "live",
    ) -> DocsProviderResult:
        self.call_count += 1
        self.last_query = query
        if self.raise_on_call:
            raise RuntimeError(f"Canary triggered: {self.source_id} called unexpectedly in {mode} mode!")
        if self.error:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.FAILED,
                error_message=self.error,
            )
        return DocsProviderResult(
            source_id=self.source_id,
            status=self.status,
            snippets=self.snippets[:k],
        )


@pytest.fixture(autouse=True)
def clean_services_and_caches():
    """Ensure every test runs with fresh registry and retriever cache."""
    _reset_docs_retrieval_service_for_tests()
    _reset_docs_retriever_cache_for_tests()
    yield
    _reset_docs_retrieval_service_for_tests()
    _reset_docs_retriever_cache_for_tests()


@pytest.mark.asyncio
async def test_primary_live_provider_succeeds():
    """When langchain-docs-local is available and returns docs, it is prioritized and fallback is not used."""
    primary_snippet = DocSnippet(
        content="Official LangChain local docs on StateGraph.",
        source="https://docs.langchain.com/graphs",
        source_kind="langchain-docs-local",
        relevance_score=0.95,
        heading="Graphs",
    )
    primary = StubProvider("langchain-docs-local", available=True, snippets=[primary_snippet])
    secondary = StubProvider("context7", available=True, snippets=[])
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[])

    service = DocsRetrievalService(precedence=["langchain-docs-local", "context7", "cached_repo_docs"])
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    result = await service.aretrieve("StateGraph", k=5, mode="live")

    assert len(result.snippets) == 1
    assert result.snippets[0].content == "Official LangChain local docs on StateGraph."
    assert result.snippets[0].source_kind == "langchain-docs-local"
    assert result.attempted_sources == ["langchain-docs-local"]
    assert result.used_sources == ["langchain-docs-local"]
    assert result.fallback_used is False
    assert primary.call_count == 1
    assert secondary.call_count == 0
    assert fallback.call_count == 0


@pytest.mark.asyncio
async def test_primary_unavailable_secondary_context7_succeeds():
    """When langchain-docs-local is unavailable, Context7 is queried and succeeds."""
    c7_snippet = DocSnippet(
        content="Context7 up-to-date documentation on LangGraph.",
        source="context7:langgraph",
        source_kind="context7",
        relevance_score=0.9,
        heading="LangGraph Overview",
    )
    primary = StubProvider("langchain-docs-local", available=False)
    secondary = StubProvider("context7", available=True, snippets=[c7_snippet])
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[])

    service = DocsRetrievalService(precedence=["langchain-docs-local", "context7", "cached_repo_docs"])
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    result = await service.aretrieve("LangGraph overview", k=5, mode="live")

    assert len(result.snippets) == 1
    assert result.snippets[0].source_kind == "context7"
    assert result.attempted_sources == ["langchain-docs-local", "context7"]
    assert result.source_statuses["langchain-docs-local"] == "unavailable"
    assert result.source_statuses["context7"] == "success"
    assert result.used_sources == ["context7"]
    assert result.fallback_used is False
    assert primary.call_count == 0
    assert secondary.call_count == 1
    assert fallback.call_count == 0


@pytest.mark.asyncio
async def test_primary_fails_with_error_secondary_context7_succeeds():
    """When primary provider fails with an error, error is logged and Context7 takes over."""
    c7_snippet = DocSnippet(
        content="Context7 fallback content.",
        source="context7:langgraph",
        source_kind="context7",
        relevance_score=0.88,
    )
    primary = StubProvider(
        "langchain-docs-local",
        available=True,
        error="Connection refused: 127.0.0.1:8000",
    )
    secondary = StubProvider("context7", available=True, snippets=[c7_snippet])
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[])

    service = DocsRetrievalService(precedence=["langchain-docs-local", "context7", "cached_repo_docs"])
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    result = await service.aretrieve("LangGraph overview", k=5, mode="live")

    assert len(result.snippets) == 1
    assert result.snippets[0].source_kind == "context7"
    assert result.attempted_sources == ["langchain-docs-local", "context7"]
    assert result.source_statuses["langchain-docs-local"] == "failed"
    assert result.source_statuses["context7"] == "success"
    assert result.used_sources == ["context7"]
    assert any("Connection refused" in w for w in result.warnings)
    assert primary.call_count == 1
    assert secondary.call_count == 1
    assert fallback.call_count == 0


@pytest.mark.asyncio
async def test_both_live_sources_unavailable_falls_back_to_cached():
    """When both primary and secondary are unavailable or fail, cached vector docs is used."""
    cached_snippet = DocSnippet(
        content="Local cached vector documentation.",
        source="cached:local_index",
        source_kind="cached_repo_docs",
        relevance_score=0.75,
    )
    primary = StubProvider("langchain-docs-local", available=False)
    secondary = StubProvider("context7", available=False)
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[cached_snippet])

    service = DocsRetrievalService(precedence=["langchain-docs-local", "context7", "cached_repo_docs"])
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    result = await service.aretrieve("Any topic", k=5, mode="live")

    assert len(result.snippets) == 1
    assert result.snippets[0].source_kind == "cached_repo_docs"
    assert result.fallback_used is True
    assert result.attempted_sources == ["langchain-docs-local", "context7", "cached_repo_docs"]
    assert result.used_sources == ["cached_repo_docs"]
    assert fallback.call_count == 1


@pytest.mark.asyncio
async def test_live_provider_empty_progresses_down_precedence():
    """When a provider returns EMPTY status, the service continues to the next provider."""
    next_snippet = DocSnippet(
        content="Secondary content after empty primary.",
        source="context7:docs",
        source_kind="context7",
        relevance_score=0.8,
    )
    primary = StubProvider("langchain-docs-local", available=True, status=DocsSourceStatus.EMPTY)
    secondary = StubProvider("context7", available=True, snippets=[next_snippet])
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[])

    service = DocsRetrievalService(precedence=["langchain-docs-local", "context7", "cached_repo_docs"])
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    result = await service.aretrieve("Specialized topic", k=5, mode="live")

    assert result.source_statuses["langchain-docs-local"] == "empty"
    assert result.source_statuses["context7"] == "success"
    assert result.used_sources == ["context7"]
    assert primary.call_count == 1
    assert secondary.call_count == 1


@pytest.mark.asyncio
async def test_stub_mode_isolation_canary():
    """In stub mode, live providers must NEVER be called, preventing network or credential leaks."""
    primary = StubProvider("langchain-docs-local", available=True, raise_on_call=True)
    secondary = StubProvider("context7", available=True, raise_on_call=True)
    cached_snippet = DocSnippet(
        content="Deterministic offline cached doc.",
        source="cache:offline",
        source_kind="cached_repo_docs",
        relevance_score=0.8,
    )
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[cached_snippet])

    service = DocsRetrievalService(precedence=["langchain-docs-local", "context7", "cached_repo_docs"])
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    # Calling in stub mode should NOT trigger the canary exceptions in primary or secondary
    result = await service.aretrieve("Prompt", k=5, mode="stub")

    assert primary.call_count == 0
    assert secondary.call_count == 0
    assert result.source_statuses["langchain-docs-local"] == "skipped"
    assert result.source_statuses["context7"] == "skipped"
    assert result.fallback_used is True
    assert result.used_sources == ["cached_repo_docs"]


def test_bounded_oversized_live_results():
    """Snippet contents are strictly bounded to docs_max_snippet_chars and scores normalized."""
    huge_content = "X" * 15000
    snippet = create_normalized_doc_snippet(
        content=huge_content,
        source="https://docs.langchain.com/huge",
        source_kind="langchain-docs-local",
        relevance_score=5.5,  # Out of [0, 1] range
        heading="Huge section",
        max_chars=1200,
    )

    assert len(snippet.content) <= 1200
    assert snippet.content.endswith("...")
    assert 0.0 <= snippet.relevance_score <= 1.0
    assert snippet.relevance_score == 1.0  # Clamped to 1.0


@pytest.mark.asyncio
async def test_architecture_selector_bypass_regression(monkeypatch):
    """ArchitectureSelector must query through provider-neutral service, consuming live docs instead of raw cache."""
    live_snippet = DocSnippet(
        content="LIVE_DOC_MARKER: LangGraph Router Pattern official guidance",
        source="langchain-docs-local:router",
        source_kind="langchain-docs-local",
        heading="Router Pattern",
        relevance_score=0.98,
    )
    cached_snippet = DocSnippet(
        content="STALE_CACHED_DOC_MARKER: Outdated router notes",
        source="cached:router",
        source_kind="cached_repo_docs",
        heading="Router Pattern",
        relevance_score=0.5,
    )

    primary = StubProvider("langchain-docs-local", available=True, snippets=[live_snippet])
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[cached_snippet])

    service = DocsRetrievalService(precedence=["langchain-docs-local", "cached_repo_docs"])
    service.registry.register(primary)
    service.registry.register(fallback)

    # Pass the provider-neutral service as docs_service to ArchitectureSelector
    selector = ArchitectureSelector(docs_service=service)

    prompt_docs = await selector._select_prompt_docs([])

    # Verify that LIVE_DOC_MARKER is present and won the selection race
    found_live = any("LIVE_DOC_MARKER" in doc.get("content", "") for doc in prompt_docs)
    found_stale = any("STALE_CACHED_DOC_MARKER" in doc.get("content", "") for doc in prompt_docs)

    assert found_live is True, "ArchitectureSelector failed to consume live docs from DocsRetrievalService"
    assert found_stale is False, "ArchitectureSelector should not have used stale cached docs when live succeeded"
    assert primary.call_count > 0, "Primary live provider was never called by ArchitectureSelector"


@pytest.mark.asyncio
async def test_cached_vector_provider_cache_reuse_preserved(monkeypatch):
    """Repeated calls to CachedVectorDocsProvider reuse process-local retriever cache."""
    counts = {"manager": 0, "retriever": 0}

    class CountingManager:
        def __init__(self, *args, **kwargs):
            counts["manager"] += 1

    class CountingRetriever:
        def __init__(self, manager):
            counts["retriever"] += 1

        def retrieve(self, *args, **kwargs):
            return [{"content": "Doc", "source": "s1", "relevance_score": 0.8}]

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.VectorStoreManager",
        CountingManager,
    )
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.DocsRetriever",
        CountingRetriever,
    )

    provider = CachedVectorDocsProvider()

    res1 = await provider.aretrieve("query 1", k=5, mode="live")
    res2 = await provider.aretrieve("query 2", k=5, mode="live")

    assert res1.status == DocsSourceStatus.SUCCESS
    assert res2.status == DocsSourceStatus.SUCCESS
    # Both calls should have reused the exact same cached instance
    assert counts["manager"] == 1
    assert counts["retriever"] == 1


def test_cli_shortcut_context_pack_truthfulness():
    """Static/shortcut context pack must not claim live sources were attempted."""
    pack = _build_generation_context_pack(
        {
            "user_prompt": "Build a workflow",
            "generation_mode": "stub",
            "constraints": [],
            "docs_context": [],
            "docs_retrieval_feedback": DocsRetrievalFeedback(
                attempted_sources=[],
                source_statuses={},
                used_sources=[],
                fallback_used=True,
                warnings=["Static shortcut used"],
            ),
        }
    )

    assert pack.fallback_used is True
    assert pack.source_summary["attempted_sources"] == []
    assert pack.source_summary["used_sources"] == []
    assert pack.source_summary["fallback_used"] is True
    assert pack.source_summary["docs_live_required"] is False
    assert "Static shortcut used" in pack.warnings


@pytest.mark.asyncio
async def test_custom_plugin_module_registration(monkeypatch):
    """docs_source_plugin_modules can register custom documentation providers."""
    class CustomDocsProvider(DocsSourceProvider):
        source_id: str = "custom_enterprise_wiki"

        def is_available(self, mode: str = "live") -> bool:
            return True

        async def aretrieve(self, query: str, k: int = 5, mode: str = "live") -> DocsProviderResult:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.SUCCESS,
                snippets=[
                    DocSnippet(
                        content="Custom internal enterprise guide",
                        source="wiki://internal",
                        source_kind="custom_enterprise_wiki",
                        relevance_score=0.99,
                    )
                ],
            )

    registry = DocsSourceRegistry()

    # Create dummy plugin module in sys.modules
    import sys
    import types

    fake_module = types.ModuleType("my_custom_docs_plugin")

    def register_docs_sources(reg: DocsSourceRegistry):
        reg.register(CustomDocsProvider())

    fake_module.register_docs_sources = register_docs_sources
    sys.modules["my_custom_docs_plugin"] = fake_module

    try:
        service = DocsRetrievalService(
            precedence=["custom_enterprise_wiki", "cached_repo_docs"],
            registry=registry,
            plugin_modules=["my_custom_docs_plugin"],
        )
        assert "custom_enterprise_wiki" in service.registry.registered_source_ids()

        result = await service.aretrieve("Search internal", k=5, mode="live")
        assert result.used_sources == ["custom_enterprise_wiki"]
        assert result.snippets[0].content == "Custom internal enterprise guide"
    finally:
        sys.modules.pop("my_custom_docs_plugin", None)


def test_import_isolation():
    """Core package and RAG module imports work cleanly without live MCP adapters."""
    import langgraph_system_generator.rag as rag_pkg
    import langgraph_system_generator.generator as gen_pkg

    assert hasattr(rag_pkg, "DocsRetrievalService")
    assert hasattr(rag_pkg, "DocsSourceRegistry")
    assert hasattr(rag_pkg, "CachedVectorDocsProvider")
    assert hasattr(rag_pkg, "LangChainDocsLocalProvider")
    assert hasattr(rag_pkg, "Context7DocsProvider")
    assert hasattr(gen_pkg, "DocsRetrievalFeedback")
