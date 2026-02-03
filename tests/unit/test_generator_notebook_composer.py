"""Tests for generator NotebookComposer."""

from __future__ import annotations

import pytest

from langgraph_system_generator.generator.agents import notebook_composer as composer_module
from langgraph_system_generator.generator.state import NotebookPlan


class DummyLLM:
    """Simple LLM stub to avoid API initialization."""

    def __init__(self, *args, **kwargs) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "architecture_type, state_marker",
    [
        ("router", "route: str"),
        ("subagents", "next: str"),
    ],
)
async def test_compose_notebook_sections_and_packages(
    monkeypatch: pytest.MonkeyPatch,
    architecture_type: str,
    state_marker: str,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    monkeypatch.setattr(
        composer_module.NotebookComposer,
        "_generate_tool_implementation",
        lambda self, tool: "# tool stub",
    )

    composer = composer_module.NotebookComposer()

    plan = NotebookPlan(
        title="Test Workflow Notebook",
        sections=["Installation", "Workflow", "Execution"],
        patterns_used=[architecture_type],
        architecture_type=architecture_type,
    )

    if architecture_type == "router":
        nodes = [
            {"name": "router", "purpose": "Route requests"},
            {"name": "search", "purpose": "Search documents"},
        ]
    else:
        nodes = [
            {"name": "supervisor", "purpose": "Coordinate agents"},
            {"name": "researcher", "purpose": "Research documents"},
        ]

    workflow_design = {
        "architecture_type": architecture_type,
        "state_schema": {"user_input": "User question"},
        "nodes": nodes,
    }

    tools = [
        {
            "name": "File Reader",
            "purpose": "Read documents",
            "category": "file",
        }
    ]

    architecture = {
        "architecture_type": architecture_type,
        "justification": "Matches the workflow requirements.",
    }

    cells = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design=workflow_design,
        tools=tools,
        architecture=architecture,
    )

    # 1. Verify intro cells content and structure
    intro_cells = [cell for cell in cells if cell.section == "intro"]
    assert len(intro_cells) >= 2, "Expected at least 2 intro cells (title + overview)"
    
    # Check first cell contains title and is markdown
    title_cell = intro_cells[0]
    assert title_cell.cell_type == "markdown", "Title cell should be markdown"
    assert plan.title in title_cell.content, "Title should appear in first intro cell"
    assert plan.architecture_type in title_cell.content, "Architecture type should appear in title cell"
    
    # Check overview cell contains sections and is markdown
    overview_cell = intro_cells[1]
    assert overview_cell.cell_type == "markdown", "Overview cell should be markdown"
    for section in plan.sections:
        assert section in overview_cell.content, f"Section '{section}' should appear in overview cell"

    # 2. Verify install cells with better error handling
    install_cells = [
        cell
        for cell in cells
        if cell.section == "setup"
        and cell.cell_type == "code"
        and "pip install" in cell.content
    ]
    assert len(install_cells) > 0, "Expected at least one pip install cell in setup section"
    install_cell = install_cells[0]
    assert "pypdf" in install_cell.content, "Install cell should include pypdf package"

    # 3. Verify state cells with better error handling
    state_cells = [
        cell for cell in cells if cell.section == "state" and cell.cell_type == "code"
    ]
    assert len(state_cells) > 0, "Expected at least one state code cell"
    state_cell = state_cells[0]
    assert state_marker in state_cell.content, f"State cell should contain '{state_marker}' marker"

    # 4. Verify tool cells exist and contain stub content
    tool_cells = [cell for cell in cells if cell.section == "tools" and cell.cell_type == "code"]
    assert len(tool_cells) > 0, "Expected at least one tool code cell"
    tool_cell = tool_cells[0]
    assert "# tool stub" in tool_cell.content, "Tool cell should contain stubbed implementation"

    # 5. Verify graph cells contain expected LangGraph code
    graph_cells = [cell for cell in cells if cell.section == "graph" and cell.cell_type == "code"]
    assert len(graph_cells) > 0, "Expected at least one graph code cell"
    graph_cell = graph_cells[0]
    assert "StateGraph" in graph_cell.content, "Graph cell should contain StateGraph construction"
    assert "add_node" in graph_cell.content, "Graph cell should contain add_node calls"
    assert "compile" in graph_cell.content, "Graph cell should contain compile call"

    # 6. Verify execution cells contain expected execution code
    execution_cells = [cell for cell in cells if cell.section == "execution" and cell.cell_type == "code"]
    assert len(execution_cells) > 0, "Expected at least one execution code cell"
    execution_cell = execution_cells[0]
    assert "stream" in execution_cell.content or "invoke" in execution_cell.content, "Execution cell should contain graph execution code"

    # 7. Verify all expected sections exist
    sections = {cell.section for cell in cells}
    assert {"intro", "setup", "state", "tools", "graph", "execution"}.issubset(sections), "All expected sections should exist"

    # 8. Verify cell ordering - cells should appear in expected sequence
    section_order = [cell.section for cell in cells if cell.section]
    
    # Define expected section order
    expected_order = ["intro", "setup", "state", "tools", "nodes", "graph", "execution"]
    
    # Extract unique sections while preserving order
    unique_sections: list[str] = []
    for section in section_order:
        if section not in unique_sections:
            unique_sections.append(section)
    
    # Build position map for expected order
    expected_positions = {s: i for i, s in enumerate(expected_order)}
    
    # Fail fast if any unexpected sections are present
    unexpected_sections = [s for s in unique_sections if s not in expected_positions]
    assert not unexpected_sections, (
        f"Unexpected sections found: {unexpected_sections}. "
        f"Allowed sections (in order) are: {expected_order}"
    )
    
    # Verify sections appear in correct order by checking that each section's
    # expected position is greater than the previous section's expected position
    prev_expected_pos = -1
    for section in unique_sections:
        current_expected_pos = expected_positions[section]
        assert current_expected_pos > prev_expected_pos, (
            f"Section '{section}' appears out of order. Expected sections in order: {expected_order}"
        )
        prev_expected_pos = current_expected_pos
