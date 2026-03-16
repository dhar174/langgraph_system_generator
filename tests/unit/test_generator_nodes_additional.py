"""Additional tests for generator graph nodes with synthetic state inputs."""

import pytest

from langgraph_system_generator.generator.agents import (
    architecture_selector,
    graph_designer,
    notebook_composer,
    requirements_analyst,
    toolchain_engineer,
)
from langgraph_system_generator.generator.nodes import (
    _runtime_qa_suggestions,
    architecture_selection_node,
    graph_design_node,
    intake_node,
    notebook_assembly_node,
    package_outputs_node,
    rag_retrieval_node,
    repair_node,
    runtime_qa_node,
    static_qa_node,
    tooling_plan_node,
)
from langgraph_system_generator.generator.state import CellSpec, Constraint, QAReport


class DummyResponse:
    """Simple stub for LLM response objects."""

    def __init__(self, content: str):
        self.content = content


def make_stub_llm(content: str):
    """Create a ChatOpenAI stub that returns a fixed response payload."""

    class StubLLM:
        def __init__(self, *_args, **_kwargs):
            self._content = content

        async def ainvoke(self, _messages):
            return DummyResponse(self._content)

    return StubLLM


@pytest.mark.asyncio
async def test_intake_node_sets_constraints(monkeypatch):
    constraints = [Constraint(type="goal", value="Test", priority=5)]
    payload = '[{"type":"goal","value":"Test","priority":5}]'

    monkeypatch.setattr(
        requirements_analyst,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    result = await intake_node({"user_prompt": "Build a test workflow"})

    assert result["constraints"] == constraints
r

@pytest.mark.asyncio
async def test_rag_retrieval_node_falls_back_on_failure(monkeypatch):
    """Test that rag_retrieval_node returns empty docs_context when DocsRetriever.retrieve fails.
    
    This test ensures VectorStoreManager initialization succeeds (by mocking OpenAIEmbeddings)
    so that the actual retrieval failure path is exercised.
    """
    from unittest.mock import Mock
    from langchain_community.embeddings import FakeEmbeddings

    # Mock OpenAIEmbeddings to avoid requiring credentials and ensure VectorStoreManager succeeds
    monkeypatch.setattr(
        "langgraph_system_generator.rag.embeddings.OpenAIEmbeddings",
        lambda: FakeEmbeddings(size=32),
    )

    # Mock DocsRetriever.retrieve to raise an exception
    def fake_retrieve(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.DocsRetriever.retrieve",
        fake_retrieve,
    )

    result = await rag_retrieval_node({"user_prompt": "Need docs"})

    assert result["docs_context"] == []


@pytest.mark.asyncio
async def test_architecture_selection_node_defaults_when_missing(monkeypatch):
    payload = '{"architecture_type":"router","patterns":null,"justification":"Because"}'

    # Mock ChatOpenAI to avoid real LLM calls
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    # Mock DocsRetriever.retrieve_for_pattern to avoid real embeddings/FAISS similarity search
    monkeypatch.setattr(
        "langgraph_system_generator.generator.agents.architecture_selector.DocsRetriever.retrieve_for_pattern",
        lambda self, pattern_name: [],
    )

    result = await architecture_selection_node(
        {"constraints": [], "docs_context": []}
    )

    assert result["selected_patterns"] == {}
    assert result["architecture_type"] == "router"
    assert result["architecture_justification"] == "Because"


@pytest.mark.asyncio
async def test_graph_design_node_defaults_architecture_type(monkeypatch):
    payload = '{"nodes":["a","b"]}'

    monkeypatch.setattr(
        graph_designer,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    state = {
        "user_prompt": "Test workflow",
        "constraints": [Constraint(type="goal", value="Test", priority=1)],
        "selected_patterns": {"primary": "subagents"},
        "architecture_justification": "Reason",
    }
    result = await graph_design_node(state)

    notebook_plan = result["notebook_plan"]
    assert notebook_plan.title.startswith("LangGraph Workflow: Test workflow")
    assert notebook_plan.sections == [
        "Setup",
        "State Definition",
        "Tools",
        "Nodes",
        "Graph Construction",
        "Execution",
    ]
    assert notebook_plan.patterns_used == ["subagents"]
    assert notebook_plan.architecture_type == "subagents"
    assert result["workflow_design"] == {"nodes": ["a", "b"]}


@pytest.mark.asyncio
async def test_tooling_plan_node_returns_tools_plan(monkeypatch):
    payload = '[{"name":"tool","category":"misc","purpose":"x","configuration":{}}]'

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    result = await tooling_plan_node({"workflow_design": {"nodes": []}, "constraints": []})

    assert result["tools_plan"] == [{"name": "tool", "category": "misc", "purpose": "x", "configuration": {}}]


@pytest.mark.asyncio
async def test_notebook_assembly_node_returns_generated_cells(monkeypatch):
    cells = [CellSpec(cell_type="markdown", content="Hi", metadata={})]
    # Mock NotebookComposer to return cells without needing LLM
    payload = '[]'  # Dummy payload since we'll mock the compose method

    monkeypatch.setattr(
        notebook_composer,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    
    async def fake_compose_notebook(*_args, **_kwargs):
        return cells
    
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookComposer.compose_notebook",
        fake_compose_notebook,
    )

    state = {
        "notebook_plan": None,
        "workflow_design": {},
        "tools_plan": [],
        "selected_patterns": {"primary": "router"},
        "architecture_justification": "Reason",
    }
    result = await notebook_assembly_node(state)

    assert result["generated_cells"] == cells


@pytest.mark.asyncio
async def test_static_qa_node_appends_reports(monkeypatch):
    existing = [QAReport(check_name="Existing", passed=True, message="ok")]
    new_reports = [QAReport(check_name="New", passed=True, message="fine")]

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookValidator.validate_all",
        lambda *_args, **_kwargs: new_reports,
    )

    state = {
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "qa_reports": existing,
    }
    result = await static_qa_node(state)

    assert result["qa_reports"] == [*existing, *new_reports]


@pytest.mark.asyncio
async def test_runtime_qa_node_message_empty_cells():
    result = await runtime_qa_node({"generated_cells": [], "qa_reports": []})

    report = result["qa_reports"][-1]
    assert "no generated cells" in report.message


@pytest.mark.asyncio
async def test_runtime_qa_node_message_with_cells(monkeypatch):
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.run_notebook_smoke_test",
        lambda kernel_name="python3", timeout=60: (True, "Runtime execution environment validated using the 'python3' kernel."),
    )

    state = {
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "qa_reports": [],
    }
    result = await runtime_qa_node(state)

    report = result["qa_reports"][-1]
    assert "validated" in report.message
    assert report.passed is True


