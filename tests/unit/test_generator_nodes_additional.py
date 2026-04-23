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
from langgraph_system_generator.generator.state import (
    ArchitectureFeedback,
    CellSpec,
    Constraint,
    GraphDesignFeedback,
    GraphExportBundle,
    NotebookCompositionFeedback,
    NotebookCompositionResult,
    NotebookDependencyPlan,
    QAReport,
    QARepairFeedback,
    ToolPlanningFeedback,
)
from langgraph_system_generator.utils.config import GenerationConfig


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
    payload = """
    {
      "constraints": [{"type":"goal","value":"Test","priority":5}],
      "feedback": {
        "fallback_used": false,
        "fallback_reason": null,
        "missing_inputs": [],
        "conflicts": [],
        "suggestions": [],
        "available_constraint_types": ["goal", "tone"]
      }
    }
    """

    monkeypatch.setattr(
        requirements_analyst,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    result = await intake_node({"user_prompt": "Build a test workflow"})

    assert result["constraints"] == constraints
    assert result["requirements_feedback"].fallback_used is False
    assert "goal" in result["requirements_feedback"].available_constraint_types
    assert "tone" in result["requirements_feedback"].available_constraint_types


@pytest.mark.asyncio
async def test_rag_retrieval_node_falls_back_on_failure(monkeypatch):
    """Test that rag_retrieval_node returns empty docs_context when DocsRetriever.retrieve fails.

    This test ensures VectorStoreManager initialization succeeds (by mocking OpenAIEmbeddings)
    so that the actual retrieval failure path is exercised.
    """
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

    result = await architecture_selection_node({"constraints": [], "docs_context": []})

    assert result["selected_patterns"] == {"primary": "router", "secondary": []}
    assert result["architecture_type"] == "router"
    assert result["architecture_justification"] == "Because"
    assert result["architecture_feedback"].fallback_used is False


@pytest.mark.asyncio
async def test_architecture_selection_node_surfaces_selector_fallback_feedback(monkeypatch):
    payload = '{"architecture_type":"swarm","patterns":{"primary":"swarm","secondary":[]},"justification":"x"}'

    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    monkeypatch.setattr(
        "langgraph_system_generator.generator.agents.architecture_selector.DocsRetriever.retrieve_for_pattern",
        lambda self, pattern_name: [],
    )

    result = await architecture_selection_node({"constraints": [], "docs_context": []})

    assert result["architecture_type"] == "router"
    assert result["selected_patterns"] == {"primary": "router", "secondary": []}
    assert result["architecture_feedback"].fallback_used is True
    assert result["architecture_feedback"].validation_errors


@pytest.mark.asyncio
async def test_architecture_selection_node_honors_agent_type_override():
    result = await architecture_selection_node(
        {
            "constraints": [],
            "docs_context": [],
            "generation_config": GenerationConfig(agent_type="subagents"),
        }
    )

    assert result["selected_patterns"] == {"primary": "subagents", "secondary": []}
    assert result["architecture_type"] == "subagents"
    assert "agent_type override" in result["architecture_justification"]
    assert result["architecture_feedback"].fallback_used is False
    assert result["architecture_feedback"].confidence == pytest.approx(1.0)
    assert result["architecture_feedback"].tradeoffs


@pytest.mark.asyncio
async def test_architecture_selection_node_honors_autoagent_override():
    result = await architecture_selection_node(
        {
            "constraints": [],
            "docs_context": [],
            "generation_config": GenerationConfig(agent_type="autoagent"),
        }
    )

    assert result["selected_patterns"] == {"primary": "autoagent", "secondary": []}
    assert result["architecture_type"] == "autoagent"
    assert "agent_type override" in result["architecture_justification"]
    assert result["architecture_feedback"].fallback_used is False


@pytest.mark.asyncio
async def test_architecture_selection_node_honors_hybrid_override():
    result = await architecture_selection_node(
        {
            "constraints": [],
            "docs_context": [],
            "generation_config": GenerationConfig(agent_type="hybrid"),
        }
    )

    assert result["selected_patterns"] == {
        "primary": "hybrid",
        "secondary": ["router", "subagents"],
    }
    assert result["architecture_type"] == "hybrid"
    assert "agent_type override" in result["architecture_justification"]
    assert result["architecture_feedback"].fallback_used is False
    assert result["architecture_feedback"].docs_considered == []


@pytest.mark.asyncio
async def test_graph_design_node_defaults_architecture_type(monkeypatch):
    payload = """
    {
      "state_schema": {
        "messages": "Conversation state",
        "next_agent": "Selected worker"
      },
      "nodes": [
        {"name": "supervisor", "purpose": "Coordinate workers"},
        {"name": "researcher", "purpose": "Research documents"},
        {"name": "critic", "purpose": "Critique results"}
      ],
      "edges": [],
      "conditional_edges": [
        {
          "from": "supervisor",
          "condition": "Dispatch to next worker",
          "branches": {
            "researcher": "researcher",
            "critic": "critic",
            "FINISH": "END"
          }
        }
      ],
      "entry_point": "supervisor",
      "checkpointing": true
    }
    """

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
    assert result["workflow_design"]["architecture_type"] == "subagents"
    assert result["workflow_design"]["entry_point"] == "supervisor"
    assert result["graph_design_feedback"].fallback_used is False
    assert "flowchart TD" in result["graph_exports"].mermaid
    assert result["graph_exports"].schema["entry_point"] == "supervisor"


@pytest.mark.asyncio
async def test_tooling_plan_node_returns_tools_plan(monkeypatch):
    payload = '[{"name":"tool","category":"misc","purpose":"x","configuration":{}}]'

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    result = await tooling_plan_node(
        {"workflow_design": {"nodes": []}, "constraints": []}
    )

    assert result["tools_plan"] == [
        {
            "tool_id": "tool",
            "name": "tool",
            "category": "misc",
            "purpose": "x",
            "configuration": {},
            "packages": [],
            "provider_env_vars": [],
            "status": "unsupported",
            "warnings": [
                "Unsupported tool suggestion 'tool' could not be resolved to a canonical tool."
            ],
        }
    ]
    assert result["tool_planning_feedback"].fallback_used is True
    assert result["tool_planning_feedback"].unresolved_tools == ["tool"]


@pytest.mark.asyncio
async def test_tooling_plan_node_preserves_environment_feedback(monkeypatch):
    payload = (
        '[{"tool_id":"web_search","name":"web_search","category":"search",'
        '"purpose":"Look up docs","configuration":{}}]'
    )

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    result = await tooling_plan_node(
        {
            "workflow_design": {
                "nodes": [{"name": "research", "purpose": "Search docs"}]
            },
            "constraints": [
                Constraint(
                    type="environment",
                    value="Offline only, no network access",
                    priority=5,
                )
            ],
        }
    )

    assert result["tools_plan"][0]["status"] == "unsupported"
    assert result["tool_planning_feedback"].environment_notes
    assert result["tool_planning_feedback"].unresolved_tools == ["web_search"]


@pytest.mark.asyncio
async def test_notebook_assembly_node_returns_generated_cells(monkeypatch):
    cells = [CellSpec(cell_type="markdown", content="Hi", metadata={})]
    feedback = NotebookCompositionFeedback(
        fallback_used=True,
        warnings=["Notebook composition used deterministic fallback content."],
    )
    dependency_plan = NotebookDependencyPlan(
        packages=["langgraph", "langchain-openai"]
    )
    # Mock NotebookComposer to return cells without needing LLM
    payload = "[]"  # Dummy payload since we'll mock the compose method

    monkeypatch.setattr(
        notebook_composer,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    async def fake_compose_notebook(*_args, **_kwargs):
        return NotebookCompositionResult(
            cells=cells,
            feedback=feedback,
            dependency_plan=dependency_plan,
        )

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookComposer.compose_notebook",
        fake_compose_notebook,
    )

    state = {
        "notebook_plan": None,
        "workflow_design": {
            "graph_exports": {
                "mermaid": "flowchart TD\n    A-->B",
                "schema": {"entry_point": "router"},
            }
        },
        "graph_exports": GraphExportBundle(
            mermaid="flowchart TD\n    A-->B",
            schema={"entry_point": "router"},
        ),
        "tools_plan": [],
        "tool_planning_feedback": ToolPlanningFeedback(
            fallback_used=True,
            fallback_reason="Heuristic tool fallback used.",
            unresolved_tools=["imaginary_tool"],
            available_tool_ids=["web_search"],
            warnings=["Heuristic tool fallback used."],
        ),
        "selected_patterns": {"primary": "router"},
        "architecture_justification": "Reason",
    }
    result = await notebook_assembly_node(state)

    assert result["generated_cells"] == cells
    assert result["notebook_composition_feedback"] == feedback
    assert result["notebook_dependency_plan"] == dependency_plan


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

    assert result["qa_reports"][0].check_name == "New"
    assert result["qa_reports"][0].stage == "static"
    assert result["qa_reports"][0].attempt == 0
    assert result["qa_history"][0] == existing[0]
    assert result["qa_history"][-1].check_name == "New"
    assert result["qa_history"][-1].stage == "static"
    assert result["qa_repair_feedback"].unrepaired_failures == []


@pytest.mark.asyncio
async def test_static_qa_node_surfaces_blocking_feedback(monkeypatch):
    blocking_report = QAReport(
        check_name="Python Syntax",
        passed=False,
        message="Syntax error in notebook code: invalid syntax at line 3",
        rule_id="python_syntax",
        severity="error",
        category="syntax",
        repairable=True,
        suggestions=["Fix the syntax error before execution."],
    )

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookValidator.validate_all",
        lambda *_args, **_kwargs: [blocking_report],
    )

    result = await static_qa_node(
        {
            "generated_cells": [CellSpec(cell_type="code", content="broken(", metadata={})],
            "qa_reports": [],
            "repair_attempts": 0,
        }
    )

    assert result["qa_repair_feedback"].unrepaired_failures == [
        "Python Syntax: Syntax error in notebook code: invalid syntax at line 3"
    ]
    assert "Fix the syntax error before execution." in result["qa_repair_feedback"].next_steps


