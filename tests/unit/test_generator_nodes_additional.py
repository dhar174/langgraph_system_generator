"""Additional tests for generator graph nodes with synthetic state inputs."""

import sys
import types

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
    context_pack_node,
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
    DocSnippet,
    GenerationContextPack,
    GraphDesignFeedback,
    GraphExportBundle,
    NotebookCompositionFeedback,
    NotebookCompositionResult,
    NotebookDependencyPlan,
    QAReport,
    QARepairFeedback,
    ToolPlanningFeedback,
)
from langgraph_system_generator.qa.registry import RepairRoutineRegistration
from langgraph_system_generator.qa.validators import (
    NotebookValidationContext,
    QAValidationRule,
)
from langgraph_system_generator.qa.repair import RepairOutcome
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


class NodePluginMarkerRule(QAValidationRule):
    """Synthetic plugin validator used by node integration tests."""

    rule_id = "node_plugin_marker"
    check_name = "Node Plugin Marker"
    category = "custom"
    failure_severity = "error"
    repairable = True

    def validate(self, context: NotebookValidationContext) -> QAReport:
        content = "\n".join(str(cell.source or "") for cell in context.notebook.cells)
        if "NODE_PLUGIN_BROKEN" in content:
            return self.failed_report("Node plugin marker needs repair.")
        return self.passed_report("Node plugin marker is absent.")


def _valid_generated_cells(*, execution_content: str | None = None):
    """Return a minimal valid generated cell set for node integration tests."""

    return [
        CellSpec(
            cell_type="code",
            content="from langgraph.graph import END, START, StateGraph\nfrom typing import TypedDict",
            metadata={"section": "setup"},
            section="setup",
        ),
        CellSpec(
            cell_type="code",
            content='config = {"configurable": {"thread_id": "demo"}, "recursion_limit": 25}',
            metadata={"section": "config"},
            section="config",
        ),
        CellSpec(
            cell_type="code",
            content=(
                "class WorkflowState(TypedDict, total=False):\n"
                "    messages: list\n\n"
                "workflow = StateGraph(WorkflowState)\n\n"
                "def start_node(state: WorkflowState):\n"
                "    return state\n\n"
                "workflow.add_node('start', start_node)\n"
                "workflow.add_edge(START, 'start')\n"
                "workflow.add_edge('start', END)\n"
                "graph = workflow.compile()"
            ),
            metadata={"section": "graph"},
            section="graph",
        ),
        CellSpec(
            cell_type="code",
            content=execution_content
            or (
                'initial_state = {"messages": []}\n'
                "result = graph.invoke(initial_state, config)\nprint(result)"
            ),
            metadata={"section": "execution"},
            section="execution",
        ),
    ]


def _install_qa_plugin(module_name: str, register_func) -> None:
    """Install an in-memory QA/repair plugin module."""

    module = types.ModuleType(module_name)
    module.register_qa_repair_plugins = register_func
    sys.modules[module_name] = module


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
async def test_context_pack_node_builds_docs_backed_contract_pack():
    result = await context_pack_node(
        {
            "user_prompt": "Build a museum artifact workflow",
            "generation_mode": "stub",
            "constraints": [
                Constraint(type="goal", value="Catalog artifacts", priority=5)
            ],
            "docs_context": [
                DocSnippet(
                    content="LangGraph recursion_limit is a top-level config key.",
                    source="https://docs.langchain.com/oss/python/langgraph/graph-api",
                    relevance_score=0.9,
                    heading="Recursion limit",
                )
            ],
        }
    )

    pack = result["generation_context_pack"]
    assert isinstance(pack, GenerationContextPack)
    assert pack.source_precedence[0] == "langchain-docs-local"
    assert "router" in pack.architecture_registry["supported_architecture_types"]
    assert pack.notebook_contract["compiled_graph_variable"] == "graph"
    assert (
        pack.notebook_contract["required_invocation_config"]["recursion_limit"]
        == "required_top_level_key"
    )
    assert pack.docs_snippets[0]["source"].startswith("https://docs.langchain.com")
    assert pack.fallback_used is False


