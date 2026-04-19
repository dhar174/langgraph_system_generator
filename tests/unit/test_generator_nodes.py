"""Tests for generator graph nodes and requirement analysis."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langgraph_system_generator.generator.agents.requirements_analyst import (
    RequirementsAnalyst,
)
from langgraph_system_generator.generator.nodes import (
    intake_node,
    notebook_assembly_node,
    tooling_plan_node,
)
from langgraph_system_generator.generator.state import (
    CellSpec,
    Constraint,
    NotebookPlan,
    RequirementsAnalysis,
    RequirementsFeedback,
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
            new=AsyncMock(
                return_value=RequirementsAnalysis(
                    constraints=constraints,
                    feedback=RequirementsFeedback(
                        fallback_used=False,
                        available_constraint_types=["goal", "tone"],
                    ),
                )
            ),
        ) as mock_analyze:
            result = await intake_node({"user_prompt": "Build a router workflow"})

    assert result["constraints"] == constraints
    assert result["requirements_feedback"].fallback_used is False
    assert result["requirements_feedback"].available_constraint_types == ["goal", "tone"]
    mock_analyze.assert_awaited_once_with("Build a router workflow")


@pytest.mark.asyncio
async def test_tooling_plan_node_returns_tools_plan():
    constraints = [Constraint(type="goal", value="Build agents", priority=5)]
    workflow_design = {"nodes": [{"name": "agent", "purpose": "coordinate"}]}
    expected_tools = [{"name": "search", "category": "search"}]
    expected_tools = [{"name": "search", "category": "search"}]

    # Patch ChatOpenAI used inside ToolchainEngineer.__init__ to avoid requiring OPENAI_API_KEY
    with patch(
        "langgraph_system_generator.generator.agents.toolchain_engineer.ChatOpenAI",
        return_value=MagicMock(),
    ):
        with patch(
            "langgraph_system_generator.generator.nodes.ToolchainEngineer.plan_tools",
            new=AsyncMock(return_value=expected_tools),
        ) as mock_plan:
            result = await tooling_plan_node(
                {"workflow_design": workflow_design, "constraints": constraints}
            )

    assert result == {"tools_plan": expected_tools}
    mock_plan.assert_awaited_once_with(workflow_design, constraints)


@pytest.mark.asyncio
async def test_notebook_assembly_node_passes_architecture_and_plans():
    notebook_plan = NotebookPlan(
        title="Test Notebook",
        sections=["Setup"],
        cell_count_estimate=1,
        patterns_used=["router"],
        architecture_type="router",
    )
    workflow_design = {"nodes": [{"name": "node", "purpose": "do work"}]}
    tools_plan = [{"name": "search", "category": "search"}]
    constraints = [Constraint(type="goal", value="Build agents", priority=5)]
    captured_args = {}
    expected_cells = [
        CellSpec(cell_type="markdown", content="# Intro", metadata={}, section="Setup")
    ]

    async def capture_compose(plan, design, tools, architecture):
        captured_args["plan"] = plan
        captured_args["design"] = design
        captured_args["tools"] = tools
        captured_args["architecture"] = architecture
        return expected_cells

    with patch(
        "langgraph_system_generator.generator.agents.notebook_composer.ChatOpenAI",
        return_value=MagicMock(),
    ):
        with patch(
            "langgraph_system_generator.generator.nodes.NotebookComposer.compose_notebook",
            new=AsyncMock(side_effect=capture_compose),
        ):
            result = await notebook_assembly_node(
                {
                    "notebook_plan": notebook_plan,
                    "workflow_design": workflow_design,
                    "tools_plan": tools_plan,
                    "constraints": constraints,
                    "selected_patterns": {"primary": "router"},
                    "architecture_justification": "Fits the request.",
                }
            )

    assert result == {"generated_cells": expected_cells}
    assert captured_args["plan"] is notebook_plan
    assert captured_args["design"] == workflow_design
    assert captured_args["tools"] == tools_plan
    assert captured_args["architecture"] == {
        "architecture_type": "router",
        "justification": "Fits the request.",
    }


@pytest.mark.asyncio
async def test_notebook_assembly_node_fallback_when_primary_missing():
    """Test that notebook_assembly_node uses 'router' when 'primary' key is missing from selected_patterns."""
    notebook_plan = NotebookPlan(
        title="Test Notebook",
        sections=["Setup"],
        cell_count_estimate=1,
        patterns_used=["router"],
        architecture_type="router",
    )
    workflow_design = {"nodes": [{"name": "node", "purpose": "do work"}]}
    tools_plan = [{"name": "search", "category": "search"}]
    constraints = [Constraint(type="goal", value="Build agents", priority=5)]
    captured_args = {}
    expected_cells = [
        CellSpec(cell_type="markdown", content="# Intro", metadata={}, section="Setup")
    ]

    async def capture_compose(plan, design, tools, architecture):
        captured_args["architecture"] = architecture
        return expected_cells

    with patch(
        "langgraph_system_generator.generator.agents.notebook_composer.ChatOpenAI",
        return_value=MagicMock(),
    ):
        with patch(
            "langgraph_system_generator.generator.nodes.NotebookComposer.compose_notebook",
            new=AsyncMock(side_effect=capture_compose),
        ):
            result = await notebook_assembly_node(
                {
                    "notebook_plan": notebook_plan,
                    "workflow_design": workflow_design,
                    "tools_plan": tools_plan,
                    "constraints": constraints,
                    "selected_patterns": {},  # Empty dict, no "primary" key
                    "architecture_justification": "Fits the request.",
                }
            )

    assert result == {"generated_cells": expected_cells}
    assert captured_args["architecture"] == {
        "architecture_type": "router",  # Should default to "router"
        "justification": "Fits the request.",
    }


@pytest.mark.asyncio
async def test_notebook_assembly_node_fallback_when_selected_patterns_missing():
    """Test that notebook_assembly_node uses 'router' when selected_patterns is missing from state."""
    notebook_plan = NotebookPlan(
        title="Test Notebook",
        sections=["Setup"],
        cell_count_estimate=1,
        patterns_used=["router"],
        architecture_type="router",
    )
    workflow_design = {"nodes": [{"name": "node", "purpose": "do work"}]}
    tools_plan = [{"name": "search", "category": "search"}]
    constraints = [Constraint(type="goal", value="Build agents", priority=5)]
    captured_args = {}
    expected_cells = [
        CellSpec(cell_type="markdown", content="# Intro", metadata={}, section="Setup")
    ]

    async def capture_compose(plan, design, tools, architecture):
        captured_args["architecture"] = architecture
        return expected_cells

    with patch(
        "langgraph_system_generator.generator.agents.notebook_composer.ChatOpenAI",
        return_value=MagicMock(),
    ):
        with patch(
            "langgraph_system_generator.generator.nodes.NotebookComposer.compose_notebook",
            new=AsyncMock(side_effect=capture_compose),
        ):
            result = await notebook_assembly_node(
                {
                    "notebook_plan": notebook_plan,
                    "workflow_design": workflow_design,
                    "tools_plan": tools_plan,
                    "constraints": constraints,
                    # "selected_patterns" key is completely missing
                    "architecture_justification": "Fits the request.",
                }
            )

    assert result == {"generated_cells": expected_cells}
    assert captured_args["architecture"] == {
        "architecture_type": "router",  # Should default to "router"
        "justification": "Fits the request.",
    }
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