@pytest.mark.asyncio
async def test_runtime_qa_node_message_empty_cells():
    result = await runtime_qa_node(
        {
            "generated_cells": [],
            "qa_reports": [],
            "qa_history": [],
            "generation_mode": "live",
            "repair_attempts": 0,
        }
    )

    report = result["qa_reports"][-1]
    assert "no generated cells" in report.message
    assert report.stage == "runtime"
    assert result["qa_repair_feedback"].unrepaired_failures == []


@pytest.mark.asyncio
async def test_runtime_qa_node_executes_trusted_smoke_test(monkeypatch):
    captured = {"called": False}
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.inspect_notebook_runtime_support",
        lambda kernel_name="python3": (
            True,
            "Kernel 'python3' is available for notebook execution.",
            {"kernel_name": kernel_name, "kind": "preflight"},
        ),
    )
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.run_notebook_smoke_test",
        lambda kernel_name="python3", timeout=60: (
            captured.update({"called": True}),
            True,
            "Runtime execution environment validated using the 'python3' kernel.",
        )[1:],
    )

    state = {
        "generated_cells": [CellSpec(cell_type="code", content="print('Hi')", metadata={})],
        "qa_reports": [],
        "qa_history": [],
        "generation_mode": "live",
        "repair_attempts": 0,
    }
    result = await runtime_qa_node(state)

    report = result["qa_reports"][-1]
    assert captured["called"] is True
    assert "Runtime execution environment validated" in report.message
    assert report.passed is True
    assert report.evidence["execution"]["execution_scope"] == "trusted_smoke_test"
    assert report.evidence["preflight"]["kind"] == "preflight"