@pytest.mark.asyncio
async def test_context_pack_node_falls_back_to_static_repo_facts_without_docs():
    result = await context_pack_node(
        {
            "user_prompt": "Build a workflow",
            "generation_mode": "stub",
            "constraints": [],
            "docs_context": [],
        }
    )

    pack = result["generation_context_pack"]
    assert pack.fallback_used is True
    assert pack.warnings
    assert "invocation_config" in pack.qa_gates


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
        "Build Graph",
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
async def test_static_qa_node_surfaces_non_blocking_feedback(monkeypatch):
    advisory_report = QAReport(
        check_name="Undefined Names",
        passed=False,
        message="Define or import 'app' before it is used.",
        rule_id="undefined_names",
        severity="warning",
        category="symbols",
        repairable=True,
        suggestions=["Check for small naming typos."],
    )

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookValidator.validate_all",
        lambda *_args, **_kwargs: [advisory_report],
    )

    result = await static_qa_node(
        {
            "generated_cells": [CellSpec(cell_type="code", content="app.invoke({})", metadata={})],
            "qa_reports": [],
            "repair_attempts": 0,
        }
    )

    assert result["qa_repair_feedback"].unrepaired_failures == []
    assert "Check for small naming typos." in result["qa_repair_feedback"].next_steps
    assert result["qa_repair_feedback"].warnings == [
        "Non-blocking QA advisories were recorded; artifacts remain usable."
    ]


@pytest.mark.asyncio
async def test_static_qa_node_valid_generated_cells_do_not_report_scaffold_app():
    result = await static_qa_node(
        {
            "generated_cells": _valid_generated_cells(),
            "qa_reports": [],
            "repair_attempts": 0,
        }
    )

    assert not any(
        report.rule_id == "undefined_names" and not report.passed
        for report in result["qa_reports"]
    )


@pytest.mark.asyncio
async def test_static_qa_node_uses_plugin_validators(monkeypatch):
    module_name = "test_nodes_qa_plugin_validator"

    def register(registry):
        registry.register_validator(NodePluginMarkerRule())

    _install_qa_plugin(module_name, register)
    monkeypatch.setattr(
        "langgraph_system_generator.qa.registry.settings.qa_repair_plugin_modules",
        [module_name],
    )

    result = await static_qa_node(
        {
            "generated_cells": _valid_generated_cells(
                execution_content='marker = "NODE_PLUGIN_BROKEN"\nprint(marker)'
            ),
            "qa_reports": [],
            "repair_attempts": 0,
        }
    )

    assert any(
        report.rule_id == "node_plugin_marker" and not report.passed
        for report in result["qa_reports"]
    )


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
        "langgraph_system_generator.generator.nodes.NotebookRepairAgent.repair_cells",
        lambda *_args, **_kwargs: RepairOutcome(
            status="applied",
            cells=updated_cells,
            qa_reports=updated_reports,
            attempted_fixes=["Applied deterministic fix."],
            persisted=True,
            message="Repair candidate passed validation and was accepted.",
            validation_summary={"accepted": True},
        ),
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

    managed_cells = [
        cell for cell in result["generated_cells"] if cell.section != "qa_repair_summary"
    ]
    summary_cell = next(
        cell for cell in result["generated_cells"] if cell.section == "qa_repair_summary"
    )

    assert managed_cells == updated_cells
    assert "QA and Repair Summary" in summary_cell.content
    assert "Applied a non-regressive deterministic repair." in summary_cell.content
    assert result["qa_reports"][0].check_name == "Fix"
    assert result["qa_reports"][0].stage == "static"
    assert result["qa_reports"][0].attempt == 2
    assert len(result["qa_history"]) == len(existing_history) + 1
    assert result["qa_history"][-1].check_name == "Repair Attempt"
    assert result["qa_history"][-1].rule_id == "repair_attempt"
    assert result["qa_history"][-1].attempt == 2
    assert result["qa_history"][-1].evidence["attempted_fixes"] == [
        "Applied deterministic fix."
    ]
    assert result["repair_attempts"] == 2
    assert result["qa_repair_feedback"].repair_attempts == 2
    assert result["qa_repair_feedback"].unrepaired_failures == []


