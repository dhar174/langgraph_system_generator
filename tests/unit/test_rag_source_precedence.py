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
import json
import pytest

from langgraph_system_generator.generator.agents.architecture_selector import (
    ArchitectureSelector,
)
from langgraph_system_generator.generator.nodes import (
    _build_generation_context_pack,
    _reset_docs_retriever_cache_for_tests,
    architecture_selection_node,
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
)
from langgraph_system_generator.rag.orchestrator import (
    DocsRetrievalResult,
    DocsRetrievalService,
    DocsSourceRegistry,
    _reset_docs_retrieval_service_for_tests,
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
        snippets: list[DocSnippet] | None = None,
        status: DocsSourceStatus = DocsSourceStatus.SUCCESS,
        error: str | None = None,
        error_message: str | None = None,
        raise_on_call: bool = False,
        stub_safe: bool | None = None,
    ):
        self.source_id = source_id
        self.available = available
        self.snippets = snippets or []
        self.status = status
        self.error = error or error_message
        self.error_message = self.error
        self.raise_on_call = raise_on_call
        self.call_count = 0
        self.last_query: str | None = None
        if stub_safe is not None:
            self.stub_safe = stub_safe
        elif source_id == "cached_repo_docs":
            self.stub_safe = True

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
            raise RuntimeError(
                f"Canary triggered: {self.source_id} called unexpectedly in {mode} mode!"
            )
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


class StubLLM:
    """Stub LLM for tests avoiding network calls or API keys."""

    def __init__(self, *_args, **_kwargs):
        pass

    def with_structured_output(self, *_args, **_kwargs):
        return None

    async def ainvoke(self, *_args, **_kwargs):
        import json

        from langchain_core.messages import AIMessage

        payload = {
            "architecture_type": "router",
            "patterns": {"primary": "router", "secondary": []},
            "justification": "Stub router justification",
            "feedback": {"confidence": 1.0, "alternatives": [], "tradeoffs": []},
        }
        return AIMessage(content=json.dumps(payload))


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
    primary = StubProvider(
        "langchain-docs-local", available=True, snippets=[primary_snippet]
    )
    secondary = StubProvider("context7", available=True, snippets=[])
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[])

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
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

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
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

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
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
    fallback = StubProvider(
        "cached_repo_docs", available=True, snippets=[cached_snippet]
    )

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    result = await service.aretrieve("Any topic", k=5, mode="live")

    assert len(result.snippets) == 1
    assert result.snippets[0].source_kind == "cached_repo_docs"
    assert result.fallback_used is True
    assert result.attempted_sources == [
        "langchain-docs-local",
        "context7",
        "cached_repo_docs",
    ]
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
    primary = StubProvider(
        "langchain-docs-local", available=True, status=DocsSourceStatus.EMPTY
    )
    secondary = StubProvider("context7", available=True, snippets=[next_snippet])
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[])

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
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
    fallback = StubProvider(
        "cached_repo_docs", available=True, snippets=[cached_snippet]
    )

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
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

    primary = StubProvider(
        "langchain-docs-local", available=True, snippets=[live_snippet]
    )
    fallback = StubProvider(
        "cached_repo_docs", available=True, snippets=[cached_snippet]
    )

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "cached_repo_docs"]
    )
    service.registry.register(primary)
    service.registry.register(fallback)

    monkeypatch.setattr(
        "langgraph_system_generator.generator.agents.architecture_selector.ChatOpenAI",
        StubLLM,
    )

    # Pass the provider-neutral service as docs_service to ArchitectureSelector
    selector = ArchitectureSelector(docs_service=service)

    prompt_docs = await selector._select_prompt_docs([])

    # Verify that LIVE_DOC_MARKER is present and won the selection race
    found_live = any("LIVE_DOC_MARKER" in doc.get("content", "") for doc in prompt_docs)
    found_stale = any(
        "STALE_CACHED_DOC_MARKER" in doc.get("content", "") for doc in prompt_docs
    )

    assert (
        found_live is True
    ), "ArchitectureSelector failed to consume live docs from DocsRetrievalService"
    assert (
        found_stale is False
    ), "ArchitectureSelector should not have used stale cached docs when live succeeded"
    assert (
        primary.call_count > 0
    ), "Primary live provider was never called by ArchitectureSelector"


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

        async def aretrieve(
            self, query: str, k: int = 5, mode: str = "live"
        ) -> DocsProviderResult:
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
    import langgraph_system_generator.generator as gen_pkg
    import langgraph_system_generator.rag as rag_pkg

    assert hasattr(rag_pkg, "DocsRetrievalService")
    assert hasattr(rag_pkg, "DocsSourceRegistry")
    assert hasattr(rag_pkg, "CachedVectorDocsProvider")
    assert hasattr(rag_pkg, "LangChainDocsLocalProvider")
    assert hasattr(rag_pkg, "Context7DocsProvider")
    assert hasattr(gen_pkg, "DocsRetrievalFeedback")


@pytest.mark.asyncio
async def test_architecture_selector_docs_mode_stub_canary(monkeypatch):
    """ArchitectureSelector in stub mode must not call live providers during prompt docs selection."""
    from langgraph_system_generator.generator.agents.architecture_selector import (
        ArchitectureSelector,
    )

    primary = StubProvider("langchain-docs-local", available=True, raise_on_call=True)
    secondary = StubProvider("context7", available=True, raise_on_call=True)
    cached_snippet = DocSnippet(
        content="Offline doc for selector",
        source="cache:offline",
        source_kind="cached_repo_docs",
        relevance_score=0.9,
    )
    fallback = StubProvider(
        "cached_repo_docs", available=True, snippets=[cached_snippet]
    )

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    monkeypatch.setattr(
        "langgraph_system_generator.generator.agents.architecture_selector.ChatOpenAI",
        StubLLM,
    )

    selector = ArchitectureSelector(
        docs_service=service,
        docs_mode="stub",
    )

    await selector.select_architecture(
        constraints=[Constraint(type="goal", value="support router")],
        docs_context=[],
        mode="stub",
    )
    assert primary.call_count == 0
    assert secondary.call_count == 0
    assert fallback.call_count > 0
    assert selector.docs_retrieval_feedback_delta is not None
    assert selector.docs_retrieval_feedback_delta.used_sources == []
    assert selector.docs_retrieval_feedback_delta.fallback_used is False
    assert (
        selector.docs_retrieval_feedback_delta.stage_source_statuses[
            "architecture_selection"
        ]["cached_repo_docs"]
        == "success"
    )
    assert (
        "cached_repo_docs" in selector.docs_retrieval_feedback_delta.consulted_sources
    )