@pytest.mark.asyncio
async def test_runtime_qa_node_reports_kernel_failure_in_live_mode(monkeypatch):
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.inspect_notebook_runtime_support",
        lambda kernel_name="python3": (
            False,
            "Runtime validation unavailable: kernel 'python3' is not registered.",
            {"kernel_name": kernel_name, "failure_kind": "runtime_unavailable"},
        ),
    )

    state = {
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "qa_reports": [],
        "qa_history": [],
        "generation_mode": "live",
        "repair_attempts": 0,
    }
    result = await runtime_qa_node(state)

    report = result["qa_reports"][-1]
    assert "Runtime validation unavailable" in report.message
    assert report.passed is False
    assert report.evidence["failure_kind"] == "runtime_unavailable"
    assert result["qa_repair_feedback"].unrepaired_failures == [
        f"{report.check_name}: {report.message}"
    ]


@pytest.mark.asyncio
async def test_runtime_qa_node_reports_missing_dependency_skipped_in_stub_mode(
    monkeypatch,
):
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.inspect_notebook_runtime_support",
        lambda kernel_name="python3": (
            False,
            "Runtime validation unavailable: missing notebook execution dependency (No module named 'nbclient').",
            {"kernel_name": kernel_name, "failure_kind": "runtime_unavailable"},
        ),
    )

    state = {
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "qa_reports": [],
        "qa_history": [],
        "generation_mode": "stub",
        "repair_attempts": 0,
    }
    result = await runtime_qa_node(state)

    report = result["qa_reports"][-1]
    assert "Runtime validation unavailable" in report.message
    assert report.passed is True
    assert report.evidence["failure_kind"] == "runtime_unavailable"