@pytest.mark.asyncio
async def test_repair_node_failure_keeps_cells_and_appends_history(monkeypatch):
    initial_cells = [CellSpec(cell_type="markdown", content="Hi", metadata={})]
    updated_reports = [QAReport(check_name="Fix", passed=False, message="fail")]
    existing_history = [QAReport(check_name="Runtime Check", passed=False, message="boom")]

    monkeypatch.setattr(
        "langgraph_system_generator.generator.nodes.NotebookRepairAgent.repair_cells",
        lambda *_args, **_kwargs: RepairOutcome(
            status="rolled_back",
            cells=initial_cells,
            qa_reports=updated_reports,
            attempted_fixes=["Tried deterministic fix."],
            rollback_used=True,
            persisted=False,
            message="Repair candidate was rolled back because it regressed or did not improve validation.",
            next_steps=["Inspect the QA and Repair Summary cell before retrying."],
            validation_summary={"accepted": False},
        ),
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

    managed_cells = [
        cell for cell in result["generated_cells"] if cell.section != "qa_repair_summary"
    ]
    summary_cell = next(
        cell for cell in result["generated_cells"] if cell.section == "qa_repair_summary"
    )

    assert managed_cells == initial_cells
    assert "Rolled back the repair candidate" in summary_cell.content
    assert result["qa_reports"][0].check_name == "Fix"
    assert result["qa_reports"][0].stage == "static"
    assert result["qa_reports"][0].attempt == 4
    assert len(result["qa_history"]) == len(existing_history) + 1
    assert result["qa_history"][-1].passed is False
    assert result["qa_history"][-1].attempt == 4
    assert result["repair_attempts"] == 4
    assert result["qa_repair_feedback"].repair_attempts == 4
    assert result["qa_repair_feedback"].rollback_used is True
    assert "rolled back after validation" in result["qa_repair_feedback"].warnings[-1]


@pytest.mark.asyncio
async def test_repair_node_uses_plugin_repair_routines(monkeypatch):
    module_name = "test_nodes_qa_plugin_repair"

    def repair_marker(_agent, notebook, _report):
        fixes = []
        for cell in notebook.cells:
            if cell.cell_type != "code":
                continue
            source = str(cell.source or "")
            updated = source.replace("NODE_PLUGIN_BROKEN", "NODE_PLUGIN_REPAIRED")
            if updated != source:
                cell.source = updated
                fixes.append("Repaired node plugin marker.")
        return fixes

    def register(registry):
        registry.register_validator(NodePluginMarkerRule())
        registry.register_repair_routine(
            RepairRoutineRegistration(
                routine_id="node_plugin_marker_repair",
                handled_rule_ids=("node_plugin_marker",),
                handler=repair_marker,
            )
        )

    _install_qa_plugin(module_name, register)
    monkeypatch.setattr(
        "langgraph_system_generator.qa.registry.settings.qa_repair_plugin_modules",
        [module_name],
    )
    cells = _valid_generated_cells(
        execution_content='marker = "NODE_PLUGIN_BROKEN"\nprint(marker)'
    )
    report = QAReport(
        check_name="Node Plugin Marker",
        passed=False,
        message="Node plugin marker needs repair.",
        rule_id="node_plugin_marker",
        severity="error",
        category="custom",
        repairable=True,
    )

    result = await repair_node(
        {
            "generated_cells": cells,
            "qa_reports": [report],
            "qa_history": [],
            "repair_attempts": 0,
        }
    )

    code = "\n".join(
        cell.content
        for cell in result["generated_cells"]
        if cell.cell_type == "code"
    )
    assert "NODE_PLUGIN_BROKEN" not in code
    assert "NODE_PLUGIN_REPAIRED" in code
    assert result["qa_history"][-1].evidence["attempted_fixes"] == [
        "Repaired node plugin marker."
    ]
    assert result["qa_repair_feedback"].unrepaired_failures == []


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
        "generation_context_pack": GenerationContextPack(
            notebook_contract={"compiled_graph_variable": "graph"},
            qa_gates=["invocation_config"],
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
    assert manifest["generation_context_pack"]["notebook_contract"][
        "compiled_graph_variable"
    ] == "graph"
    assert "invocation_config" in manifest["generation_context_pack"]["qa_gates"]
    assert manifest["notebook_composition_feedback"]["fallback_used"] is True
    assert "requests" in manifest["notebook_dependency_plan"]["packages"]
    assert manifest["qa_repair_feedback"]["repair_attempts"] == 1
    assert result["generation_complete"] is True


@pytest.mark.asyncio
async def test_package_outputs_node_includes_qa_reports_and_summary():
    report = QAReport(
        check_name="Undefined Names",
        passed=False,
        message="Define or import 'app' before it is used.",
        rule_id="undefined_names",
        severity="warning",
        category="symbols",
        repairable=True,
        suggestions=["Check graph object naming."],
        stage="static",
        attempt=0,
    )

    result = await package_outputs_node(
        {
            "notebook_plan": "Plan",
            "generated_cells": [CellSpec(cell_type="markdown", content="Hi", metadata={})],
            "constraints": [Constraint(type="goal", value="Test", priority=1)],
            "selected_patterns": {"primary": "router"},
            "qa_reports": [report],
            "qa_repair_feedback": QARepairFeedback(
                warnings=[
                    "Non-blocking QA advisories were recorded; artifacts remain usable."
                ],
                next_steps=["Check graph object naming."],
            ),
        }
    )

    manifest = result["artifacts_manifest"]
    assert manifest["qa_reports"][0]["rule_id"] == "undefined_names"
    assert manifest["qa_summary"]["status"] == "advisories"
    assert manifest["qa_summary"]["artifacts_usable"] is True
    assert manifest["qa_summary"]["counts"]["non_blocking"] == 1
    assert manifest["qa_summary"]["findings"][0]["stage"] == "static"
    assert result["qa_summary"] == manifest["qa_summary"]
