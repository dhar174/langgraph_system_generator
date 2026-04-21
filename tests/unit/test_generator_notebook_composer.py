"""Tests for generator NotebookComposer."""

from __future__ import annotations

import ast

import pytest

from langgraph_system_generator.generator.agents import notebook_composer as composer_module
from langgraph_system_generator.generator.state import NotebookPlan
from langgraph_system_generator.utils.config import ModelConfig


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
        (
            "router",
            "route: str",
            ['"route": ""', '"results": {}', '"final_output": ""'],
        ),
        (
            "subagents",
            "next_agent: str",
            [
                '"next_agent": "supervisor"',
                '"instructions": ""',
                '"task_results": {}',
            ],
        ),
        (
            "critique_loop",
            "revision_count: int",
            ['"revision_count": 0', '"quality_score": 0.0', '"approved": False'],
        ),
        (
            "hybrid",
            "next_agent: str",
            [
                '"route": ""',
                '"next_agent": "supervisor"',
                '"task_results": {}',
            ],
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
    elif architecture_type == "hybrid":
        nodes = [
            {"name": "router", "purpose": "Route requests"},
            {"name": "specialist_1", "purpose": "Handle direct specialist work"},
            {"name": "supervisor", "purpose": "Coordinate worker team"},
            {"name": "researcher", "purpose": "Research documents"},
            {"name": "reviewer", "purpose": "Review worker output"},
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

    intro_cells = [cell for cell in cells if cell.section == "intro"]
    assert len(intro_cells) >= 2

    title_cell = intro_cells[0]
    assert title_cell.cell_type == "markdown"
    assert plan.title in title_cell.content
    assert plan.architecture_type in title_cell.content

    overview_cell = intro_cells[1]
    assert overview_cell.cell_type == "markdown"
    for section in plan.sections:
        assert section in overview_cell.content

    install_cells = [
        cell
        for cell in cells
        if cell.section == "setup"
        and cell.cell_type == "code"
        and "pip install" in cell.content
    ]
    assert install_cells
    assert "pypdf" in install_cells[0].content

    state_cells = [
        cell for cell in cells if cell.section == "state" and cell.cell_type == "code"
    ]
    assert state_cells
    assert state_marker in state_cells[0].content

    tool_cells = [
        cell for cell in cells if cell.section == "tools" and cell.cell_type == "code"
    ]
    assert tool_cells
    assert "def File_Reader" in tool_cells[0].content
    assert "Path(" in tool_cells[0].content
    assert "pass" not in tool_cells[0].content
    assert "TODO" not in tool_cells[0].content

    graph_cells = [
        cell for cell in cells if cell.section == "graph" and cell.cell_type == "code"
    ]
    assert graph_cells
    assert "StateGraph" in graph_cells[0].content
    assert "add_node" in graph_cells[0].content
    assert "compile" in graph_cells[0].content

    execution_cells = [
        cell
        for cell in cells
        if cell.section == "execution" and cell.cell_type == "code"
    ]
    assert execution_cells
    execution_cell = execution_cells[0]
    assert "stream" in execution_cell.content or "invoke" in execution_cell.content
    for marker in expected_execution_markers:
        assert marker in execution_cell.content

    if architecture_type == "hybrid":
        assert "route: str" in state_cells[0].content
        assert 'workflow.add_node("router", router_node)' in graph_cells[0].content
        assert 'workflow.add_node("supervisor", supervisor_node)' in graph_cells[0].content
        assert 'workflow.add_edge("specialist_1", "finish")' in graph_cells[0].content
        node_source = "\n\n".join(cell.content for cell in cells if cell.section == "nodes")
        assert "def router_node" in node_source
        assert "def supervisor_node" in node_source
        assert "def reviewer_node" in node_source

    sections = {cell.section for cell in cells}
    assert {"intro", "setup", "state", "tools", "graph", "execution"}.issubset(
        sections
    )

    section_order = [cell.section for cell in cells if cell.section]
    expected_order = ["intro", "setup", "state", "tools", "nodes", "graph", "execution"]
    unique_sections: list[str] = []
    for section in section_order:
        if section not in unique_sections:
            unique_sections.append(section)

    expected_positions = {s: i for i, s in enumerate(expected_order)}
    unexpected_sections = [s for s in unique_sections if s not in expected_positions]
    assert not unexpected_sections

    prev_expected_pos = -1
    for section in unique_sections:
        current_expected_pos = expected_positions[section]
        assert current_expected_pos > prev_expected_pos
        prev_expected_pos = current_expected_pos


@pytest.mark.asyncio
async def test_compose_notebook_hybrid_sparse_nodes_keep_defaults_aligned(
    monkeypatch: pytest.MonkeyPatch,
):
    """Sparse hybrid designs should emit matching fallback nodes and graph wiring."""

    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    plan = NotebookPlan(
        title="Sparse Hybrid",
        sections=["Setup", "Workflow", "Execution"],
        patterns_used=["hybrid"],
        architecture_type="hybrid",
    )
    workflow_design = {
        "architecture_type": "hybrid",
        "state_schema": {},
        "nodes": [
            {"name": "router", "purpose": "Route requests"},
            {"name": "supervisor", "purpose": "Coordinate workers"},
        ],
    }

    cells = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design=workflow_design,
        tools=[],
        architecture={"architecture_type": "hybrid", "justification": "Fallback hybrid."},
    )

    node_source = "\n\n".join(cell.content for cell in cells if cell.section == "nodes")
    graph_code = next(
        cell.content
        for cell in cells
        if cell.section == "graph" and cell.cell_type == "code"
    )

    assert "def specialist_1_node" in node_source
    assert "def researcher_node" in node_source
    assert "def reviewer_node" in node_source
    assert 'workflow.add_node("specialist_1", specialist_1_node)' in graph_code
    assert 'workflow.add_node("researcher", researcher_node)' in graph_code
    assert 'workflow.add_node("reviewer", reviewer_node)' in graph_code
    assert 'workflow.add_edge("specialist_1", "finish")' in graph_code


@pytest.mark.asyncio
async def test_compose_notebook_hybrid_sanitizes_worker_and_specialist_graph_ids(
    monkeypatch: pytest.MonkeyPatch,
):
    """Hybrid graph wiring should use sanitized node ids for direct and worker paths."""

    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    plan = NotebookPlan(
        title="Hybrid Sanitization",
        sections=["Setup", "Workflow", "Execution"],
        patterns_used=["hybrid"],
        architecture_type="hybrid",
    )
    workflow_design = {
        "architecture_type": "hybrid",
        "state_schema": {},
        "nodes": [
            {"name": "router", "purpose": "Route requests"},
            {"name": "supervisor", "purpose": "Coordinate workers"},
            {"name": "fact checker", "purpose": "Handle direct fact checking"},
            {"name": "review lead", "purpose": "Review worker output"},
            {"name": "research analyst", "purpose": "Gather supporting facts"},
        ],
    }

    cells = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design=workflow_design,
        tools=[],
        architecture={"architecture_type": "hybrid", "justification": "Hybrid sanitization."},
    )

    node_source = "\n\n".join(cell.content for cell in cells if cell.section == "nodes")
    graph_code = next(
        cell.content
        for cell in cells
        if cell.section == "graph" and cell.cell_type == "code"
    )

    assert "def fact_checker_node" in node_source
    assert "def review_lead_node" in node_source
    assert "def research_analyst_node" in node_source
    assert 'workflow.add_node("fact_checker", fact_checker_node)' in graph_code
    assert 'workflow.add_node("review_lead", review_lead_node)' in graph_code
    assert 'workflow.add_node("research_analyst", research_analyst_node)' in graph_code
    assert '"fact checker": "fact_checker"' in graph_code