@pytest.mark.asyncio
async def test_runtime_qa_node_reports_actual_failure(monkeypatch):
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.inspect_notebook_runtime_support",
        lambda kernel_name="python3": (
            True,
            "Kernel 'python3' is available for notebook execution.",
            {"kernel_name": kernel_name},
        ),
    )
    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.run_notebook_smoke_test",
        lambda kernel_name="python3", timeout=60: (
            False,
            "Runtime validation failed: smoke notebook executed without the expected output.",
        ),
    )

    state = {
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "qa_reports": [],
        "qa_history": [],
        "generation_mode": "live",
        "repair_attempts": 0,
    }
    result = await runtime_qa_node(state)

    report = result["qa_reports"][-1]
    assert "Runtime validation failed" in report.message
    assert report.passed is False
    assert report.evidence["execution"]["execution_scope"] == "trusted_smoke_test"


@pytest.mark.asyncio
async def test_repair_node_success_refreshes_cells_and_appends_history(monkeypatch):
    initial_cells = [CellSpec(cell_type="markdown", content="Hi", metadata={})]
    updated_cells = [CellSpec(cell_type="markdown", content="Updated", metadata={})]
    updated_reports = [QAReport(check_name="Fix", passed=True, message="done")]
    existing_history = [QAReport(check_name="Runtime Check", passed=False, message="boom")]

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
        "qa_reports": [
            QAReport(check_name="Runtime Check", passed=False, message="boom", stage="runtime")
        ],
        "qa_history": existing_history,
        "repair_attempts": 1,
    }
    result = await repair_node(state)

    assert result["generated_cells"] == updated_cells
    assert result["qa_reports"][0].check_name == "Fix"
    assert result["qa_reports"][0].stage == "static"
    assert result["qa_reports"][0].attempt == 2
    assert len(result["qa_history"]) == len(existing_history) + 1
    assert result["qa_history"][-1].check_name == "Repair Attempt"
    assert result["repair_attempts"] == 2
    assert result["qa_repair_feedback"].repair_attempts == 2
    assert result["qa_repair_feedback"].unrepaired_failures == []


