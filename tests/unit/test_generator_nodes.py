"""Tests for generator graph nodes and requirement analysis."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langgraph_system_generator.generator.agents.requirements_analyst import (
    RequirementsAnalyst,
)
from langgraph_system_generator.generator.nodes import intake_node, rag_retrieval_node
from langgraph_system_generator.generator.state import Constraint, DocSnippet


@pytest.mark.asyncio
async def test_intake_node_returns_constraints():
    constraints = [
        Constraint(type="goal", value="Build a router workflow", priority=5),
        Constraint(type="tone", value="technical", priority=3),
    ]

    with patch(
        "langgraph_system_generator.generator.agents.requirements_analyst.ChatOpenAI",
        return_value=MagicMock(),
    ):
        with patch.object(
            RequirementsAnalyst,
            "analyze",
            new=AsyncMock(return_value=constraints),
        ) as mock_analyze:
            result = await intake_node({"user_prompt": "Build a router workflow"})

    assert result == {"constraints": constraints}
    mock_analyze.assert_awaited_once_with("Build a router workflow")


@pytest.mark.asyncio
async def test_requirements_analyst_fallback_truncates_prompt_on_bad_json():
    long_prompt = "Build a workflow " + ("with a long prompt " * 15)
    assert len(long_prompt) > 200

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock()
    mock_llm.ainvoke.return_value.content = "not-json"

    with patch(
        "langgraph_system_generator.generator.agents.requirements_analyst.ChatOpenAI",
        return_value=mock_llm,
    ):
        analyst = RequirementsAnalyst(model="test-model")
        constraints = await analyst.analyze(long_prompt)

    assert len(constraints) == 1
    constraint = constraints[0]
    assert constraint.type == "goal"
    assert constraint.priority == 5
    assert constraint.value == long_prompt[:200]
    assert len(constraint.value) == 200


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["vector_store", "retrieve"])
async def test_rag_retrieval_node_returns_empty_on_failure(
    monkeypatch, failure_mode
):
    if failure_mode == "vector_store":
        class BoomManager:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            "langgraph_system_generator.generator.nodes.VectorStoreManager",
            BoomManager,
        )
    else:
        class DummyManager:
            def __init__(self, *args, **kwargs):
                pass

        class BoomRetriever:
            def __init__(self, manager):
                pass

            def retrieve(self, *args, **kwargs):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            "langgraph_system_generator.generator.nodes.VectorStoreManager",
            DummyManager,
        )
        monkeypatch.setattr(
            "langgraph_system_generator.generator.nodes.DocsRetriever",
            BoomRetriever,
        )

    result = await rag_retrieval_node({"user_prompt": "Find docs"})

    assert result == {"docs_context": []}


@pytest.mark.asyncio
async def test_rag_retrieval_node_maps_snippets(monkeypatch):
    class DummyManager:
        def __init__(self, *args, **kwargs):
            pass

    class DummyRetriever:
        def __init__(self, manager):
            pass

        def retrieve(self, prompt, k=10):
            return [
                {
                    "content": "Content A",
                    "source": "source-a",
                    "relevance_score": 0.9,
                    "heading": "Heading A",
                },
                {
                    "content": "Content B",
                    "source": "source-b",
                    "relevance_score": 0.5,
                },
            ]

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.VectorStoreManager",
        DummyManager,
    )
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.DocsRetriever",
        DummyRetriever,
    )

    result = await rag_retrieval_node({"user_prompt": "Find docs"})

    assert result["docs_context"] == [
        DocSnippet(
            content="Content A",
            source="source-a",
            relevance_score=0.9,
            heading="Heading A",
        ),
        DocSnippet(
            content="Content B",
            source="source-b",
            relevance_score=0.5,
            heading=None,
        ),
    ]
