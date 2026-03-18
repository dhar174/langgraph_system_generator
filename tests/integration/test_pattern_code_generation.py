"""Integration tests for pattern-based code generation in notebooks."""

from __future__ import annotations

import os
from pathlib import Path

import nbformat
import pytest

from langgraph_system_generator.cli import generate_artifacts


@pytest.mark.asyncio
async def test_router_pattern_notebook_generation(tmp_path: Path):
    """Test notebook generation with router pattern."""

    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    os.environ['BASE_OUTPUT_DIR'] = str(tmp_path.resolve())

    # Generate notebook for router pattern
    artifacts = await generate_artifacts(
        prompt="Create a multi-agent system with a router that can handle search, analysis, and summarization tasks",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    # Load the generated notebook
    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    assert notebook_path.exists(), "Notebook not generated"

    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Extract all code cells
    code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]
    all_code = "\n\n".join([cell.source for cell in code_cells])

    # Verify pattern-specific code generation
    assert "class WorkflowState(MessagesState):" in all_code, "State class not found"
    assert "route:" in all_code, "Router state field missing"
    assert (
        "def router_node(state: WorkflowState, window_size: int = 5)" in all_code
    ), "Router node not found"
    assert "Recent conversation (last {window_size} messages):" in all_code
    assert "TypedDict" in all_code, "TypedDict state not found"
    assert "route_history" in all_code, "Router reducer-backed state field missing"
    assert "Command" in all_code, "Router should use Command-based routing"

    # Verify no empty implementations (no standalone 'pass' statements for nodes)
    # Note: We allow pass in fallback scenarios, but pattern code should not have it
    code_sections = all_code.split("\n\n")
    router_related = [s for s in code_sections if "def router_node" in s]
    if router_related:
        # Router node should have actual implementation, not just pass
        assert "with_structured_output" in all_code or "ChatOpenAI" in all_code, (
            "Router notebook should include model-backed routing logic"
        )

    # Verify graph construction
    assert "StateGraph(WorkflowState)" in all_code, "Graph construction missing"
    assert "add_node" in all_code, "Graph node addition missing"
    assert "compile" in all_code, "Graph compilation missing"

    execution_cells = [
        cell for cell in nb.cells if cell.cell_type == "code" and 'config = {"configurable"' in cell.source
    ]
    assert execution_cells, "Execution cell missing"
    execution_source = execution_cells[0].source
    assert '"route": ""' in execution_source
    assert '"results": {}' in execution_source
    assert '"final_output": ""' in execution_source


@pytest.mark.asyncio
async def test_subagents_pattern_notebook_generation(tmp_path: Path):
    """Test notebook generation with subagents pattern."""

    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    os.environ['BASE_OUTPUT_DIR'] = str(tmp_path.resolve())

    # Generate notebook for subagents pattern
    artifacts = await generate_artifacts(
        prompt="Create a supervisor-based multi-agent system with researcher, writer, and reviewer agents",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    # Load the generated notebook
    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    assert notebook_path.exists(), "Notebook not generated"

    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Extract all code cells
    code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]
    all_code = "\n\n".join([cell.source for cell in code_cells])

    # Verify pattern-specific code generation
    assert "TypedDict" in all_code, "TypedDict state not found"
    assert "next_agent:" in all_code, "Supervisor state field 'next_agent' missing"
    assert "instructions:" in all_code, "Supervisor state field 'instructions' missing"
    assert "Command" in all_code, "Supervisor should use Command-based routing"

    # Verify graph construction
    assert "StateGraph(WorkflowState)" in all_code, "Graph construction missing"
    assert "finish_node" in all_code, "Finish node missing"

    execution_cells = [
        cell for cell in nb.cells if cell.cell_type == "code" and 'config = {"configurable"' in cell.source
    ]
    assert execution_cells, "Execution cell missing"
    execution_source = execution_cells[0].source
    assert '"next": "supervisor"' in execution_source
    assert '"instructions": ""' in execution_source
    assert '"task_results": {}' in execution_source


@pytest.mark.asyncio
async def test_tool_code_generation_not_empty(tmp_path: Path):
    """Test that tools have real implementations, not just 'pass' statements."""

    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    os.environ['BASE_OUTPUT_DIR'] = str(tmp_path.resolve())

    # Generate notebook that should have tools
    artifacts = await generate_artifacts(
        prompt="Create a system that can search the web and process data",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    # Load the generated notebook
    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Find tools section
    code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]

    meaningful_markers = ("DuckDuckGoSearchRun", "Path(", "requests.get", "return {")
    for cell in code_cells:
        if "# Tool:" in cell.source or (
            "def " in cell.source and "_tool" in cell.source.lower()
        ):
            assert "pass" not in cell.source, f"Tool implementation should not contain pass: {cell.source[:200]}"
            assert "TODO" not in cell.source, f"Tool implementation should not contain TODO: {cell.source[:200]}"
            assert "Implement your tool logic here" not in cell.source
            assert any(marker in cell.source for marker in meaningful_markers), (
                f"Tool implementation lacks meaningful logic markers: {cell.source[:200]}"
            )

    # It's ok if no tools found for some prompts
    # The main check is if tools exist, they should have meaningful content