@pytest.mark.asyncio
async def test_provider_exception_boundary():
    """Uncaught exceptions in provider is_available or aretrieve must be trapped safely."""
    exploding_avail = StubProvider("langchain-docs-local", available=True)

    def boom_avail(mode="live"):
        raise RuntimeError("Fatal availability crash")

    exploding_avail.is_available = boom_avail

    exploding_retrieval = StubProvider("context7", available=True)

    async def boom_retrieve(query, k=5, mode="live"):
        raise ValueError("Fatal retrieval crash")

    exploding_retrieval.aretrieve = boom_retrieve

    safe_snippet = DocSnippet(
        content="Safe fallback content",
        source="cache:safe",
        source_kind="cached_repo_docs",
        relevance_score=0.8,
    )
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[safe_snippet])

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
    service.registry.register(exploding_avail)
    service.registry.register(exploding_retrieval)
    service.registry.register(fallback)

    result = await service.aretrieve("Crash test", k=5, mode="live")

    assert result.source_statuses["langchain-docs-local"] == "failed"
    assert result.source_statuses["context7"] == "failed"
    assert result.source_statuses["cached_repo_docs"] == "success"
    assert result.used_sources == ["cached_repo_docs"]
    assert len(result.warnings) >= 2
    assert any("Fatal availability crash" in w for w in result.warnings)
    assert any("Fatal retrieval crash" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_cache_non_eviction_on_live_provider_exception(monkeypatch):
    """RAG retrieval node errors must not evict healthy DocsRetriever cache entries."""
    import langgraph_system_generator.generator.nodes as nodes_mod

    mock_retriever = object()
    nodes_mod._DOCS_RETRIEVER_CACHE["default"] = mock_retriever

    class BrokenService:
        async def aretrieve(self, *args, **kwargs):
            raise ConnectionError("Live network timeout")

    monkeypatch.setattr(
        nodes_mod, "get_default_docs_retrieval_service", lambda: BrokenService()
    )

    state = {
        "user_prompt": "Hello test",
        "generation_mode": "live",
    }
    result = await rag_retrieval_node(state)

    assert result["docs_context"] == []
    assert result["docs_retrieval_feedback"].fallback_used is False
    assert "default" in nodes_mod._DOCS_RETRIEVER_CACHE
    assert nodes_mod._DOCS_RETRIEVER_CACHE["default"] is mock_retriever


@pytest.mark.asyncio
async def test_crosscheck_control_flow_primary_success_never_falls_back(monkeypatch):
    """When primary succeeds, Context7 failure/unavailability must NEVER trigger cached fallback."""
    monkeypatch.setattr(settings, "docs_context7_crosscheck", True)

    primary_snippet = DocSnippet(
        content="Primary LangChain documentation",
        source="langchain:docs",
        source_kind="langchain-docs-local",
        relevance_score=0.95,
    )
    primary = StubProvider(
        "langchain-docs-local", available=True, snippets=[primary_snippet]
    )
    secondary = StubProvider(
        "context7",
        available=True,
        status=DocsSourceStatus.FAILED,
        error_message="Rate limit 429",
    )
    fallback = StubProvider(
        "cached_repo_docs",
        available=True,
        snippets=[
            DocSnippet(
                content="Cached fallback",
                source="cache:doc",
                source_kind="cached_repo_docs",
                relevance_score=0.5,
            )
        ],
    )

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    result = await service.aretrieve("Query", k=5, mode="live")

    assert result.used_sources == ["langchain-docs-local"]
    assert result.fallback_used is False
    assert fallback.call_count == 0
    assert result.source_statuses.get("cached_repo_docs") == "skipped"


@pytest.mark.asyncio
async def test_crosscheck_capping_survival(monkeypatch):
    """Context7 crosscheck snippet must survive capping when primary fills quota."""
    monkeypatch.setattr(settings, "docs_context7_crosscheck", True)

    primary_snippets = [
        DocSnippet(
            content=f"Primary doc content {i}",
            source=f"langchain:doc{i}",
            source_kind="langchain-docs-local",
            relevance_score=0.9,
        )
        for i in range(5)
    ]
    primary = StubProvider(
        "langchain-docs-local", available=True, snippets=primary_snippets
    )
    c7_snippet = DocSnippet(
        content="Context7 freshest API updates",
        source="context7:freshest",
        source_kind="context7",
        relevance_score=0.85,
    )
    secondary = StubProvider("context7", available=True, snippets=[c7_snippet])
    fallback = StubProvider("cached_repo_docs", available=True, snippets=[])

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
    service.registry.register(primary)
    service.registry.register(secondary)
    service.registry.register(fallback)

    result = await service.aretrieve("LangGraph updates", k=5, mode="live")

    assert len(result.snippets) == 5
    assert any(s.source_kind == "context7" for s in result.snippets)
    assert "context7" in result.used_sources
    assert "langchain-docs-local" in result.used_sources
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_plugin_prepend_ordering():
    """Prepended custom provider must execute ahead of cached fallback and satisfy retrieval."""
    plugin_snippet = DocSnippet(
        content="High priority internal wiki snippet",
        source="wiki:priority",
        source_kind="custom_wiki",
        relevance_score=0.99,
    )
    plugin_provider = StubProvider(
        "custom_wiki", available=True, snippets=[plugin_snippet]
    )
    cached_provider = StubProvider(
        "cached_repo_docs",
        available=True,
        snippets=[
            DocSnippet(
                content="Cached doc",
                source="cache:1",
                source_kind="cached_repo_docs",
                relevance_score=0.5,
            )
        ],
    )

    service = DocsRetrievalService(precedence=[])
    service.registry.register(cached_provider)
    service.registry.register(plugin_provider, prepend=True)

    result = await service.aretrieve("Internal question", k=5, mode="live")

    assert result.used_sources == ["custom_wiki"]
    assert result.fallback_used is False
    assert cached_provider.call_count == 0
    assert result.attempted_sources[0] == "custom_wiki"


def test_faiss_distance_ordering_and_fields():
    """FAISS distance ordering converts smaller distance to higher similarity without 1.0 clamping."""
    from langgraph_system_generator.rag.retriever import RetrievedSnippet

    snippet = RetrievedSnippet(
        content="Some text",
        source="file.md",
        relevance_score=0.9,
        distance=0.1,
        score_kind="distance",
    )
    assert snippet["distance"] == 0.1
    assert snippet["score_kind"] == "distance"

    score_small_dist = normalize_relevance_score(0.1, is_distance=True)
    score_large_dist = normalize_relevance_score(2.0, is_distance=True)

    assert score_small_dist > score_large_dist
    assert 0.0 <= score_small_dist <= 1.0
    assert 0.0 <= score_large_dist <= 1.0


@pytest.mark.asyncio
async def test_zero_score_preservation():
    """Scores of 0.0 must be preserved rather than truth-value defaulting to 1.0."""
    local_provider = LangChainDocsLocalProvider()
    snippets_local = local_provider._extract_snippets_from_payload(
        {
            "snippets": [
                {
                    "content": "Zero score doc",
                    "url": "https://python.langchain.com/zero",
                    "score": 0.0,
                }
            ]
        },
        fallback_url="https://python.langchain.com",
    )
    assert len(snippets_local) == 1
    assert snippets_local[0].relevance_score == 0.0

    c7_provider = Context7DocsProvider()
    snippets_c7 = c7_provider._parse_snippets(
        {
            "snippets": [
                {
                    "text": "Zero score c7",
                    "url": "https://context7.ai/doc",
                    "score": 0.0,
                }
            ]
        },
        fallback_source="https://context7.ai",
    )
    assert len(snippets_c7) == 1
    assert snippets_c7[0].relevance_score == 0.0


def test_context7_explicit_endpoint_availability(monkeypatch):
    """Context7 is available when explicit endpoint is given or default endpoint is enabled even if api_key is omitted."""
    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(settings, "context7_docs_enabled", True)
    monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)
    monkeypatch.delenv("CONTEXT7_MCP_URL", raising=False)

    provider = Context7DocsProvider(
        api_key=None, endpoint_url="http://localhost:8080/mcp"
    )
    assert provider.is_available("live") is True

    # Under Option A, the default hosted endpoint is available when enabled without requiring API key
    provider_default = Context7DocsProvider(api_key=None, endpoint_url=None)
    assert provider_default.is_available("live") is True

    # When context7_docs_enabled is False, it is unavailable
    monkeypatch.setattr(settings, "context7_docs_enabled", False)
    assert provider_default.is_available("live") is False


def test_custom_provider_provenance_in_context_pack():
    """Custom provider source_kind must be preserved and counted in GenerationContextPack."""
    state = {
        "user_prompt": "Enterprise agent",
        "generation_mode": "live",
        "constraints": [],
        "docs_context": [
            DocSnippet(
                content="Enterprise internal docs",
                source="wiki://enterprise",
                source_kind="custom_enterprise_wiki",
                relevance_score=0.98,
            )
        ],
        "docs_retrieval_feedback": {
            "attempted_sources": ["custom_enterprise_wiki"],
            "source_statuses": {"custom_enterprise_wiki": "success"},
            "used_sources": ["custom_enterprise_wiki"],
            "fallback_used": False,
            "warnings": [],
        },
    }

    pack = _build_generation_context_pack(state)

    assert len(pack.docs_snippets) == 1
    assert pack.docs_snippets[0]["source_kind"] == "custom_enterprise_wiki"
    assert pack.source_summary["source_counts"].get("custom_enterprise_wiki") == 1
    assert "custom_enterprise_wiki" in pack.source_summary["source_precedence"]
    assert pack.source_summary["fallback_used"] is False