@pytest.mark.asyncio
async def test_repair_node_failure_keeps_cells_and_appends_history(monkeypatch):
    initial_cells = [CellSpec(cell_type="markdown", content="Hi", metadata={})]
    updated_reports = [QAReport(check_name="Fix", passed=False, message="fail")]
    existing_history = [QAReport(check_name="Runtime Check", passed=False, message="boom")]

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookRepairAgent.repair_notebook",
        lambda *_args, **_kwargs: (False, updated_reports),
    )

    state = {
        "generated_cells": initial_cells,
        "qa_reports": [
            QAReport(check_name="Runtime Check", passed=False, message="boom", stage="runtime")
        ],
        "qa_history": existing_history,
        "repair_attempts": 3,
    }
    result = await repair_node(state)

    assert result["generated_cells"] == initial_cells
    assert result["qa_reports"][0].check_name == "Fix"
    assert result["qa_reports"][0].stage == "static"
    assert result["qa_reports"][0].attempt == 4
    assert len(result["qa_history"]) == len(existing_history) + 1
    assert result["qa_history"][-1].passed is False
    assert result["repair_attempts"] == 4
    assert result["qa_repair_feedback"].repair_attempts == 4
    assert "Repair attempt did not resolve" in result["qa_repair_feedback"].warnings[-1]


@pytest.mark.asyncio
async def test_package_outputs_node_manifest_fields():
    state = {
        "notebook_plan": "Plan",
        "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
        "constraints": [Constraint(type="goal", value="Test", priority=1)],
        "selected_patterns": {"primary": "hybrid"},
        "architecture_type": None,
        "architecture_feedback": ArchitectureFeedback(
            fallback_used=True,
            fallback_reason="Validation failed.",
            validation_errors=["Unsupported architecture_type 'swarm'."],
        ),
        "graph_design_feedback": GraphDesignFeedback(
            fallback_used=True,
            fallback_reason="Live graph design validation failed.",
            validation_errors=["Duplicate node id 'router'."],
            warnings=["Recovered using deterministic hybrid fallback."],
        ),
        "graph_exports": GraphExportBundle(
            mermaid="flowchart TD\n    router --> finish",
            schema={
                "entry_point": "router",
                "terminal_nodes": ["finish"],
                "validation_summary": {
                    "errors": ["Duplicate node id 'router'."],
                    "warnings": ["Recovered using deterministic hybrid fallback."],
                },
            },
        ),
        "tool_planning_feedback": ToolPlanningFeedback(
            fallback_used=True,
            fallback_reason="Tool planning used heuristic fallback inference.",
            validation_errors=["Unsupported tool suggestion 'swarm_tool'."],
            unresolved_tools=["swarm_tool"],
            available_tool_ids=["web_search", "http_client"],
            warnings=["Tool planning used heuristic fallback inference."],
        ),
        "notebook_composition_feedback": NotebookCompositionFeedback(
            fallback_used=True,
            warnings=["Deterministic fallback used for node \"enrich\"."],
            sections_built=["intro", "install", "config", "state", "nodes", "graph"],
        ),
        "notebook_dependency_plan": NotebookDependencyPlan(
            packages=["langgraph", "langchain-openai", "requests"],
            provider_env_vars=["OPENAI_API_KEY"],
        ),
        "qa_repair_feedback": QARepairFeedback(
            repair_attempts=1,
            unrepaired_failures=["Runtime Check: Runtime validation failed."],
            next_steps=["Inspect the runtime environment before retrying."],
            warnings=["Blocking QA issues remain after validation or repair."],
        ),
    }
    result = await package_outputs_node(state)

    manifest = result["artifacts_manifest"]
    assert manifest["cell_count"] == "1"
    assert manifest["constraints_count"] == "1"
    assert manifest["architecture_type"] == "hybrid"
    assert manifest["architecture_feedback"]["fallback_used"] is True
    assert manifest["graph_design_feedback"]["fallback_used"] is True
    assert "flowchart TD" in manifest["graph_exports"]["mermaid"]
    assert manifest["tool_planning_feedback"]["fallback_used"] is True
    assert manifest["notebook_composition_feedback"]["fallback_used"] is True
    assert "requests" in manifest["notebook_dependency_plan"]["packages"]
    assert manifest["qa_repair_feedback"]["repair_attempts"] == 1
    assert result["generation_complete"] is True
