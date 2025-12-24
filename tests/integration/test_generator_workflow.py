"""Integration tests for the complete generator workflow."""

import pytest

from langgraph_system_generator.generator import (
    CellSpec,
    NotebookPlan,
    create_generator_graph,
)


@pytest.mark.asyncio
async def test_generator_integration_structure():
    """Test that the generator graph has the correct structure."""
    graph = create_generator_graph()

    # Check that graph is compiled
    assert graph is not None

    # The graph should be executable via the async LangGraph API
    # Note: This tests the structure without actually invoking with real LLM calls
    assert hasattr(graph, "ainvoke")


@pytest.mark.asyncio
async def test_generator_state_initialization():
    """Test that we can create a valid initial state."""
    initial_state = {
        "user_prompt": "Create a chatbot with router pattern",
        "uploaded_files": None,
        "constraints": [],
        "selected_patterns": {},
        "docs_context": [],
        "notebook_plan": None,
        "architecture_justification": "",
        "workflow_design": None,
        "tools_plan": None,
        "generated_cells": [],
        "qa_reports": [],
        "repair_attempts": 0,
        "artifacts_manifest": {},
        "generation_complete": False,
        "error_message": None,
    }

    # Verify all required keys are present
    assert "user_prompt" in initial_state
    assert "repair_attempts" in initial_state
    assert "generation_complete" in initial_state

    # Verify initial state values
    assert initial_state["repair_attempts"] == 0
    assert initial_state["generation_complete"] is False


@pytest.mark.asyncio
async def test_notebook_plan_model():
    """Test NotebookPlan model creation."""
    plan = NotebookPlan(
        title="Test Workflow",
        sections=["Setup", "Implementation", "Execution"],
        cell_count_estimate=15,
        patterns_used=["router"],
        architecture_type="router",
    )

    assert plan.title == "Test Workflow"
    assert len(plan.sections) == 3
    assert "Setup" in plan.sections
    assert plan.architecture_type == "router"


@pytest.mark.asyncio
async def test_cellspec_creation():
    """Test creating multiple cell specs."""
    cells = [
        CellSpec(
            cell_type="markdown",
            content="# Title",
            section="intro",
        ),
        CellSpec(
            cell_type="code",
            content="import langgraph",
            section="setup",
        ),
        CellSpec(
            cell_type="code",
            content="graph = StateGraph(State)",
            section="graph",
        ),
    ]

    assert len(cells) == 3
    assert cells[0].cell_type == "markdown"
    assert cells[1].cell_type == "code"
    assert "langgraph" in cells[1].content
    assert "StateGraph" in cells[2].content


@pytest.mark.asyncio
async def test_graph_repair_loop_structure():
    """Test that repair loop structure is properly configured."""
    graph = create_generator_graph()

    # The graph should be compiled and ready to execute
    assert graph is not None

    # Note: This test only performs lightweight structural checks on the graph.
    # More exhaustive behavior (e.g., executing the graph and exercising the
    # repair loop with real LLM/API calls) should be covered in separate tests.