@pytest.mark.asyncio
async def test_architecture_retrieval_feedback_merges_into_state(monkeypatch):
    """Architecture selection node merges docs retrieval feedback delta into state."""
    initial_feedback = DocsRetrievalFeedback(
        attempted_sources=["langchain-docs-local"],
        source_statuses={"langchain-docs-local": "success"},
        used_sources=["langchain-docs-local"],
        fallback_used=False,
        warnings=["Initial warning"],
    )

    state = {
        "user_prompt": "Customer support router",
        "generation_mode": "stub",
        "constraints": [],
        "docs_context": [],
        "docs_retrieval_feedback": initial_feedback,
    }

    monkeypatch.setattr(
        "langgraph_system_generator.generator.agents.architecture_selector.ChatOpenAI",
        StubLLM,
    )

    result = await architecture_selection_node(state)

    assert "docs_retrieval_feedback" in result
    merged = result["docs_retrieval_feedback"]
    assert "langchain-docs-local" in merged.attempted_sources
    assert "cached_repo_docs" in merged.attempted_sources
    assert "Initial warning" in merged.warnings


@pytest.mark.asyncio
async def test_context7_resolve_library_id_to_query_docs_workflow(monkeypatch):
    """Context7 queries resolve-library-id then query-docs with unmasked Bearer header."""
    import httpx

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(settings, "context7_docs_enabled", True)

    calls = []

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        calls.append({"url": str(url), "headers": headers or {}, "json": json or {}})
        method = (json or {}).get("params", {}).get("name")
        req_id = (json or {}).get("id", 1)
        if method == "resolve-library-id":
            res_content = '{"libraries": [{"library_id": "langgraph-core-id"}]}'
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"text": res_content}]},
                },
            )
        elif method == "query-docs":
            res_content = '{"snippets": [{"snippet": "Query docs snippet", "url": "https://c7.ai/docs", "score": 0.9}]}'
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"text": res_content}]},
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = Context7DocsProvider(
        api_key="secret-c7-key-123", endpoint_url="http://context7.mock/mcp"
    )

    res = await provider.aretrieve("LangGraph graph", k=2, mode="live")

    assert res.status == DocsSourceStatus.SUCCESS
    assert len(res.snippets) == 1
    assert res.snippets[0].content == "Query docs snippet"
    assert len(calls) == 2
    assert calls[0]["headers"].get("Authorization") == "Bearer secret-c7-key-123"
    assert calls[1]["headers"].get("Authorization") == "Bearer secret-c7-key-123"
    assert calls[0]["json"]["params"]["name"] == "resolve-library-id"
    assert calls[1]["json"]["params"]["name"] == "query-docs"


def test_sanitized_warnings_redaction():
    """Warnings must redact Bearer tokens and API keys and bound lengths."""
    from langgraph_system_generator.rag.orchestrator import (
        _add_warning,
        _sanitize_warning,
    )

    dirty = "Failed with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and api_key=sk-1234567890abcdef"
    clean = _sanitize_warning(dirty)
    assert "[REDACTED]" in clean
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in clean
    assert "sk-1234567890abcdef" not in clean

    warnings = []
    for i in range(15):
        _add_warning(warnings, f"Warning {i}")
    assert len(warnings) == 10


@pytest.mark.asyncio
async def test_langchain_local_connection_error_breaks_loop(monkeypatch):
    """Network connection failure breaks tool compatibility loop immediately."""
    import httpx

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)

    call_count = 0

    async def mock_post(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = LangChainDocsLocalProvider(endpoint_url="http://127.0.0.1:9999/mcp")
    res = await provider.aretrieve("Query", k=3, mode="live")
    assert res.status == DocsSourceStatus.FAILED
    assert call_count == 1
    assert "Connection refused" in (res.error_message or "")


@pytest.mark.asyncio
async def test_mcp_transport_protocol_headers_and_metadata(monkeypatch):
    """call_mcp_tool sends protocol version 2026-07-28, streamable headers, and _meta."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import call_mcp_tool

    captured = {}

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        captured["url"] = str(url)
        captured["headers"] = dict(headers or {})
        captured["json"] = dict(json or {})
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": (json or {}).get("id", 1),
                "result": {"content": [{"text": "success"}]},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    res = await call_mcp_tool(
        endpoint_url="http://test.mcp/endpoint",
        tool_name="test_tool",
        arguments={"arg1": "val1"},
        api_key="secret-key",
    )
    assert res.get("result") == {"content": [{"text": "success"}]}
    assert captured["headers"].get("MCP-Protocol-Version") == "2026-07-28"
    assert captured["headers"].get("Mcp-Method") == "tools/call"
    assert captured["headers"].get("Mcp-Name") == "test_tool"
    assert captured["headers"].get("Authorization") == "Bearer secret-key"
    assert captured["json"]["method"] == "tools/call"
    assert captured["json"]["params"]["name"] == "test_tool"
    meta = captured["json"]["params"]["_meta"]
    assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
    assert "io.modelcontextprotocol/clientCapabilities" in meta
    assert "protocolVersion" not in meta


@pytest.mark.asyncio
async def test_mcp_transport_sse_response_parsing(monkeypatch):
    """call_mcp_tool handles text/event-stream SSE responses."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import call_mcp_tool

    sse_body = (
        "event: message\n"
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "sse-result"}]}}\n\n'
    )

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=sse_body.encode("utf-8"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    res = await call_mcp_tool(
        endpoint_url="http://test.mcp/sse",
        tool_name="test_tool",
        arguments={},
    )
    assert res.get("result") == {"content": [{"text": "sse-result"}]}


@pytest.mark.asyncio
async def test_fallback_used_semantics_cases_abc():
    """Verify fallback_used semantics: Case A (True), Case B (False), Case C (False)."""
    # Case A: live failed, cached fallback returned snippets -> fallback_used=True
    primary_a = StubProvider(
        "langchain-docs-local", available=True, error="network failure"
    )
    fallback_a = StubProvider(
        "cached_repo_docs",
        available=True,
        snippets=[
            DocSnippet(
                content="Cached text", source="cache", source_kind="cached_repo_docs"
            )
        ],
    )
    service_a = DocsRetrievalService(
        precedence=["langchain-docs-local", "cached_repo_docs"]
    )
    service_a.registry.register(primary_a)
    service_a.registry.register(fallback_a)
    res_a = await service_a.aretrieve("test query", mode="live")
    assert res_a.fallback_used is True
    assert "cached_repo_docs" in res_a.used_sources

    # Case B: live failed, cached fallback returned 0 snippets -> fallback_used=False
    primary_b = StubProvider(
        "langchain-docs-local", available=True, error="network failure"
    )
    fallback_b = StubProvider("cached_repo_docs", available=True, snippets=[])
    service_b = DocsRetrievalService(
        precedence=["langchain-docs-local", "cached_repo_docs"]
    )
    service_b.registry.register(primary_b)
    service_b.registry.register(fallback_b)
    res_b = await service_b.aretrieve("test query", mode="live")
    assert res_b.fallback_used is False
    assert res_b.used_sources == []

    # Case C: live failed, cached fallback raised an exception -> fallback_used=False
    primary_c = StubProvider(
        "langchain-docs-local", available=True, error="network failure"
    )
    fallback_c = StubProvider("cached_repo_docs", available=True, error="disk corrupt")
    service_c = DocsRetrievalService(
        precedence=["langchain-docs-local", "cached_repo_docs"]
    )
    service_c.registry.register(primary_c)
    service_c.registry.register(fallback_c)
    res_c = await service_c.aretrieve("test query", mode="live")
    assert res_c.fallback_used is False
    assert res_c.used_sources == []


@pytest.mark.asyncio
async def test_context7_resolve_library_empty_returns_empty(monkeypatch):
    """Context7 returns EMPTY without calling query-docs or search when resolve-library-id yields no library."""
    import httpx

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(settings, "context7_docs_enabled", True)

    tools_called = []

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        name = (json or {}).get("params", {}).get("name")
        tools_called.append(name)
        req_id = (json or {}).get("id", 1)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"text": '{"libraries": []}'}]},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = Context7DocsProvider(endpoint_url="http://mock.c7/mcp")
    res = await provider.aretrieve("Unknown Library", mode="live")

    assert res.status == DocsSourceStatus.EMPTY
    assert len(res.snippets) == 0
    assert tools_called == ["resolve-library-id"]


