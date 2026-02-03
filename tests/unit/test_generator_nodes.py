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
from langgraph_system_generator.generator.state import CellSpec, Constraint, NotebookPlan


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
async def test_tooling_plan_node_returns_tools_plan():
    constraints = [Constraint(type="goal", value="Build agents", priority=5)]
    workflow_design = {"nodes": [{"name": "agent", "purpose": "coordinate"}]}
    expected_tools = [{"name": "search", "category": "search"}]

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
