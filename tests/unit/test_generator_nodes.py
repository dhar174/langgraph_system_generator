"""Tests for generator graph nodes and requirement analysis."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langgraph_system_generator.generator.agents.requirements_analyst import (
    RequirementsAnalyst,
)
from langgraph_system_generator.generator.nodes import (
    intake_node,
    notebook_assembly_node,
    rag_retrieval_node,
    tooling_plan_node,
)
from langgraph_system_generator.generator.state import (
    CellSpec,
    Constraint,
    DocSnippet,
    NotebookCompositionFeedback,
    NotebookCompositionResult,
    NotebookDependencyPlan,
    NotebookPlan,
    RequirementsAnalysis,
    RequirementsFeedback,
    ToolPlanningFeedback,
    ToolPlanningResult,
    ToolSpec,
)


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
    expected_tools = [
        ToolSpec(
            tool_id="web_search",
            name="search",
            category="search",
            purpose="Look up docs",
            configuration={"backend": "duckduckgo"},
            packages=["langchain-community"],
            provider_env_vars=[],
            status="ready",
            warnings=[],
        )
    ]
    expected_feedback = ToolPlanningFeedback(
        fallback_used=False,
        available_tool_ids=["web_search"],
    )

    # Patch ChatOpenAI used inside ToolchainEngineer.__init__ to avoid requiring OPENAI_API_KEY
    with patch(
        "langgraph_system_generator.generator.agents.toolchain_engineer.ChatOpenAI",
        return_value=MagicMock(),
    ):
        with patch(
            "langgraph_system_generator.generator.nodes.ToolchainEngineer.plan_tools",
            new=AsyncMock(
                return_value=ToolPlanningResult(
                    tools=expected_tools,
                    feedback=expected_feedback,
                )
            ),
        ) as mock_plan:
            result = await tooling_plan_node(
                {"workflow_design": workflow_design, "constraints": constraints}
            )

    assert result == {
        "tools_plan": [tool.model_dump() for tool in expected_tools],
        "tool_planning_feedback": expected_feedback,
    }
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
    expected_feedback = NotebookCompositionFeedback(
        fallback_used=True,
        warnings=["Notebook composition used deterministic fallback content."],
    )
    expected_dependency_plan = NotebookDependencyPlan(
        packages=["langgraph", "langchain-openai"]
    )

    tool_planning_feedback = ToolPlanningFeedback(
        fallback_used=True,
        fallback_reason="Heuristic tool fallback used.",
        available_tool_ids=["web_search"],
        warnings=["Heuristic tool fallback used."],
    )

    async def capture_compose(
        plan,
        design,
        tools,
        architecture,
        *,
        tool_planning_feedback=None,
    ):
        captured_args["plan"] = plan
        captured_args["design"] = design
        captured_args["tools"] = tools
        captured_args["architecture"] = architecture
        captured_args["tool_planning_feedback"] = tool_planning_feedback
        return NotebookCompositionResult(
            cells=expected_cells,
            feedback=expected_feedback,
            dependency_plan=expected_dependency_plan,
        )

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
                    "tool_planning_feedback": tool_planning_feedback,
                    "constraints": constraints,
                    "selected_patterns": {"primary": "router"},
                    "architecture_justification": "Fits the request.",
                }
            )

    assert result == {
        "generated_cells": expected_cells,
        "notebook_composition_feedback": expected_feedback,
        "notebook_dependency_plan": expected_dependency_plan,
    }
    assert captured_args["plan"] is notebook_plan
    assert captured_args["design"] == workflow_design
    assert captured_args["tools"] == tools_plan
    assert captured_args["architecture"] == {
        "architecture_type": "router",
        "justification": "Fits the request.",
    }
    assert captured_args["tool_planning_feedback"] == tool_planning_feedback


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
    expected_feedback = NotebookCompositionFeedback(fallback_used=False)
    expected_dependency_plan = NotebookDependencyPlan()

    async def capture_compose(plan, design, tools, architecture, **kwargs):
        captured_args["architecture"] = architecture
        captured_args["tool_planning_feedback"] = kwargs.get("tool_planning_feedback")
        return NotebookCompositionResult(
            cells=expected_cells,
            feedback=expected_feedback,
            dependency_plan=expected_dependency_plan,
        )

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

    assert result == {
        "generated_cells": expected_cells,
        "notebook_composition_feedback": expected_feedback,
        "notebook_dependency_plan": expected_dependency_plan,
    }
    assert captured_args["architecture"] == {
        "architecture_type": "router",  # Should default to "router"
        "justification": "Fits the request.",
    }
    assert captured_args["tool_planning_feedback"] is None


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
    expected_feedback = NotebookCompositionFeedback(fallback_used=False)
    expected_dependency_plan = NotebookDependencyPlan()

    async def capture_compose(plan, design, tools, architecture, **kwargs):
        captured_args["architecture"] = architecture
        captured_args["tool_planning_feedback"] = kwargs.get("tool_planning_feedback")
        return NotebookCompositionResult(
            cells=expected_cells,
            feedback=expected_feedback,
            dependency_plan=expected_dependency_plan,
        )

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

    assert result == {
        "generated_cells": expected_cells,
        "notebook_composition_feedback": expected_feedback,
        "notebook_dependency_plan": expected_dependency_plan,
    }
    assert captured_args["architecture"] == {
        "architecture_type": "router",  # Should default to "router"
        "justification": "Fits the request.",
    }
    assert captured_args["tool_planning_feedback"] is None
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