@pytest.mark.asyncio
async def test_context7_query_docs_failed_returns_failed(monkeypatch):
    """Context7 returns FAILED when query-docs encounters a server error."""
    import httpx

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(settings, "context7_docs_enabled", True)

    tools_called = []

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        name = (json or {}).get("params", {}).get("name")
        tools_called.append(name)
        req_id = (json or {}).get("id", 1)
        if name == "resolve-library-id":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"text": '{"libraries": [{"library_id": "lib-456"}]}'}
                        ]
                    },
                },
            )
        elif name == "query-docs":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32000,
                        "message": "Database error in query-docs",
                    },
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = Context7DocsProvider(endpoint_url="http://mock.c7/mcp")
    res = await provider.aretrieve("Some topic", mode="live")

    assert res.status == DocsSourceStatus.FAILED
    assert "Database error in query-docs" in (res.error_message or "")
    assert tools_called == ["resolve-library-id", "query-docs"]


@pytest.mark.asyncio
async def test_context7_unknown_tool_falls_back_to_search(monkeypatch):
    """Context7 falls back to search only when server explicitly rejects tool as unknown."""
    import httpx

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(settings, "context7_docs_enabled", True)

    tools_called = []

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        name = (json or {}).get("params", {}).get("name")
        tools_called.append(name)
        req_id = (json or {}).get("id", 1)
        if name == "resolve-library-id":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": "Tool resolve-library-id not found",
                    },
                },
            )
        elif name == "search":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "text": '{"results": [{"snippet": "Search result", "url": "https://c7.ai"}]}'
                            }
                        ]
                    },
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = Context7DocsProvider(endpoint_url="http://mock.c7/mcp")
    res = await provider.aretrieve("Some query", mode="live")

    assert res.status == DocsSourceStatus.SUCCESS
    assert len(res.snippets) == 1
    assert res.snippets[0].content == "Search result"
    assert tools_called == ["resolve-library-id", "search"]


@pytest.mark.asyncio
async def test_architecture_selector_transient_docs_provenance_isolation(monkeypatch):
    """Pipeline integration: RAG live docs remain pure in used_sources and context pack even if ArchitectureSelector uses fallback."""
    live_snippet = DocSnippet(
        content="Official LangGraph Graph docs",
        source="langchain://live/graph",
        source_kind="langchain-docs-local",
        relevance_score=0.96,
    )
    rag_provider = StubProvider(
        "langchain-docs-local", available=True, snippets=[live_snippet]
    )
    rag_service = DocsRetrievalService(
        precedence=["langchain-docs-local", "cached_repo_docs"]
    )
    rag_service.registry.register(rag_provider)

    from langgraph_system_generator.generator import nodes as nodes_mod

    monkeypatch.setattr(
        nodes_mod, "get_default_docs_retrieval_service", lambda: rag_service
    )

    state = {
        "user_prompt": "Build a state graph router",
        "generation_mode": "live",
        "constraints": [Constraint(type="goal", value="support router")],
    }

    rag_out = await rag_retrieval_node(state)
    state.update(rag_out)

    assert state["docs_retrieval_feedback"].used_sources == ["langchain-docs-local"]
    assert state["docs_retrieval_feedback"].fallback_used is False

    selector_live = StubProvider(
        "langchain-docs-local", available=True, error="network blip"
    )
    cached_doc = DocSnippet(
        content="Offline selector facts",
        source="cache://facts",
        source_kind="cached_repo_docs",
        relevance_score=0.90,
    )
    selector_fallback = StubProvider(
        "cached_repo_docs", available=True, snippets=[cached_doc]
    )
    selector_service = DocsRetrievalService(
        precedence=["langchain-docs-local", "cached_repo_docs"]
    )
    selector_service.registry.register(selector_live)
    selector_service.registry.register(selector_fallback)

    monkeypatch.setattr(
        nodes_mod, "get_default_docs_retrieval_service", lambda: selector_service
    )
    monkeypatch.setattr(
        "langgraph_system_generator.generator.agents.architecture_selector.ChatOpenAI",
        StubLLM,
    )

    arch_out = await architecture_selection_node(state)
    state.update(arch_out)

    feedback = state["docs_retrieval_feedback"]
    assert feedback.used_sources == ["langchain-docs-local"]
    assert feedback.fallback_used is False
    assert feedback.stage_source_statuses["rag"]["langchain-docs-local"] == "success"
    assert (
        feedback.stage_source_statuses["architecture_selection"]["cached_repo_docs"]
        == "success"
    )
    assert "cached_repo_docs" in feedback.consulted_sources

    pack = _build_generation_context_pack(state)
    assert pack.source_summary["used_sources"] == ["langchain-docs-local"]
    assert pack.source_summary["fallback_used"] is False
    assert (
        pack.source_summary["stage_source_statuses"] == feedback.stage_source_statuses
    )


@pytest.mark.asyncio
async def test_concurrent_architecture_feedback_determinism(monkeypatch):
    """Concurrent query retrieval reduces source statuses deterministically regardless of arrival order."""
    from langgraph_system_generator.generator.agents.architecture_selector import (
        ArchitectureSelector,
    )

    class AsyncStaggeredService:
        async def aretrieve(self, query: str, k: int = 5, mode: str = "live"):
            if "deep agent" in query.lower() or "planning" in query.lower():
                await asyncio.sleep(0.01)
                return DocsRetrievalResult(
                    attempted_sources=["context7"],
                    source_statuses={"context7": "failed"},
                    used_sources=[],
                    fallback_used=False,
                    warnings=["Query 2 failed"],
                )
            elif "hierarchical" in query.lower() or "worker" in query.lower():
                await asyncio.sleep(0.02)
                return DocsRetrievalResult(
                    attempted_sources=["context7"],
                    source_statuses={"context7": "empty"},
                    used_sources=[],
                    fallback_used=False,
                )
            else:
                await asyncio.sleep(0.05)
                return DocsRetrievalResult(
                    snippets=[
                        DocSnippet(
                            content="LangGraph core",
                            source="c7",
                            source_kind="context7",
                        )
                    ],
                    attempted_sources=["context7"],
                    source_statuses={"context7": "success"},
                    used_sources=["context7"],
                    fallback_used=False,
                )

    monkeypatch.setattr(
        "langgraph_system_generator.generator.agents.architecture_selector.ChatOpenAI",
        StubLLM,
    )

    selector = ArchitectureSelector(
        docs_service=AsyncStaggeredService(),
        docs_mode="live",
    )

    await selector.select_architecture(
        constraints=[Constraint(type="goal", value="support router")],
        docs_context=[],
        mode="live",
    )

    delta = selector.docs_retrieval_feedback_delta
    assert delta is not None
    assert delta.source_statuses["context7"] == "success"
    assert (
        delta.stage_source_statuses["architecture_selection"]["context7"] == "success"
    )


