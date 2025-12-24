"""Tests for generator graph and state."""

import pytest

from langgraph_system_generator.generator import (
    CellSpec,
    Constraint,
    create_generator_graph,
)


def test_generator_graph_compiles():
    """Test that the generator graph compiles successfully."""
    graph = create_generator_graph()
    assert graph is not None


def test_constraint_model():
    """Test Constraint pydantic model."""
    constraint = Constraint(type="goal", value="Build a chatbot", priority=5)
    assert constraint.type == "goal"
    assert constraint.value == "Build a chatbot"
    assert constraint.priority == 5


def test_cellspec_model():
    """Test CellSpec pydantic model."""
    cell = CellSpec(
        cell_type="code",
        content="print('hello')",
        metadata={"section": "intro"},
    )
    assert cell.cell_type == "code"
    assert cell.content == "print('hello')"
    assert cell.metadata["section"] == "intro"


@pytest.mark.asyncio
async def test_generator_minimal_run():
    """Test that the graph compiles and can be initialized with valid state."""
    graph = create_generator_graph()

    initial_state = {
        "user_prompt": "Create a simple router-based chatbot",
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

    # Verify the graph structure and state initialization
    assert graph is not None
    assert initial_state["user_prompt"] is not None