def test_generate_node_implementation_falls_back_to_meaningful_state_updates(
    monkeypatch: pytest.MonkeyPatch,
):
    """Custom architectures should fall back to runnable node code."""
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    node_code = composer._generate_node_implementation(
        {"name": "enrich", "purpose": "Enrich the current workflow results"},
        {
            "architecture_type": "custom",
            "state_schema": {"results": "Collected outputs"},
            "nodes": [
                {"name": "enrich", "purpose": "Enrich the current workflow results"}
            ],
        },
    )

    assert "def enrich_node" in node_code
    assert 'updates["messages"]' in node_code
    assert 'updates["results"]' in node_code
    assert "return updates" in node_code
    assert "return state" not in node_code
    assert "pass" not in node_code
    assert "TODO" not in node_code


def test_tool_fallback_sanitizes_identifier_and_compiles(
    monkeypatch: pytest.MonkeyPatch,
):
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


def test_node_fallback_sanitizes_identifier_and_compiles(
    monkeypatch: pytest.MonkeyPatch,
):
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
            "entry_point": "start node",
            "nodes": [
                {"name": "start node"},
                {"name": "9 result-node"},
            ],
            "edges": [{"from": "start node", "to": "9 result-node"}],
        }
    )

    assert 'workflow.add_node("start node", start_node_node)' in graph_code
    assert 'workflow.add_node("9 result-node", _9_result_node_node)' in graph_code
    compile(graph_code, "<graph_fallback>", "exec")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "architecture_type",
    ["router", "subagents", "critique_loop", "autoagent", "hybrid"],
)
async def test_pattern_nodes_use_request_scoped_model_config(
    monkeypatch: pytest.MonkeyPatch,
    architecture_type: str,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer(
        model_config=ModelConfig(
            model="gpt-5.2",
            temperature=0.3,
            api_base="https://example.test/v1",
            max_tokens=2048,
        )
    )

    plan = NotebookPlan(
        title="Configured Workflow Notebook",
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
    elif architecture_type == "autoagent":
        nodes = [{"name": "planner", "purpose": "Plan the work"}]
    elif architecture_type == "hybrid":
        nodes = [
            {"name": "router", "purpose": "Route requests"},
            {"name": "specialist_1", "purpose": "Handle direct specialist work"},
            {"name": "supervisor", "purpose": "Coordinate worker team"},
            {"name": "researcher", "purpose": "Research documents"},
            {"name": "reviewer", "purpose": "Review worker output"},
        ]
    else:
        nodes = [
            {"name": "generate", "purpose": "Generate an initial draft"},
            {"name": "critique", "purpose": "Critique the current draft"},
            {"name": "revise", "purpose": "Revise the draft using feedback"},
        ]

    cells = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design={
            "architecture_type": architecture_type,
            "state_schema": {"user_input": "User question"},
            "nodes": nodes,
        },
        tools=[],
        architecture={
            "architecture_type": architecture_type,
            "justification": "Matches the workflow requirements.",
        },
    )

    node_cells = [cell for cell in cells if cell.section == "nodes"]
    assert node_cells
    assert any(
        "ChatOpenAI(model='gpt-5.2', temperature=0.3, base_url='https://example.test/v1', max_tokens=2048)"
        in cell.content
        for cell in node_cells
    )

    setup_code_cells = [
        cell
        for cell in cells
        if cell.section == "setup" and cell.cell_type == "code"
    ]
    assert any('MODEL = "gpt-5.2"' in cell.content for cell in setup_code_cells)
    assert any("TEMPERATURE = 0.3" in cell.content for cell in setup_code_cells)
    assert any('API_BASE = "https://example.test/v1"' in cell.content for cell in setup_code_cells)
    assert any("MAX_TOKENS = 2048" in cell.content for cell in setup_code_cells)