@pytest.mark.asyncio
async def test_runtime_qa_node_reports_kernel_failure(monkeypatch):
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.run_notebook_smoke_test",
        lambda kernel_name="python3", timeout=60: (False, "Runtime validation unavailable: kernel 'python3' is not registered."),
    )

    state = {
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "qa_reports": [],
    }
    result = await runtime_qa_node(state)

    report = result["qa_reports"][-1]
    assert "Runtime validation unavailable" in report.message
    # Kernel/runtime unavailability is treated as a skipped/warning, not a failure
    assert report.passed is True


@pytest.mark.asyncio
async def test_runtime_qa_node_reports_actual_failure(monkeypatch):
    """Actual smoke-test failures (not 'unavailable') should still fail the check."""
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.run_notebook_smoke_test",
        lambda kernel_name="python3", timeout=60: (False, "Runtime validation failed: smoke notebook executed without the expected output."),
    )

    state = {
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "qa_reports": [],
    }
    result = await runtime_qa_node(state)

    report = result["qa_reports"][-1]
    assert "Runtime validation failed" in report.message
    assert report.passed is False


@pytest.mark.asyncio
async def test_repair_node_success_refreshes_cells(monkeypatch):
    initial_cells = [CellSpec(cell_type="markdown", content="Hi", metadata={})]
    updated_cells = [CellSpec(cell_type="markdown", content="Updated", metadata={})]
    updated_reports = [QAReport(check_name="Fix", passed=True, message="done")]

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookRepairAgent.repair_notebook",
        lambda *_args, **_kwargs: (True, updated_reports),
    )
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes._cells_from_notebook",
        lambda *_args, **_kwargs: updated_cells,
    )

    state = {
        "generated_cells": initial_cells,
        "qa_reports": [],
        "repair_attempts": 1,
    }
    result = await repair_node(state)

    assert result["generated_cells"] == updated_cells
    assert result["qa_reports"] == updated_reports
    assert result["repair_attempts"] == 2


@pytest.mark.asyncio
async def test_repair_node_failure_keeps_cells(monkeypatch):
    initial_cells = [CellSpec(cell_type="markdown", content="Hi", metadata={})]
    updated_reports = [QAReport(check_name="Fix", passed=False, message="fail")]

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookRepairAgent.repair_notebook",
        lambda *_args, **_kwargs: (False, updated_reports),
    )

    state = {
        "generated_cells": initial_cells,
        "qa_reports": [],
        "repair_attempts": 3,
    }
    result = await repair_node(state)

    assert result["generated_cells"] == initial_cells
    assert result["qa_reports"] == updated_reports
    assert result["repair_attempts"] == 4


@pytest.mark.asyncio
async def test_package_outputs_node_manifest_fields():
    state = {
        "notebook_plan": "Plan",
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "constraints": [Constraint(type="goal", value="Test", priority=1)],
        "selected_patterns": {"primary": "hybrid"},
        "architecture_type": None,
    }
    result = await package_outputs_node(state)

    manifest = result["artifacts_manifest"]
    assert manifest["cell_count"] == "1"
    assert manifest["constraints_count"] == "1"
    assert manifest["architecture_type"] == "hybrid"
    assert result["generation_complete"] is True