@pytest.mark.asyncio
async def test_langchain_local_http_error_does_not_retry_candidates(monkeypatch):
    """Transport/HTTP failures must stop LangChain candidate tool probing immediately after 1 request."""
    import httpx

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)

    call_count = 0

    async def mock_post(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(404, text="Not Found: endpoint /mcp does not exist")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = LangChainDocsLocalProvider(
        endpoint_url="http://127.0.0.1:9999/wrong-path"
    )
    res = await provider.aretrieve("Query", k=3, mode="live")
    assert res.status == DocsSourceStatus.FAILED
    assert call_count == 1
    assert "404" in (res.error_message or "")


@pytest.mark.asyncio
async def test_context7_http_404_fails_without_search_fallback(monkeypatch):
    """Transport/HTTP 404 on Context7 must fail the provider immediately without falling back to search."""
    import httpx

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(settings, "context7_docs_enabled", True)

    tools_called = []

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        name = (json or {}).get("params", {}).get("name")
        tools_called.append(name)
        return httpx.Response(404, text="Not Found: reverse proxy error")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = Context7DocsProvider(endpoint_url="http://mock.c7/wrong-mcp")
    res = await provider.aretrieve("Some topic", mode="live")

    assert res.status == DocsSourceStatus.FAILED
    assert "404" in (res.error_message or "")
    # Must NOT have fallen back to 'search' against the nonexistent endpoint!
    assert tools_called == ["resolve-library-id"]


@pytest.mark.asyncio
async def test_mcp_transport_multi_event_sse_with_progress_notifications(monkeypatch):
    """call_mcp_tool consumes progress notifications and returns the final matching response."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import call_mcp_tool

    sse_body = (
        'data: {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 1, "total": 2}}\n\n'
        'data: {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 2, "total": 2}}\n\n'
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "final-sse-result"}]}}\n\n'
    )

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=sse_body.encode("utf-8"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    res = await call_mcp_tool(
        endpoint_url="http://test.mcp/sse-stream",
        tool_name="test_tool",
        arguments={},
        request_id=1,
    )
    assert res.get("id") == 1
    assert res.get("result") == {"content": [{"text": "final-sse-result"}]}


@pytest.mark.asyncio
async def test_mcp_transport_sse_ignores_unrelated_response_id(monkeypatch):
    """call_mcp_tool ignores unrelated response IDs and returns matching id, or raises parse error."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import (
        MCPTransportError,
        call_mcp_tool,
    )

    # Sub-case A: Unrelated response ID alongside matching response ID
    sse_body_mixed = (
        'data: {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 1}}\n\n'
        'data: {"jsonrpc": "2.0", "id": 999, "result": {"content": [{"text": "unrelated-id-result"}]}}\n\n'
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"text": "matching-id-result"}]}}\n\n'
    )

    async def mock_post_mixed(self, url, headers=None, json=None, timeout=None):
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=sse_body_mixed.encode("utf-8"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_mixed)

    res = await call_mcp_tool(
        endpoint_url="http://test.mcp/sse-mixed",
        tool_name="test_tool",
        arguments={},
        request_id=1,
    )
    assert res.get("id") == 1
    assert res.get("result") == {"content": [{"text": "matching-id-result"}]}

    # Sub-case B: Only unrelated response ID exists in stream -> raises parse error
    sse_body_unrelated_only = 'data: {"jsonrpc": "2.0", "id": 999, "result": {"content": [{"text": "unrelated-id-result"}]}}\n\n'

    async def mock_post_unrelated(self, url, headers=None, json=None, timeout=None):
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=sse_body_unrelated_only.encode("utf-8"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_unrelated)

    with pytest.raises(MCPTransportError) as exc_info:
        await call_mcp_tool(
            endpoint_url="http://test.mcp/sse-unrelated",
            tool_name="test_tool",
            arguments={},
            request_id=1,
        )
    assert exc_info.value.error_kind == "parse"
    assert "No valid JSON-RPC response" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mcp_transport_structured_jsonrpc_error_on_http_400(monkeypatch):
    """call_mcp_tool preserves structured JSON-RPC error payload on HTTP 400 for provider compatibility probing."""
    import json
    import httpx
    from langgraph_system_generator.rag.mcp_transport import call_mcp_tool

    http_400_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": -32601,
            "message": "Method not found",
        },
    }

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        return httpx.Response(
            400,
            headers={"Content-Type": "application/json"},
            json=http_400_body,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    # 1. Direct call_mcp_tool test
    payload = await call_mcp_tool(
        endpoint_url="http://test.mcp/compat",
        tool_name="search",
        arguments={"query": "test"},
        request_id=1,
    )
    assert payload.get("id") == 1
    assert payload.get("error", {}).get("code") == -32601
    assert payload.get("error", {}).get("message") == "Method not found"

    # 2. Provider integration: compatibility probing continues on structured tool error
    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    tools_called = []

    async def mock_provider_post(self, url, *args, **kwargs):
        payload = kwargs.get("json") or {}
        tool_name = payload.get("params", {}).get("name")
        req_id = payload.get("id", 1)
        tools_called.append(tool_name)
        if tool_name == "search":
            return httpx.Response(
                400,
                headers={"Content-Type": "application/json"},
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": "Method not found"},
                },
            )
        elif tool_name == "search_docs_by_lang_chain":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "text": json.dumps(
                                    [{"content": "Success snippet", "url": "http://ok"}]
                                )
                            }
                        ]
                    },
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_provider_post)

    provider = LangChainDocsLocalProvider(
        endpoint_url="http://test.mcp/compat-provider"
    )
    res = await provider.aretrieve("Query", k=3, mode="live")
    assert res.status == DocsSourceStatus.SUCCESS
    assert len(res.snippets) == 1
    assert res.snippets[0].content == "Success snippet"
    assert tools_called == ["search", "search_docs_by_lang_chain"]


@pytest.mark.asyncio
async def test_mcp_transport_plain_http_failure_raises_transport_error(monkeypatch):
    """call_mcp_tool raises MCPTransportError on plain HTTP 404 failure and provider halts probing."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import (
        MCPTransportError,
        call_mcp_tool,
    )

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        return httpx.Response(404, text="Not Found: reverse proxy route missing")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(MCPTransportError) as exc_info:
        await call_mcp_tool(
            endpoint_url="http://test.mcp/broken-proxy",
            tool_name="search",
            arguments={"query": "test"},
            request_id=1,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.error_kind == "http"
    assert "Not Found: reverse proxy route missing" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mcp_transport_generic_json_error_on_non_2xx_raises_transport_error(
    monkeypatch,
):
    """call_mcp_tool does not treat arbitrary HTTP 404/400 JSON bodies without matching id as tool-not-found."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import (
        MCPTransportError,
        call_mcp_tool,
    )

    async def mock_post(self, url, headers=None, json=None, timeout=None):
        return httpx.Response(404, json={"detail": "Route /tools/call not registered"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(MCPTransportError) as exc_info:
        await call_mcp_tool(
            endpoint_url="http://test.mcp/api",
            tool_name="search",
            arguments={"query": "test"},
            request_id=1,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.error_kind == "http"


def test_registry_replacement_preserves_builtin_precedence():
    """Replacing an existing provider by source_id preserves its index in the registry."""
    registry = DocsSourceRegistry()
    initial_ids = registry.registered_source_ids()
    assert initial_ids == [
        "langchain-docs-local",
        "context7",
        "cached_repo_docs",
    ]

    replacement_primary = StubProvider(
        "langchain-docs-local",
        available=True,
        snippets=[
            DocSnippet(
                content="Replaced primary",
                source="test:1",
                source_kind="langchain-docs-local",
            )
        ],
    )
    registry.register(replacement_primary)

    after_ids = registry.registered_source_ids()
    assert after_ids == [
        "langchain-docs-local",
        "context7",
        "cached_repo_docs",
    ]
    assert registry.get_provider("langchain-docs-local") is replacement_primary


@pytest.mark.asyncio
async def test_registry_replacement_remains_executable_as_primary():
    """Replaced primary provider is executed first and satisfies retrieval without downstream calls."""
    registry = DocsSourceRegistry()
    replacement_primary = StubProvider(
        "langchain-docs-local",
        available=True,
        snippets=[
            DocSnippet(
                content="Fresh snippet from replaced primary",
                source="https://custom.langchain.docs",
                source_kind="langchain-docs-local",
                relevance_score=0.98,
            )
        ],
    )
    context7_provider = StubProvider("context7", available=True, snippets=[])
    cached_provider = StubProvider("cached_repo_docs", available=True, snippets=[])

    registry.register(replacement_primary)
    registry.register(context7_provider)
    registry.register(cached_provider)

    service = DocsRetrievalService(registry=registry)
    result = await service.aretrieve("StateGraph reducer query", k=5, mode="live")

    assert replacement_primary.call_count == 1
    assert context7_provider.call_count == 0
    assert cached_provider.call_count == 0
    assert result.used_sources == ["langchain-docs-local"]
    assert result.fallback_used is False
    assert len(result.snippets) == 1
    assert result.snippets[0].content == "Fresh snippet from replaced primary"


def test_registry_replacement_explicit_prepend_still_repositions():
    """Replacing an existing provider with prepend=True moves it to index 0."""
    registry = DocsSourceRegistry()
    assert registry.registered_source_ids() == [
        "langchain-docs-local",
        "context7",
        "cached_repo_docs",
    ]

    # Prepend replacement for index 1 ('context7')
    replacement_c7 = StubProvider("context7", available=True)
    registry.register(replacement_c7, prepend=True)

    assert registry.registered_source_ids() == [
        "context7",
        "langchain-docs-local",
        "cached_repo_docs",
    ]
    assert registry.list_providers()[0] is replacement_c7


def test_langchain_local_extracts_serialized_results_object():
    """Serialized JSON object containing 'results' collection is unpacked into DocSnippets without raw JSON."""
    provider = LangChainDocsLocalProvider(endpoint_url="http://mock-mcp/endpoint")
    payload = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "results": [
                                {
                                    "snippet": "Actual documentation content",
                                    "url": "https://example/docs",
                                    "title": "Example Docs",
                                    "score": 0.82,
                                }
                            ]
                        }
                    ),
                }
            ]
        }
    }

    snippets = provider._extract_snippets_from_payload(
        payload, fallback_url="http://fallback.url"
    )
    assert len(snippets) == 1
    s = snippets[0]
    assert s.content == "Actual documentation content"
    assert s.source == "https://example/docs"
    assert s.heading == "Example Docs"
    assert s.relevance_score == 0.82
    assert s.source_kind == "langchain-docs-local"
    assert "results" not in s.content
    assert "{" not in s.content