@pytest.mark.asyncio
async def test_node_code_generation_not_empty(tmp_path: Path):
    """Test that nodes have real implementations or meaningful templates."""

    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    os.environ['BASE_OUTPUT_DIR'] = str(tmp_path.resolve())

    # Generate notebook
    artifacts = await generate_artifacts(
        prompt="Create a chatbot that can route between search and analysis",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    # Load the generated notebook
    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Find node implementations
    code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]

    node_found = False
    for cell in code_cells:
        if "def " in cell.source and "_node(state:" in cell.source:
            node_found = True
            assert "return state" not in cell.source, f"Node implementation contains stub return: {cell.source[:200]}"
            assert "pass" not in cell.source, f"Node implementation contains pass: {cell.source[:200]}"
            assert "TODO: Implement" not in cell.source, f"Node implementation contains TODO placeholder: {cell.source[:200]}"
            has_logic = any(
                keyword in cell.source
                for keyword in [
                    "ChatOpenAI",
                    "llm",
                    "messages",
                    "invoke",
                    "results",
                    "task_results",
                    "current_draft",
                ]
            )
            assert has_logic, f"Node implementation too minimal: {cell.source[:200]}"

    # We should find at least one node
    assert node_found, "No node implementations found in notebook"


@pytest.mark.asyncio
async def test_generated_code_is_syntactically_valid(tmp_path: Path):
    """Test that all generated Python code is syntactically valid."""

    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    os.environ['BASE_OUTPUT_DIR'] = str(tmp_path.resolve())

    # Generate notebook
    artifacts = await generate_artifacts(
        prompt="Create a simple multi-agent workflow",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    # Load the generated notebook
    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Check each code cell for syntax errors
    code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]

    for i, cell in enumerate(code_cells):
        try:
            # Skip cells with magic commands
            if cell.source.strip().startswith("!") or cell.source.strip().startswith("%"):
                continue

            # Filter out magic commands from within cells
            clean_source = "\n".join(
                line for line in cell.source.split("\n")
                if not line.strip().startswith("!") and not line.strip().startswith("%")
            )

            # Try to compile each cell
            compile(clean_source, f"<cell-{i}>", "exec")
        except SyntaxError as e:
            pytest.fail(
                f"Cell {i} has syntax error: {e}\nCell content:\n{cell.source[:500]}"
            )


@pytest.mark.asyncio
async def test_pattern_selection_based_on_prompt(tmp_path: Path):
    """Test that different prompts result in appropriate pattern selection."""

    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    os.environ['BASE_OUTPUT_DIR'] = str(tmp_path.resolve())

    # Test router pattern selection
    artifacts_router = await generate_artifacts(
        prompt="Create a routing system that directs queries to specialized agents",
        output_dir=tmp_path / "router",
        mode="stub",
        formats=["ipynb"],
    )

    notebook_path = Path(artifacts_router["manifest"]["notebook_path"])
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    all_content = "\n".join([cell.source for cell in nb.cells])

    # The architecture should be mentioned in the notebook
    assert (
        "router" in all_content.lower() or "routing" in all_content.lower()
    ), "Router pattern not reflected in notebook"


@pytest.mark.asyncio
async def test_complete_workflow_has_no_broken_references(tmp_path: Path):
    """Test that generated notebooks have no undefined variable references."""

    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    os.environ['BASE_OUTPUT_DIR'] = str(tmp_path.resolve())

    # Generate notebook
    artifacts = await generate_artifacts(
        prompt="Create a multi-agent system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    # Load the generated notebook
    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]
    all_code = "\n".join([cell.source for cell in code_cells])

    # Common issues to check
    # 1. If StateGraph is used, WorkflowState should be defined
    if "StateGraph(WorkflowState)" in all_code:
        assert "class WorkflowState" in all_code, "WorkflowState used but not defined"

    # 2. If nodes are added to graph, they should be defined
    import re

    node_additions = re.findall(r'add_node\("([^"]+)"', all_code)
    for node_name in node_additions:
        node_func = f"def {node_name}_node" if node_name != "node_name" else None
        if node_func:
            # Either the function should exist or it should be a comment/example
            if "# " not in all_code or node_func not in all_code:
                # Check it's not just a placeholder
                assert (
                    node_func in all_code or "# Add your" in all_code
                ), f"Node '{node_name}' added to graph but function not defined"


@pytest.mark.asyncio
async def test_notebooks_include_execution_section(tmp_path: Path):
    """Test that generated notebooks include complete execution sections."""

    # Set BASE_OUTPUT_DIR to allow test output in tmp_path
    os.environ['BASE_OUTPUT_DIR'] = str(tmp_path.resolve())

    # Generate notebook
    artifacts = await generate_artifacts(
        prompt="Create a chatbot system",
        output_dir=tmp_path,
        mode="stub",
        formats=["ipynb"],
    )

    # Load the generated notebook
    notebook_path = Path(artifacts["manifest"]["notebook_path"])
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    # Check for execution section
    sections = {cell.metadata.get("section") for cell in nb.cells}
    assert "execution" in sections, "No execution section in notebook"

    # Find execution cells
    exec_cells = [
        cell
        for cell in nb.cells
        if cell.metadata.get("section") == "execution" and cell.cell_type == "code"
    ]

    assert len(exec_cells) > 0, "No execution code cells"

    # Execution cells should contain invocation logic
    exec_code = "\n".join([cell.source for cell in exec_cells])
    assert any(
        keyword in exec_code for keyword in ["invoke", "stream", "graph"]
    ), "Execution cells missing graph invocation"
