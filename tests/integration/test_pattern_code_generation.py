"""Integration tests for pattern-based code generation in notebooks."""

from __future__ import annotations

from pathlib import Path

import nbformat
import pytest

from langgraph_system_generator.cli import generate_artifacts


@pytest.mark.asyncio
async def test_router_pattern_notebook_generation(tmp_path: Path):
    """Test notebook generation with router pattern."""

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
    assert "def router_node(state: WorkflowState)" in all_code, "Router node not found"

    # Verify no empty implementations (no standalone 'pass' statements for nodes)
    # Note: We allow pass in fallback scenarios, but pattern code should not have it
    code_sections = all_code.split("\n\n")
    router_related = [s for s in code_sections if "def router_node" in s]
    if router_related:
        # Router node should have actual implementation, not just pass
        assert any(
            "ChatOpenAI" in section or "llm" in section.lower()
            for section in router_related
        ), "Router node has no LLM implementation"

    # Verify graph construction
    assert "StateGraph(WorkflowState)" in all_code, "Graph construction missing"
    assert "add_node" in all_code, "Graph node addition missing"
    assert "compile" in all_code, "Graph compilation missing"


@pytest.mark.asyncio
async def test_subagents_pattern_notebook_generation(tmp_path: Path):
    """Test notebook generation with subagents pattern."""

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
    assert "class WorkflowState(MessagesState):" in all_code, "State class not found"
    assert "next:" in all_code, "Supervisor state field 'next' missing"
    assert "instructions:" in all_code, "Supervisor state field 'instructions' missing"

    # Verify graph construction
    assert "StateGraph(WorkflowState)" in all_code, "Graph construction missing"
    assert "add_conditional_edges" in all_code, "Conditional edges missing"


@pytest.mark.asyncio
async def test_tool_code_generation_not_empty(tmp_path: Path):
    """Test that tools have real implementations, not just 'pass' statements."""

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

    for cell in code_cells:
        if "# Tool:" in cell.source or (
            "def " in cell.source and "_tool" in cell.source.lower()
        ):
            # Tool should have either real implementation or helpful comments
            # Check it's not just "pass" with nothing else
            lines = [
                line.strip()
                for line in cell.source.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
            # If there's only a function def and pass, it's too empty
            if len(lines) <= 3:  # def, docstring, pass
                has_impl_hints = (
                    "Example" in cell.source
                    or "TODO" in cell.source
                    or "import" in cell.source.lower()
                )
                assert (
                    has_impl_hints
                ), f"Tool implementation too minimal: {cell.source[:200]}"

    # It's ok if no tools found for some prompts
    # The main check is if tools exist, they should have meaningful content


@pytest.mark.asyncio
async def test_node_code_generation_not_empty(tmp_path: Path):
    """Test that nodes have real implementations or meaningful templates."""

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
            # Node should have more than just "return state"
            # Look for LLM usage, message handling, or other logic
            has_logic = any(
                keyword in cell.source
                for keyword in [
                    "ChatOpenAI",
                    "llm",
                    "messages",
                    "invoke",
                    "Example",
                    "TODO",
                ]
            )
            assert has_logic, f"Node implementation too minimal: {cell.source[:200]}"

    # We should find at least one node
    assert node_found, "No node implementations found in notebook"


@pytest.mark.asyncio
async def test_generated_code_is_syntactically_valid(tmp_path: Path):
    """Test that all generated Python code is syntactically valid."""

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