def test_langchain_local_extracts_serialized_object_with_zero_score():
    """Relevance score of 0.0 inside serialized object must survive unchanged without defaulting to 0.95."""
    provider = LangChainDocsLocalProvider(endpoint_url="http://mock-mcp/endpoint")
    payload = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "results": [
                                {
                                    "snippet": "Zero score documentation snippet",
                                    "url": "https://example/zero",
                                    "title": "Zero Score Title",
                                    "score": 0.0,
                                }
                            ]
                        }
                    ),
                }
            ]
        }
    }

    snippets = provider._extract_snippets_from_payload(
        payload, fallback_url="http://fallback.url"
    )
    assert len(snippets) == 1
    assert snippets[0].relevance_score == 0.0
    assert snippets[0].content == "Zero score documentation snippet"


def test_langchain_local_extracts_serialized_snippets_and_documents_collections():
    """Serialized JSON objects with 'snippets' or 'documents' collection keys are properly normalized."""
    provider = LangChainDocsLocalProvider(endpoint_url="http://mock-mcp/endpoint")

    # Test 'snippets' collection key
    payload_snippets = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "snippets": [
                                {
                                    "content": "Documentation text via snippets key",
                                    "source": "https://example/snippets",
                                    "heading": "Snippets Heading",
                                    "relevance_score": 0.88,
                                }
                            ]
                        }
                    ),
                }
            ]
        }
    }
    res_snippets = provider._extract_snippets_from_payload(
        payload_snippets, fallback_url="http://fallback.url"
    )
    assert len(res_snippets) == 1
    assert res_snippets[0].content == "Documentation text via snippets key"
    assert res_snippets[0].source == "https://example/snippets"
    assert res_snippets[0].heading == "Snippets Heading"
    assert res_snippets[0].relevance_score == 0.88

    # Test 'documents' collection key with page_content
    payload_docs = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "documents": [
                                {
                                    "page_content": "Documentation text via documents key",
                                    "url": "https://example/documents",
                                    "title": "Documents Title",
                                }
                            ]
                        }
                    ),
                }
            ]
        }
    }
    res_docs = provider._extract_snippets_from_payload(
        payload_docs, fallback_url="http://fallback.url"
    )
    assert len(res_docs) == 1
    assert res_docs[0].content == "Documentation text via documents key"
    assert res_docs[0].source == "https://example/documents"
    assert res_docs[0].heading == "Documents Title"
    assert res_docs[0].relevance_score == 0.95  # default when omitted


def test_langchain_local_extracts_serialized_single_doc_object():
    """Serialized JSON object containing a single doc item directly is properly normalized."""
    provider = LangChainDocsLocalProvider(endpoint_url="http://mock-mcp/endpoint")
    payload = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "snippet": "Direct single doc snippet text",
                            "url": "https://example/single",
                            "title": "Single Doc Title",
                            "score": 0.92,
                        }
                    ),
                }
            ]
        }
    }

    snippets = provider._extract_snippets_from_payload(
        payload, fallback_url="http://fallback.url"
    )
    assert len(snippets) == 1
    assert snippets[0].content == "Direct single doc snippet text"
    assert snippets[0].source == "https://example/single"
    assert snippets[0].heading == "Single Doc Title"
    assert snippets[0].relevance_score == 0.92


@pytest.mark.asyncio
async def test_langchain_local_serialized_object_provider_integration(monkeypatch):
    """End-to-end provider aretrieve() succeeds and normalizes serialized object payload from call_mcp_tool."""
    import langgraph_system_generator.rag.providers.langchain_local as local_mod

    raw_json_results = json.dumps(
        {
            "results": [
                {
                    "snippet": "LangGraph StateGraph workflow coordination guide",
                    "url": "https://docs.langchain.com/langgraph/guide",
                    "title": "StateGraph Guide",
                    "score": 0.91,
                }
            ]
        }
    )

    async def mock_call_mcp_tool(*args, **kwargs):
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": raw_json_results,
                    }
                ]
            }
        }

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(local_mod, "call_mcp_tool", mock_call_mcp_tool)

    provider = LangChainDocsLocalProvider(endpoint_url="http://test.mcp/endpoint")
    result = await provider.aretrieve("StateGraph guide", k=5, mode="live")

    assert result.status == DocsSourceStatus.SUCCESS
    assert len(result.snippets) == 1
    assert (
        result.snippets[0].content == "LangGraph StateGraph workflow coordination guide"
    )
    assert result.snippets[0].source == "https://docs.langchain.com/langgraph/guide"
    assert result.snippets[0].heading == "StateGraph Guide"
    assert result.snippets[0].relevance_score == 0.91
    assert "{" not in result.snippets[0].content


@pytest.mark.asyncio
async def test_langchain_local_rejects_protocol_envelope_json(monkeypatch):
    """Protocol-envelope JSON without recognized doc content must not be emitted as document snippet."""
    import langgraph_system_generator.rag.providers.langchain_local as local_mod

    envelope_json = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "notifications/initialized",
            "params": {},
        }
    )

    async def mock_call_mcp_tool(*args, **kwargs):
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": envelope_json,
                    }
                ]
            }
        }

    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(local_mod, "call_mcp_tool", mock_call_mcp_tool)

    provider = LangChainDocsLocalProvider(endpoint_url="http://test.mcp/endpoint")
    result = await provider.aretrieve("Check envelope", k=5, mode="live")

    assert result.status == DocsSourceStatus.EMPTY
    assert len(result.snippets) == 0


@pytest.mark.asyncio
async def test_unsafe_custom_provider_never_invoked_in_stub_mode():
    """A third-party/custom provider with stub_safe=False (or defaulting to False) must NEVER have is_available or aretrieve invoked in stub mode."""

    class CanaryUnsafeCustomProvider(DocsSourceProvider):
        source_id = "custom-remote-api"
        stub_safe = False

        def is_available(self, mode: str = "live") -> bool:
            raise AssertionError(
                "is_available() must not be called on non-stub-safe provider in stub mode!"
            )

        async def aretrieve(
            self, query: str, k: int = 5, mode: str = "live"
        ) -> DocsProviderResult:
            raise AssertionError(
                "aretrieve() must not be called on non-stub-safe provider in stub mode!"
            )

    class CanaryDefaultCustomProvider(DocsSourceProvider):
        source_id = "custom-third-party-default"

        def is_available(self, mode: str = "live") -> bool:
            raise AssertionError(
                "is_available() must not be called on default provider in stub mode!"
            )

        async def aretrieve(
            self, query: str, k: int = 5, mode: str = "live"
        ) -> DocsProviderResult:
            raise AssertionError(
                "aretrieve() must not be called on default provider in stub mode!"
            )

    cached_snippet = DocSnippet(
        content="Deterministic fallback snippet",
        source="cached:local",
        source_kind="cached_repo_docs",
        relevance_score=0.9,
    )
    cached_provider = StubProvider(
        "cached_repo_docs", available=True, snippets=[cached_snippet]
    )

    service = DocsRetrievalService(
        precedence=[
            "custom-remote-api",
            "custom-third-party-default",
            "cached_repo_docs",
        ]
    )
    service.registry.register(CanaryUnsafeCustomProvider())
    service.registry.register(CanaryDefaultCustomProvider())
    service.registry.register(cached_provider)

    result = await service.aretrieve("test query", k=5, mode="stub")

    assert result.source_statuses["custom-remote-api"] == DocsSourceStatus.SKIPPED.value
    assert (
        result.source_statuses["custom-third-party-default"]
        == DocsSourceStatus.SKIPPED.value
    )
    assert "custom-remote-api" not in result.attempted_sources
    assert "custom-third-party-default" not in result.attempted_sources
    assert result.fallback_used is True
    assert result.used_sources == ["cached_repo_docs"]
    assert len(result.snippets) == 1
    assert result.snippets[0].content == "Deterministic fallback snippet"


