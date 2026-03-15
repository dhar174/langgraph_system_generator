"""Tests for generator NotebookComposer."""

from __future__ import annotations

import ast

import pytest

from langgraph_system_generator.generator.agents import notebook_composer as composer_module
from langgraph_system_generator.generator.state import NotebookPlan


class DummyLLM:
    """Simple LLM stub to avoid API initialization."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def invoke(self, *args, **kwargs):
        """Minimal invoke stub returning an object with a `content` attribute."""
        class Response:
            def __init__(self, content: str) -> None:
                self.content = content

        return Response("")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "architecture_type, state_marker, expected_execution_markers",
    [
        ("router", "route: str", ['"route": ""', '"results": {}', '"final_output": ""']),
        (
            "subagents",
            "next: str",
            ['"next": "supervisor"', '"instructions": ""', '"task_results": {}'],
        ),
        (
            "critique_loop",
            "revision_count: int",
            ['"revision_count": 0', '"quality_score": 0.0', '"approved": False'],
        ),
    ],
)
async def test_compose_notebook_sections_and_packages(
    monkeypatch: pytest.MonkeyPatch,
    architecture_type: str,
    state_marker: str,
    expected_execution_markers: list[str],
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)

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
    elif architecture_type == "subagents":
        nodes = [
            {"name": "supervisor", "purpose": "Coordinate agents"},
            {"name": "researcher", "purpose": "Research documents"},
        ]
    else:
        nodes = [
            {"name": "generate", "purpose": "Generate an initial draft"},
            {"name": "critique", "purpose": "Critique the current draft"},
            {"name": "revise", "purpose": "Revise the draft using feedback"},
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

    # 4. Verify tool cells exist and contain deterministic fallback content
    tool_cells = [cell for cell in cells if cell.section == "tools" and cell.cell_type == "code"]
    assert len(tool_cells) > 0, "Expected at least one tool code cell"
    tool_cell = tool_cells[0]
    assert "def file_reader" in tool_cell.content, "Tool cell should contain a real fallback implementation"
    assert "Path(" in tool_cell.content, "File tool fallback should use pathlib-based logic"
    assert "pass" not in tool_cell.content, "Tool fallback should not use pass"
    assert "TODO" not in tool_cell.content, "Tool fallback should not contain TODO placeholders"

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
    for marker in expected_execution_markers:
        assert marker in execution_cell.content, f"Execution cell should contain architecture-aware marker {marker!r}"

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


def test_generate_node_implementation_falls_back_to_meaningful_state_updates(
    monkeypatch: pytest.MonkeyPatch,
):
    """Custom architectures should fall back to runnable node code, not bare return-state stubs."""
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    node_code = composer._generate_node_implementation(
        {"name": "enrich", "purpose": "Enrich the current workflow results"},
        {
            "architecture_type": "custom",
            "state_schema": {"results": "Collected outputs"},
            "nodes": [{"name": "enrich", "purpose": "Enrich the current workflow results"}],
        },
    )

    assert "def enrich_node" in node_code
    assert 'updates["messages"]' in node_code
    assert 'updates["results"]' in node_code
    assert "return updates" in node_code
    assert "return state" not in node_code
    assert "pass" not in node_code
    assert "TODO" not in node_code
def test_tool_fallback_sanitizes_identifier_and_compiles(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    fallback_code = composer._generate_tool_fallback(
        {
            "name": '9 bad tool";\nprint("oops")',
            "purpose": 'Line 1\n"""\nprint("owned")',
            "category": 'api"\n# injected',
        }
    )

    assert 'def _9_bad_tool_print_oops' in fallback_code
    assert '# Tool: 9 bad tool"; print("oops")' in fallback_code
    assert '9 bad tool";\nprint("oops")' not in fallback_code
    assert '"category": "api\\" # injected"' in fallback_code
    assert fallback_code.splitlines()[0] == '# Tool: 9 bad tool"; print("oops")'
    compile(fallback_code, "<tool_fallback>", "exec")
    parsed = ast.parse(fallback_code)
    assert len(parsed.body) == 1
    assert isinstance(parsed.body[0], ast.FunctionDef)


def test_node_fallback_sanitizes_identifier_and_compiles(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    fallback_code = composer._generate_node_fallback(
        {
            "name": '9 node name";\nraise SystemExit',
            "purpose": 'Node purpose\n"""\nraise RuntimeError("boom")',
        },
        {},
    )

    assert 'def _9_node_name_raise_SystemExit_node' in fallback_code
    assert '9 node name";\nraise SystemExit' not in fallback_code
    assert '\\"\\"\\"' in fallback_code
    compile(fallback_code, "<node_fallback>", "exec")
    parsed = ast.parse(fallback_code)
    assert len(parsed.body) == 1
    assert isinstance(parsed.body[0], ast.FunctionDef)


def test_graph_fallback_uses_sanitized_function_references(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    graph_code = composer._generate_graph_fallback(
        {
            "entry_point": 'start node',
            "nodes": [
                {"name": 'start node'},
                {"name": '9 result-node'},
            ],
            "edges": [{"from": 'start node', "to": '9 result-node'}],
        }
    )

    assert 'workflow.add_node("start node", start_node_node)' in graph_code
    assert 'workflow.add_node("9 result-node", _9_result_node_node)' in graph_code
    compile(graph_code, "<graph_fallback>", "exec")
