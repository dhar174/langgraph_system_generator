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

    intro_content = "".join(cell.content for cell in cells if cell.section == "intro")
    assert plan.title in intro_content
    assert plan.architecture_type in intro_content
    for section in plan.sections:
        assert section in intro_content

    install_cell = next(
        cell
        for cell in cells
        if cell.section == "setup" and cell.cell_type == "code" and "pip install" in cell.content
    )
    assert "pypdf" in install_cell.content

    state_cell = next(
        cell for cell in cells if cell.section == "state" and cell.cell_type == "code"
    )
    assert state_marker in state_cell.content

    sections = {cell.section for cell in cells}
    assert {"intro", "setup", "graph", "execution"}.issubset(sections)
    assert any(cell.section == "graph" for cell in cells)
    assert any(cell.section == "execution" for cell in cells)