@pytest.mark.asyncio
async def test_explicit_stub_safe_provider_may_execute_in_stub_mode():
    """A deterministic custom provider explicitly declaring stub_safe=True may execute during stub mode according to precedence."""

    class StubSafeLocalPlugin(DocsSourceProvider):
        source_id = "custom-offline-knowledge-base"
        stub_safe = True

        def __init__(self):
            self.available_called = False
            self.retrieve_called = False

        def is_available(self, mode: str = "live") -> bool:
            self.available_called = True
            return True

        async def aretrieve(
            self, query: str, k: int = 5, mode: str = "live"
        ) -> DocsProviderResult:
            self.retrieve_called = True
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.SUCCESS,
                snippets=[
                    DocSnippet(
                        content="Offline local plugin documentation snippet",
                        source="plugin:offline_kb",
                        source_kind=self.source_id,
                        relevance_score=0.95,
                    )
                ],
            )

    plugin = StubSafeLocalPlugin()
    cached_snippet = DocSnippet(
        content="Cached repo fallback snippet",
        source="cache:offline",
        source_kind="cached_repo_docs",
        relevance_score=0.7,
    )
    cached_provider = StubProvider(
        "cached_repo_docs", available=True, snippets=[cached_snippet]
    )

    service = DocsRetrievalService(
        precedence=["custom-offline-knowledge-base", "cached_repo_docs"]
    )
    service.registry.register(plugin)
    service.registry.register(cached_provider)

    result = await service.aretrieve("query", k=5, mode="stub")

    assert plugin.available_called is True
    assert plugin.retrieve_called is True
    assert result.source_statuses["custom-offline-knowledge-base"] == "success"
    assert result.used_sources == ["custom-offline-knowledge-base"]
    assert result.attempted_sources == ["custom-offline-knowledge-base"]
    assert result.fallback_used is False
    assert len(result.snippets) == 1
    assert result.snippets[0].source_kind == "custom-offline-knowledge-base"
    assert cached_provider.call_count == 0


@pytest.mark.asyncio
async def test_builtin_providers_stub_safe_invariants_and_isolation():
    """Verify built-in provider stub_safe attributes and guarantee live providers are never invoked in stub mode."""
    assert DocsSourceProvider.stub_safe is False
    assert LangChainDocsLocalProvider.stub_safe is False
    assert Context7DocsProvider.stub_safe is False
    assert CachedVectorDocsProvider.stub_safe is True

    local_provider = LangChainDocsLocalProvider(
        endpoint_url="http://127.0.0.1:9999/unreachable"
    )
    context7_provider = Context7DocsProvider(
        api_key="sk-test-key",
        endpoint_url="http://127.0.0.1:9999/unreachable",
    )
    dummy_snippet = DocSnippet(
        content="Retrieved from process-local vector cache without network.",
        source="cache:vector",
        source_kind="cached_repo_docs",
        relevance_score=0.85,
    )
    cached_vector_provider = StubProvider(
        "cached_repo_docs",
        available=True,
        snippets=[dummy_snippet],
        stub_safe=True,
    )

    service = DocsRetrievalService(
        precedence=["langchain-docs-local", "context7", "cached_repo_docs"]
    )
    service.registry.register(local_provider)
    service.registry.register(context7_provider)
    service.registry.register(cached_vector_provider)

    result = await service.aretrieve("How to use StateGraph", k=3, mode="stub")

    assert result.source_statuses["langchain-docs-local"] == DocsSourceStatus.SKIPPED.value
    assert result.source_statuses["context7"] == DocsSourceStatus.SKIPPED.value
    assert result.source_statuses["cached_repo_docs"] == DocsSourceStatus.SUCCESS.value
    assert "langchain-docs-local" not in result.attempted_sources
    assert "context7" not in result.attempted_sources
    assert result.attempted_sources == ["cached_repo_docs"]
    assert result.used_sources == ["cached_repo_docs"]
    assert result.fallback_used is True
    assert len(result.snippets) == 1
    assert result.snippets[0].content == (
        "Retrieved from process-local vector cache without network."
    )


# ---------------------------------------------------------------------------
# Finding 2 tests: MCP transport HTTP-200 JSON request ID validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_transport_matching_request_id_succeeds(monkeypatch):
    """call_mcp_tool succeeds when HTTP-200 JSON response matches the active request_id."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import call_mcp_tool

    async def mock_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"content": []}},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    payload = await call_mcp_tool(
        endpoint_url="http://test.mcp/endpoint",
        tool_name="test_tool",
        request_id=1,
    )
    assert payload.get("id") == 1
    assert payload.get("result") == {"content": []}


@pytest.mark.asyncio
async def test_mcp_transport_mismatched_request_id_raises_parse_error(monkeypatch):
    """call_mcp_tool raises MCPTransportError(error_kind='parse') when HTTP-200 JSON has mismatched ID."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import (
        MCPTransportError,
        call_mcp_tool,
    )

    async def mock_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 999, "result": {"content": []}},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(MCPTransportError) as exc_info:
        await call_mcp_tool(
            endpoint_url="http://test.mcp/endpoint",
            tool_name="test_tool",
            request_id=1,
        )
    assert exc_info.value.error_kind == "parse"
    assert "Invalid JSON-RPC response for request_id '1'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mcp_transport_notification_envelope_raises_parse_error(monkeypatch):
    """call_mcp_tool raises MCPTransportError(error_kind='parse') when HTTP-200 is a notification-only envelope."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import (
        MCPTransportError,
        call_mcp_tool,
    )

    async def mock_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "method": "notifications/progress", "params": {}},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(MCPTransportError) as exc_info:
        await call_mcp_tool(
            endpoint_url="http://test.mcp/endpoint",
            tool_name="test_tool",
            request_id=1,
        )
    assert exc_info.value.error_kind == "parse"


# ---------------------------------------------------------------------------
# Finding 3 tests: Custom provider provenance preservation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_provider_untagged_snippets_acquire_provider_provenance():
    """Untagged custom provider snippets receive provider.source_id provenance and appear in used_sources."""

    class UntaggedCustomProvider(DocsSourceProvider):
        source_id = "custom-untagged-plugin"
        stub_safe = True

        def is_available(self, mode: str = "live") -> bool:
            return True

        async def aretrieve(
            self, query: str, k: int = 5, mode: str = "live"
        ) -> DocsProviderResult:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.SUCCESS,
                snippets=[
                    DocSnippet(
                        content="Plugin documentation content",
                        source="https://plugins.example.com/doc-1",
                        source_kind=None,
                        relevance_score=0.9,
                    )
                ],
            )

    provider = UntaggedCustomProvider()
    service = DocsRetrievalService(precedence=["custom-untagged-plugin"])
    service.registry.register(provider)

    result = await service.aretrieve("plugin query", k=5, mode="live")

    assert len(result.snippets) == 1
    assert result.snippets[0].source_kind == "custom-untagged-plugin"
    assert result.snippets[0].source == "https://plugins.example.com/doc-1"
    assert "custom-untagged-plugin" in result.used_sources
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_custom_provider_explicit_provenance_preserved():
    """Custom provider snippet with explicit source_kind remains untouched."""

    class ExplicitCustomProvider(DocsSourceProvider):
        source_id = "custom-explicit-plugin"
        stub_safe = True

        def is_available(self, mode: str = "live") -> bool:
            return True

        async def aretrieve(
            self, query: str, k: int = 5, mode: str = "live"
        ) -> DocsProviderResult:
            return DocsProviderResult(
                source_id=self.source_id,
                status=DocsSourceStatus.SUCCESS,
                snippets=[
                    DocSnippet(
                        content="Explicit provenance plugin content",
                        source="https://plugins.example.com/doc-2",
                        source_kind="explicit-upstream-origin",
                        relevance_score=0.88,
                    )
                ],
            )

    provider = ExplicitCustomProvider()
    service = DocsRetrievalService(precedence=["custom-explicit-plugin"])
    service.registry.register(provider)

    result = await service.aretrieve("explicit query", k=5, mode="live")

    assert len(result.snippets) == 1
    assert result.snippets[0].source_kind == "explicit-upstream-origin"
    assert result.snippets[0].source == "https://plugins.example.com/doc-2"


# ---------------------------------------------------------------------------
# Finding 4 tests: Context7 empty snippet prevention & fallback
# ---------------------------------------------------------------------------


def test_context7_nested_serialized_object_without_text_emits_no_snippets():
    """Context7 payload containing nested object without text/content emits zero snippets."""
    provider = Context7DocsProvider(api_key="test-key")
    payload = {
        "results": [
            {
                "url": "https://example.com/empty-result",
            }
        ]
    }
    snippets = provider._parse_snippets(
        payload, fallback_source="https://context7.example.com"
    )
    assert snippets == []


@pytest.mark.asyncio
async def test_context7_empty_snippets_returns_empty_and_allows_cached_fallback(
    monkeypatch,
):
    """Context7 returning only invalid/empty-content entries returns EMPTY and allows cached fallback."""
    import httpx

    # Mock Context7 returning resolve-library-id then query-docs with entries without text
    async def mock_post(self, url, headers=None, json=None, timeout=None):
        name = (json or {}).get("params", {}).get("name")
        req_id = (json or {}).get("id", 1)
        if name == "resolve-library-id":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"text": '{"libraries": [{"library_id": "lib-123"}]}'}
                        ]
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "results": [
                        {"url": "https://example.com/no-content-1"},
                        {"url": "https://example.com/no-content-2", "content": "   "},
                    ]
                },
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    monkeypatch.setattr(settings, "docs_live_sources_enabled", True)
    monkeypatch.setattr(settings, "context7_docs_enabled", True)

    context7_provider = Context7DocsProvider(
        api_key="sk-test",
        endpoint_url="http://test.context7/mcp",
    )
    direct_res = await context7_provider.aretrieve("test query", k=5, mode="live")
    assert direct_res.status == DocsSourceStatus.EMPTY
    assert len(direct_res.snippets) == 0

    # Test through DocsRetrievalService: precedence continues to cached_repo_docs
    cached_snippet = DocSnippet(
        content="Cached documentation content fallback",
        source="cache:repo",
        source_kind="cached_repo_docs",
        relevance_score=0.75,
    )
    cached_provider = StubProvider(
        "cached_repo_docs", available=True, snippets=[cached_snippet]
    )

    service = DocsRetrievalService(precedence=["context7", "cached_repo_docs"])
    service.registry.register(context7_provider)
    service.registry.register(cached_provider)

    result = await service.aretrieve("test query", k=5, mode="live")
    assert result.source_statuses["context7"] == DocsSourceStatus.EMPTY.value
    assert result.source_statuses["cached_repo_docs"] == DocsSourceStatus.SUCCESS.value
    assert result.fallback_used is True
    assert len(result.snippets) == 1
    assert result.snippets[0].content == "Cached documentation content fallback"


# ---------------------------------------------------------------------------
# Finding 5 tests: LangChain local content-only / text-only serialized documents
# ---------------------------------------------------------------------------


def test_langchain_local_extracts_serialized_content_only_doc():
    """LangChain local extracts a single-document object containing only 'content'."""
    provider = LangChainDocsLocalProvider(endpoint_url="http://test.mcp")
    payload = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": '{"content": "Content-only documentation"}',
                }
            ]
        }
    }
    snippets = provider._extract_snippets_from_payload(
        payload, fallback_url="https://docs.langchain.com/default"
    )
    assert len(snippets) == 1
    assert snippets[0].content == "Content-only documentation"
    assert snippets[0].source == "https://docs.langchain.com/default"
    assert snippets[0].source_kind == "langchain-docs-local"


def test_langchain_local_extracts_serialized_text_only_doc():
    """LangChain local extracts a single-document object containing only 'text'."""
    provider = LangChainDocsLocalProvider(endpoint_url="http://test.mcp")
    payload = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": '{"text": "Text-only documentation"}',
                }
            ]
        }
    }
    snippets = provider._extract_snippets_from_payload(
        payload, fallback_url="https://docs.langchain.com/default"
    )
    assert len(snippets) == 1
    assert snippets[0].content == "Text-only documentation"
    assert snippets[0].source == "https://docs.langchain.com/default"
    assert snippets[0].source_kind == "langchain-docs-local"


# ---------------------------------------------------------------------------
# Follow-up review tests: URL sanitization in MCP errors & Context7 protocol rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_transport_parse_error_sanitizes_endpoint_url(monkeypatch):
    """MCPTransportError redacts sensitive query parameters and credentials in endpoint URLs."""
    import httpx
    from langgraph_system_generator.rag.mcp_transport import (
        MCPTransportError,
        call_mcp_tool,
    )

    async def mock_post_invalid_json(*args, **kwargs):
        return httpx.Response(200, text="not valid json {{{")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_invalid_json)

    # Test query param secret redaction
    with pytest.raises(MCPTransportError) as exc_info:
        await call_mcp_tool(
            endpoint_url="https://api.example.com/mcp?api_key=secret_param_token_999",
            tool_name="test_tool",
            request_id=1,
        )
    assert exc_info.value.error_kind == "parse"
    assert "secret_param_token_999" not in str(exc_info.value)
    assert "api_key=[REDACTED]" in str(exc_info.value)

    # Test basic auth credential redaction
    with pytest.raises(MCPTransportError) as exc_info2:
        await call_mcp_tool(
            endpoint_url="https://admin:super_secret_pw@api.example.com/mcp",
            tool_name="test_tool",
            request_id=1,
        )
    assert exc_info2.value.error_kind == "parse"
    assert "super_secret_pw" not in str(exc_info2.value)
    assert "admin:[REDACTED]@" in str(exc_info2.value)


def test_context7_rejects_protocol_envelope_in_text_without_fallback_emission():
    """Context7 rejects protocol envelope nested inside text and does not emit raw JSON."""
    provider = Context7DocsProvider(api_key="test-key")
    payload = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": '{"jsonrpc": "2.0", "method": "notifications/message", "params": {}}',
                }
            ]
        }
    }
    snippets = provider._parse_snippets(
        payload, fallback_source="https://context7.example.com"
    )
    assert snippets == []


def test_context7_rejects_protocol_envelope_as_direct_string_item():
    """Context7 rejects protocol envelope passed as a string item and does not emit raw JSON."""
    provider = Context7DocsProvider(api_key="test-key")
    payload = {
        "result": [
            '{"jsonrpc": "2.0", "id": 1, "result": {"value": 123}}',
        ]
    }
    snippets = provider._parse_snippets(
        payload, fallback_source="https://context7.example.com"
    )
    assert snippets == []


def test_context7_extracts_single_doc_dict_from_serialized_text():
    """Context7 extracts single-document JSON from text field when valid document fields exist."""
    provider = Context7DocsProvider(api_key="test-key")
    payload = {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": '{"content": "Context7 extracted document", "title": "Context7 Title", "url": "https://docs.context7.ai/page"}',
                }
            ]
        }
    }
    snippets = provider._parse_snippets(
        payload, fallback_source="https://context7.example.com"
    )
    assert len(snippets) == 1
    assert snippets[0].content == "Context7 extracted document"
    assert snippets[0].heading == "Context7 Title"
    assert snippets[0].source == "https://docs.context7.ai/page"
    assert snippets[0].source_kind == "context7"


