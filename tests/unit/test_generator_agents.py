"""Tests for generator agents fallback behavior."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langgraph_system_generator.generator.agents import (
    architecture_selector,
    graph_designer,
    notebook_composer,
    qa_repair_agent,
    requirements_analyst,
    toolchain_engineer,
)
from langgraph_system_generator.generator.architecture_registry import (
    ArchitectureRegistration,
    get_default_architecture_registry,
)
from langgraph_system_generator.generator.graph_design_registry import (
    build_graph_exports,
    GraphDesignRegistration,
    GraphDesignRegistry,
    get_graph_design_registry,
    normalize_graph_design,
    validate_graph_design,
)
from langgraph_system_generator.generator import tool_registry as tool_registry_module
from langgraph_system_generator.generator import tool_dependency_utils
from langgraph_system_generator.generator.tool_registry import (
    ToolRegistration,
    ToolRegistry,
    get_tool_registry,
)
from langgraph_system_generator.qa.repair import RepairOutcome
from langgraph_system_generator.generator.state import (
    ArchitectureSelectionResult,
    CellSpec,
    Constraint,
    DocSnippet,
    GraphConditionalEdgeSpec,
    GraphDesignResult,
    GraphEdgeSpec,
    GraphNodeSpec,
    QAReport,
    ToolSpec,
)
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.config import ModelConfig


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


def make_capturing_llm(captured_kwargs: dict):
    """Create a ChatOpenAI stub that records constructor kwargs."""

    class CapturingLLM:
        def __init__(self, *_args, **kwargs):
            captured_kwargs.update(kwargs)

        async def ainvoke(self, _messages):
            return DummyResponse("[]")

    return CapturingLLM


def make_recording_llm(content: str, captured_messages: list):
    """Create a ChatOpenAI stub that records prompt messages."""

    class RecordingLLM:
        def __init__(self, *_args, **_kwargs):
            self._content = content

        async def ainvoke(self, messages):
            captured_messages.append(messages)
            return DummyResponse(self._content)

    return RecordingLLM


class StubDocsRetriever:
    """Simple docs retriever stub that records raw query usage."""

    def __init__(self, query_results: dict[str, list[dict]]):
        self.query_results = query_results
        self.queries: list[tuple[str, int]] = []

    def retrieve(self, query: str, k: int = 5):
        self.queries.append((query, k))
        return list(self.query_results.get(query, []))


def test_architecture_registry_includes_builtin_architectures():
    """Built-in architecture support should come from the shared registry."""

    registry = get_default_architecture_registry()

    assert set(registry.supported_architecture_types()) == {
        "router",
        "subagents",
        "hybrid",
        "autoagent",
    }

    hybrid = registry.get("hybrid")
    assert hybrid.default_secondary_patterns == ["router", "subagents"]
    assert hybrid.deterministic is True


@pytest.mark.asyncio
async def test_qa_repair_agent_validate_uses_shared_notebook_validator(monkeypatch):
    monkeypatch.setattr(
        qa_repair_agent,
        "ChatOpenAI",
        make_stub_llm("[]"),
    )

    agent = qa_repair_agent.QARepairAgent()
    reports = await agent.validate(
        [
            CellSpec(cell_type="markdown", content="## Graph", metadata={"section": "graph"}),
            CellSpec(
                cell_type="code",
                content="graph_hint = 'StateGraph'\nprint(graph_hint)",
                metadata={"section": "graph"},
            ),
        ]
    )

    graph_report = next(report for report in reports if report.check_name == "Graph Compilation")

    assert graph_report.rule_id == "graph_structure"
    assert graph_report.passed is False


@pytest.mark.asyncio
async def test_qa_repair_agent_repair_delegates_to_shared_engine(monkeypatch):
    monkeypatch.setattr(
        qa_repair_agent,
        "ChatOpenAI",
        make_stub_llm("[]"),
    )
    repaired_cells = [CellSpec(cell_type="markdown", content="Updated", metadata={})]

    monkeypatch.setattr(
        "langgraph_system_generator.generator.agents.qa_repair_agent.NotebookRepairAgent.repair_cells",
        lambda *_args, **_kwargs: RepairOutcome(
            status="applied",
            cells=repaired_cells,
            qa_reports=[],
            attempted_fixes=["Applied deterministic fix."],
            persisted=True,
            message="Repair candidate passed validation and was accepted.",
            validation_summary={"accepted": True},
        ),
    )

    agent = qa_repair_agent.QARepairAgent()
    result = await agent.repair(
        [CellSpec(cell_type="markdown", content="Original", metadata={})],
        [QAReport(check_name="Undefined Names", passed=False, message="boom")],
    )

    assert result == repaired_cells


def test_architecture_registry_preserves_zero_docs_weight_and_filters_unknown_patterns():
    """Registry normalization should preserve explicit zero weights and drop unknown patterns."""

    registry = get_default_architecture_registry().clone()
    registry.register(
        ArchitectureRegistration(
            architecture_id="custom_router",
            selector_prompt_description="Custom router variant.",
            docs_queries=["custom router docs"],
            docs_weight=0.0,
        )
    )

    assert registry.get("custom_router").docs_weight == 0.0
    primary, secondary = registry.normalize_patterns(
        "hybrid",
        secondary_patterns=["router", "unknown", "subagents", "router"],
    )
    assert primary == "hybrid"
    assert secondary == ["router", "subagents"]


@pytest.mark.asyncio
async def test_requirements_analyst_parsing(monkeypatch):
    """RequirementsAnalyst returns structured constraints and feedback."""
    payload = """
    {
      "constraints": [
        {
          "type": "goal",
          "value": "from-json",
          "priority": 5,
          "confidence": 0.92,
          "explanation": "Prompt clearly asks for this deliverable."
        },
        {
          "type": "environment",
          "value": "Run in Colab",
          "priority": 3,
          "confidence": 0.61,
          "explanation": "The prompt references notebook execution."
        }
      ],
      "feedback": {
        "fallback_used": false,
        "fallback_reason": null,
        "missing_inputs": [],
        "conflicts": [],
        "suggestions": [],
        "available_constraint_types": ["goal", "environment"]
      }
    }
    """
    monkeypatch.setattr(
        requirements_analyst,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    analyst = requirements_analyst.RequirementsAnalyst()
    analysis = await analyst.analyze("x")
    assert analysis.constraints[0].value == "from-json"
    assert analysis.constraints[0].confidence == pytest.approx(0.92)
    assert analysis.constraints[0].explanation == "Prompt clearly asks for this deliverable."
    assert analysis.feedback.fallback_used is False
    assert "goal" in analysis.feedback.available_constraint_types
    assert "environment" in analysis.feedback.available_constraint_types


@pytest.mark.asyncio
async def test_requirements_analyst_fallback_truncates_prompt_on_bad_json(monkeypatch):
    """Malformed model output should produce fallback constraints plus structured feedback."""
    long_prompt = "Build a workflow " + ("with a long prompt " * 15)
    assert len(long_prompt) > 200

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock()
    mock_llm.ainvoke.return_value.content = "not-json"

    with patch(
        "langgraph_system_generator.generator.agents.requirements_analyst.ChatOpenAI",
        return_value=mock_llm,
    ):
        analyst = requirements_analyst.RequirementsAnalyst(model="test-model")
        analysis = await analyst.analyze(long_prompt)

    assert len(analysis.constraints) == 1
    constraint = analysis.constraints[0]
    assert constraint.type == "goal"
    assert constraint.priority == 5
    assert constraint.value == long_prompt[:200]
    assert len(constraint.value) == 200
    assert analysis.feedback.fallback_used is True
    assert analysis.feedback.fallback_reason
    assert {"runtime", "environment"}.issubset(set(analysis.feedback.missing_inputs))
    assert analysis.feedback.suggestions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "reason_fragment"),
    [
        (
            """
            {
              "constraints": [
                {"value": "Build an agent notebook", "priority": 5}
              ]
            }
            """,
            "must include a non-empty type",
        ),
        (
            """
            {
              "constraints": [
                {"type": "architecture", "value": "router", "priority": 4}
              ]
            }
            """,
            "Unsupported constraint type",
        ),
    ],
)
async def test_requirements_analyst_falls_back_for_invalid_constraint_types(
    monkeypatch, payload, reason_fragment
):
    """Invalid or unsupported constraint types should trigger the fallback path."""

    monkeypatch.setattr(
        requirements_analyst,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    analyst = requirements_analyst.RequirementsAnalyst()
    analysis = await analyst.analyze("Build an agent notebook")

    assert analysis.feedback.fallback_used is True
    assert reason_fragment in (analysis.feedback.fallback_reason or "")
    assert len(analysis.constraints) == 1
    assert analysis.constraints[0].type == "goal"


@pytest.mark.asyncio
async def test_requirements_analyst_detects_conflicts_and_missing_inputs(monkeypatch):
    """Conflicting duplicates and missing core inputs should be surfaced in feedback."""
    payload = """
    {
      "constraints": [
        {"type": "goal", "value": "Build an agent notebook", "priority": 5},
        {"type": "runtime", "value": "Use gpt-5-mini", "priority": 4},
        {"type": "runtime", "value": "Use claude-3", "priority": 4}
      ]
    }
    """

    monkeypatch.setattr(
        requirements_analyst,
        "ChatOpenAI",
        make_stub_llm(payload),
    )

    analyst = requirements_analyst.RequirementsAnalyst()
    analysis = await analyst.analyze("Build an agent notebook with conflicting model instructions")

    assert analysis.feedback.fallback_used is False
    assert "environment" in analysis.feedback.missing_inputs
    assert analysis.feedback.conflicts
    assert any("runtime" in conflict.lower() for conflict in analysis.feedback.conflicts)
    assert analysis.feedback.suggestions


@pytest.mark.asyncio
async def test_requirements_analyst_uses_configured_constraint_type_registry(monkeypatch):
    """Configured extra requirement types should appear in the prompt registry and feedback."""
    captured_messages = []
    monkeypatch.setattr(
        requirements_analyst,
        "settings",
        requirements_analyst.settings.model_copy(
            update={
                "requirements_constraint_types": [
                    "Regulatory",
                    " regulatory ",
                    "custom type",
                ]
            }
        ),
    )
    monkeypatch.setattr(
        requirements_analyst,
        "ChatOpenAI",
        make_recording_llm(
            """
            {
              "constraints": [
                {
                  "type": "regulatory",
                  "value": "Must follow SOC 2 controls",
                  "priority": 4,
                  "confidence": 0.8,
                  "explanation": "The prompt explicitly names compliance."
                }
              ]
            }
            """,
            captured_messages,
        ),
    )

    analyst = requirements_analyst.RequirementsAnalyst()
    analysis = await analyst.analyze("Build a SOC 2 compliant workflow")

    assert analysis.constraints[0].type == "regulatory"
    assert "regulatory" in analysis.feedback.available_constraint_types
    assert "custom_type" in analysis.feedback.available_constraint_types
    assert analysis.feedback.available_constraint_types.count("regulatory") == 1
    assert "regulatory" in captured_messages[0][0].content
    assert "custom_type" in captured_messages[0][0].content


@pytest.mark.asyncio
async def test_architecture_selector_parsing(monkeypatch):
    """ArchitectureSelector returns typed results with structured feedback."""
    payload = """
    {
      "architecture_type": "subagents",
      "patterns": {"primary": "subagents", "secondary": ["router"]},
      "justification": "Subagents fit specialized worker contexts better than a single router.",
      "feedback": {
        "confidence": 0.82,
        "alternatives": [
          {
            "architecture_type": "router",
            "score": 0.47,
            "rationale": "Simpler, but weaker for isolated specialist contexts."
          }
        ],
        "tradeoffs": [
          "Higher coordination overhead than a single router."
        ]
      }
    }
    """
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    selector = architecture_selector.ArchitectureSelector()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    result = await selector.select_architecture(constraints, [])
    assert isinstance(result, ArchitectureSelectionResult)
    assert result.architecture_type == "subagents"
    assert result.patterns.primary == "subagents"
    assert result.patterns.secondary == ["router"]
    assert result.feedback.confidence == pytest.approx(0.82)
    assert result.feedback.alternatives[0].architecture_type == "router"
    assert result.feedback.tradeoffs
    assert result.feedback.fallback_used is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "reason_fragment"),
    [
        (
            '{"architecture_type":"swarm","patterns":{"primary":"swarm","secondary":[]},"justification":"x"}',
            "Unsupported architecture_type",
        ),
        (
            '{"architecture_type":"router","patterns":"router","justification":"x"}',
            "malformed patterns",
        ),
        (
            '{"architecture_type":"router","patterns":{"primary":"router","secondary":[]},"justification":"  "}',
            "non-empty justification",
        ),
    ],
)
async def test_architecture_selector_falls_back_on_invalid_payload(
    payload, reason_fragment, monkeypatch
):
    """ArchitectureSelector should surface fallback feedback for invalid model payloads."""
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    selector = architecture_selector.ArchitectureSelector()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    result = await selector.select_architecture(constraints, [])
    assert result.architecture_type == "router"
    assert result.patterns.primary == "router"
    assert result.feedback.fallback_used is True
    assert result.feedback.fallback_reason
    assert any(reason_fragment in error for error in result.feedback.validation_errors)


@pytest.mark.asyncio
async def test_architecture_selector_normalizes_pattern_primary(monkeypatch):
    """ArchitectureSelector should normalize the primary pattern to match architecture_type."""
    payload = """
    {
      "architecture_type": "autoagent",
      "patterns": {"primary": "router", "secondary": ["subagents"]},
      "justification": "AutoAgent best fits the planner/executor/critic loop.",
      "feedback": {
        "confidence": 0.73
      }
    }
    """
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    selector = architecture_selector.ArchitectureSelector()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    result = await selector.select_architecture(constraints, [])
    assert result.architecture_type == "autoagent"
    assert result.patterns.primary == "autoagent"
    assert any(
        "primary pattern did not match architecture_type" in error
        for error in result.feedback.validation_errors
    )


@pytest.mark.asyncio
async def test_architecture_selector_uses_registry_weighted_docs_and_limit(monkeypatch):
    """ArchitectureSelector should use registry-driven queries, weights, dedupe, and cap."""
    captured_messages = []
    retriever = StubDocsRetriever(
        {
            "Custom router override": [
                {
                    "content": "Router overview from override docs.",
                    "source": "shared.md",
                    "heading": "Overview",
                    "relevance_score": 0.7,
                }
            ],
            "Weighted subagents doc": [
                {
                    "content": "Subagent team guidance should win the dedupe race.",
                    "source": "shared.md",
                    "heading": "Overview",
                    "relevance_score": 0.8,
                },
                {
                    "content": "Worker-team coordination details.",
                    "source": "subagents.md",
                    "heading": "Team",
                    "relevance_score": 0.4,
                },
            ],
            "Light autoagent doc": [
                {
                    "content": "AutoAgent notes.",
                    "source": "autoagent.md",
                    "heading": "Planner",
                    "relevance_score": 0.95,
                }
            ],
            "Hybrid routing doc": [
                {
                    "content": "Hybrid router + supervisor guidance.",
                    "source": "hybrid.md",
                    "heading": "Composition",
                    "relevance_score": 0.2,
                }
            ],
        }
    )
    monkeypatch.setattr(
        architecture_selector,
        "settings",
        architecture_selector.settings.model_copy(
            update={
                "architecture_pattern_doc_queries": {
                    "router": ["Custom router override"],
                    "subagents": ["Weighted subagents doc"],
                    "autoagent": ["Light autoagent doc"],
                    "hybrid": ["Hybrid routing doc"],
                },
                "architecture_pattern_doc_weights": {
                    "router": 1.0,
                    "subagents": 3.0,
                    "autoagent": 0.1,
                    "hybrid": 0.5,
                },
                "architecture_prompt_doc_limit": 2,
            }
        ),
    )
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_recording_llm(
            """
            {
              "architecture_type": "router",
              "patterns": {"primary": "router", "secondary": []},
              "justification": "A router is sufficient here."
            }
            """,
            captured_messages,
        ),
    )

    selector = architecture_selector.ArchitectureSelector(docs_retriever=retriever)
    result = await selector.select_architecture(
        [Constraint(type="goal", value="Route requests", priority=5)],
        [],
    )

    assert {query for query, _k in retriever.queries} >= {
        "Custom router override",
        "Weighted subagents doc",
        "Light autoagent doc",
        "Hybrid routing doc",
    }
    assert {k for _, k in retriever.queries} == {2}
    assert result.feedback.docs_considered == [
        "shared.md#Overview",
        "subagents.md#Team",
    ]
    assert "Subagent team guidance should win the dedupe race." in captured_messages[0][1].content
    assert "AutoAgent notes." not in captured_messages[0][1].content


@pytest.mark.asyncio
async def test_architecture_selector_uses_docs_context_when_registry_retrieval_is_empty(
    monkeypatch,
):
    """Selector should fall back to the existing docs_context when weighted retrieval is empty."""

    captured_messages = []
    retriever = StubDocsRetriever({})
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_recording_llm(
            """
            {
              "architecture_type": "router",
              "patterns": {"primary": "router", "secondary": []},
              "justification": "Router is enough for this task."
            }
            """,
            captured_messages,
        ),
    )

    selector = architecture_selector.ArchitectureSelector(docs_retriever=retriever)
    docs_context = [
        DocSnippet(
            content="Existing RAG docs should still inform the selector prompt.",
            source="rag.md",
            heading="Useful",
            relevance_score=0.7,
        )
    ]
    result = await selector.select_architecture(
        [Constraint(type="goal", value="Route requests reliably", priority=5)],
        docs_context,
    )

    assert result.feedback.docs_considered == ["rag.md#Useful"]
    assert "Existing RAG docs should still inform the selector prompt." in captured_messages[0][1].content


@pytest.mark.asyncio
async def test_architecture_selector_dedupes_blank_metadata_by_content(monkeypatch):
    """Distinct blank-metadata snippets should survive prompt-doc dedupe."""

    captured_messages = []
    retriever = StubDocsRetriever(
        {
            "Blank metadata docs": [
                {
                    "content": "First blank metadata doc",
                    "source": "",
                    "heading": "",
                    "relevance_score": 0.8,
                },
                {
                    "content": "Second blank metadata doc",
                    "source": "",
                    "heading": "",
                    "relevance_score": 0.7,
                },
            ]
        }
    )
    monkeypatch.setattr(
        architecture_selector,
        "settings",
        architecture_selector.settings.model_copy(
            update={
                "architecture_pattern_doc_queries": {
                    "router": ["Blank metadata docs"],
                    "subagents": [],
                    "autoagent": [],
                    "hybrid": [],
                },
                "architecture_prompt_doc_limit": 5,
            }
        ),
    )
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_recording_llm(
            """
            {
              "architecture_type": "router",
              "patterns": {"primary": "router", "secondary": []},
              "justification": "Router remains the best fit."
            }
            """,
            captured_messages,
        ),
    )

    selector = architecture_selector.ArchitectureSelector(docs_retriever=retriever)
    result = await selector.select_architecture(
        [Constraint(type="goal", value="Handle metadata-poor docs", priority=5)],
        [],
    )

    assert result.feedback.docs_considered == [
        "First blank metadata doc",
        "Second blank metadata doc",
    ]
    assert "First blank metadata doc" in captured_messages[0][1].content
    assert "Second blank metadata doc" in captured_messages[0][1].content


@pytest.mark.asyncio
async def test_architecture_selector_uses_programmatically_registered_metadata(monkeypatch):
    """Programmatic registry entries should participate in selector prompt/doc metadata."""
    captured_messages = []
    retriever = StubDocsRetriever(
        {
            "LangGraph research team orchestration": [
                {
                    "content": "Research team docs.",
                    "source": "custom.md",
                    "heading": "Research Team",
                    "relevance_score": 0.6,
                }
            ]
        }
    )
    registry = get_default_architecture_registry().clone()
    registry.register(
        ArchitectureRegistration(
            architecture_id="research_team",
            selector_prompt_description="Research team architecture for discovery-heavy workflows.",
            default_secondary_patterns=["router"],
            docs_queries=["LangGraph research team orchestration"],
            docs_weight=1.2,
            deterministic=False,
        )
    )
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_recording_llm(
            """
            {
              "architecture_type": "router",
              "patterns": {"primary": "router", "secondary": []},
              "justification": "Router remains the best fit."
            }
            """,
            captured_messages,
        ),
    )

    selector = architecture_selector.ArchitectureSelector(
        docs_retriever=retriever,
        architecture_registry=registry,
    )
    await selector.select_architecture(
        [Constraint(type="goal", value="Investigate research-heavy tasks", priority=5)],
        [],
    )

    assert any(query == "LangGraph research team orchestration" for query, _k in retriever.queries)
    assert "research_team" in captured_messages[0][0].content
    assert "Research team architecture for discovery-heavy workflows." in captured_messages[0][0].content


@pytest.mark.asyncio
async def test_architecture_selector_normalizes_hybrid_secondary_patterns(monkeypatch):
    """Hybrid selections should normalize to router plus subagents secondary patterns."""
    payload = """
    {
      "architecture_type": "hybrid",
      "patterns": {"primary": "hybrid", "secondary": ["router"]},
      "justification": "Hybrid mixes direct routing with a supervisor team.",
      "feedback": {
        "confidence": 0.67
      }
    }
    """
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    selector = architecture_selector.ArchitectureSelector()
    result = await selector.select_architecture(
        [Constraint(type="goal", value="Mix direct specialists with a team path", priority=5)],
        [],
    )

    assert result.architecture_type == "hybrid"
    assert result.patterns.primary == "hybrid"
    assert result.patterns.secondary == ["router", "subagents"]


@pytest.mark.asyncio
@pytest.mark.parametrize("arch_type", ["router", "subagents"])
async def test_graph_designer_fallback(arch_type, monkeypatch):
    """GraphDesigner should return typed fallback output when parsing fails."""
    monkeypatch.setattr(
        graph_designer,
        "ChatOpenAI",
        make_stub_llm("invalid"),
    )
    designer = graph_designer.GraphDesigner()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    architecture = {"architecture_type": arch_type, "justification": "x"}
    expected = designer._fallback_design(arch_type)
    result = await designer.design_workflow(architecture, constraints)
    assert isinstance(result, GraphDesignResult)
    assert result.feedback.fallback_used is True
    assert result.to_workflow_design_payload()["entry_point"] == expected["entry_point"]
    assert result.to_workflow_design_payload()["nodes"] == expected["nodes"]


@pytest.mark.asyncio
async def test_graph_designer_returns_typed_result_with_exports(monkeypatch):
    """GraphDesigner should normalize a valid design into typed output plus exports."""

    payload = """
    {
      "state_schema": {
        "messages": "Conversation state",
        "route": "Selected route"
      },
      "nodes": [
        {"name": "router", "purpose": "Route requests"},
        {"name": "search", "purpose": "Search documents"}
      ],
      "edges": [],
      "conditional_edges": [
        {
          "from": "router",
          "condition": "Dispatch by route",
          "branches": {"search": "search", "END": "END"}
        }
      ],
      "entry_point": "router",
      "checkpointing": false
    }
    """
    monkeypatch.setattr(graph_designer, "ChatOpenAI", make_stub_llm(payload))

    designer = graph_designer.GraphDesigner()
    result = await designer.design_workflow(
        {
            "architecture_type": "router",
            "justification": "Routing is sufficient.",
            "selected_patterns": {"primary": "router", "secondary": []},
        },
        [Constraint(type="goal", value="Build a router workflow", priority=5)],
    )

    assert isinstance(result, GraphDesignResult)
    assert result.architecture_type == "router"
    assert result.nodes[0].name == "router"
    assert result.feedback.fallback_used is False
    assert "flowchart TD" in result.exports.mermaid
    assert result.exports.schema["entry_point"] == "router"
    assert result.exports.schema["terminal_nodes"]


@pytest.mark.asyncio
async def test_graph_designer_falls_back_for_invalid_live_graph(monkeypatch):
    """Invalid live graph payloads should trigger validated fallback feedback."""

    payload = """
    {
      "state_schema": {"messages": "Conversation state"},
      "nodes": [
        {"name": "router", "purpose": "Route requests"},
        {"name": "router", "purpose": "Duplicate node"},
        {"name": "orphan", "purpose": "Never reached"}
      ],
      "edges": [
        {"from": "router", "to": "missing_target"}
      ],
      "conditional_edges": [],
      "entry_point": "router",
      "checkpointing": false
    }
    """
    monkeypatch.setattr(graph_designer, "ChatOpenAI", make_stub_llm(payload))

    designer = graph_designer.GraphDesigner()
    result = await designer.design_workflow(
        {
            "architecture_type": "router",
            "justification": "Routing is sufficient.",
            "selected_patterns": {"primary": "router", "secondary": []},
        },
        [Constraint(type="goal", value="Build a router workflow", priority=5)],
    )

    assert isinstance(result, GraphDesignResult)
    assert result.feedback.fallback_used is True
    assert result.feedback.fallback_reason
    assert any("duplicate" in message.lower() for message in result.feedback.validation_errors)
    assert any("missing_target" in message for message in result.feedback.validation_errors)
    assert result.entry_point == "router"
    assert "flowchart TD" in result.exports.mermaid


@pytest.mark.asyncio
async def test_graph_designer_raises_when_fallback_is_invalid(monkeypatch):
    """If fallback normalization still fails, GraphDesigner should raise a structured error."""

    monkeypatch.setattr(graph_designer, "ChatOpenAI", make_stub_llm("not-json"))

    registry = GraphDesignRegistry()
    registry.register(
        GraphDesignRegistration(
            architecture_id="broken",
            supported_entry_shapes=["broken"],
            supported_exit_shapes=["broken"],
            cycles_allowed=False,
            fallback_builder=lambda *_args, **_kwargs: {
                "state_schema": {},
                "nodes": [],
                "edges": [],
                "conditional_edges": [],
                "entry_point": "",
                "checkpointing": False,
            },
            normalization_hook=None,
            validation_hook=None,
            export_label_defaults={"title": "Broken"},
            composition_strategy="broken",
        )
    )

    designer = graph_designer.GraphDesigner(registry=registry)
    with pytest.raises(GenerationError, match="fallback"):
        await designer.design_workflow(
            {
                "architecture_type": "broken",
                "justification": "Broken architecture for validation testing.",
                "selected_patterns": {"primary": "broken", "secondary": []},
            },
            [Constraint(type="goal", value="Break the graph designer", priority=5)],
        )


def test_graph_design_validation_detects_cycles_and_unreachable_nodes():
    """Graph validation should detect structural errors before export or use."""

    result = GraphDesignResult(
        architecture_type="router",
        state_schema={"messages": "Conversation state"},
        nodes=[
            GraphNodeSpec(name="router", purpose="Route requests"),
            GraphNodeSpec(name="search", purpose="Search documents"),
            GraphNodeSpec(name="dead_end", purpose="Never reached"),
        ],
        edges=[
            GraphEdgeSpec.model_validate({"from": "search", "to": "router"}),
        ],
        conditional_edges=[
            GraphConditionalEdgeSpec.model_validate(
                {
                    "from": "router",
                    "condition": "Dispatch by route",
                    "branches": {"search": "search"},
                }
            )
        ],
        entry_point="router",
        checkpointing=False,
    )

    issues = validate_graph_design(result, get_graph_design_registry().get("router"))
    issue_codes = {issue.code for issue in issues}

    assert "cycle_detected" in issue_codes
    assert "unreachable_node" in issue_codes
    assert "missing_terminal_path" in issue_codes


def test_graph_design_registry_loads_plugin_modules(monkeypatch):
    """Graph design plugin modules should be able to register new architectures."""

    class FakePluginModule:
        @staticmethod
        def register_graph_designers(registry):
            registry.register(
                GraphDesignRegistration(
                    architecture_id="plugin_router",
                    supported_entry_shapes=["router"],
                    supported_exit_shapes=["terminal"],
                    cycles_allowed=False,
                    fallback_builder=lambda *_args, **_kwargs: {
                        "state_schema": {"messages": "Conversation state"},
                        "nodes": [
                            {"name": "router", "purpose": "Route requests"},
                            {"name": "finish", "purpose": "Finish requests"},
                        ],
                        "edges": [{"from": "router", "to": "finish"}],
                        "conditional_edges": [],
                        "entry_point": "router",
                        "checkpointing": False,
                    },
                    normalization_hook=None,
                    validation_hook=None,
                    export_label_defaults={"title": "Plugin Router"},
                    composition_strategy="plugin",
                )
            )

    monkeypatch.setattr(
        graph_designer.importlib,
        "import_module",
        lambda name: FakePluginModule if name == "fake_graph_plugin" else None,
    )

    registry = get_graph_design_registry(plugin_modules=("fake_graph_plugin",))

    assert "plugin_router" in registry.supported_architecture_types()
    assert registry.get("plugin_router").composition_strategy == "plugin"


def test_graph_design_registry_surfaces_plugin_import_failures(monkeypatch):
    """Plugin import failures should name the module and the original import error."""

    def broken_import(name: str):
        if name == "broken_graph_plugin":
            raise ModuleNotFoundError("No module named 'missing_graph_extension'")
        raise AssertionError(f"Unexpected import request: {name}")

    monkeypatch.setattr(graph_designer.importlib, "import_module", broken_import)

    with pytest.raises(
        ValueError,
        match="Failed to import graph design plugin module 'broken_graph_plugin'",
    ):
        get_graph_design_registry(plugin_modules=("broken_graph_plugin",))


def test_graph_designer_hybrid_fallback_contains_router_supervisor_and_team(monkeypatch):
    """Hybrid fallback should produce a real mixed routing/team workflow shape."""
    monkeypatch.setattr(
        graph_designer,
        "ChatOpenAI",
        make_stub_llm("invalid"),
    )
    designer = graph_designer.GraphDesigner()

    result = designer._fallback_design("hybrid")

    node_names = [node["name"] for node in result["nodes"]]
    assert node_names.count("router") == 1
    assert node_names.count("supervisor") == 1
    assert node_names.count("finish") == 1
    assert len([name for name in node_names if name.startswith("specialist_")]) >= 1
    assert len(
        [
            name
            for name in node_names
            if name not in {"router", "supervisor", "finish"}
            and not name.startswith("specialist_")
        ]
    ) >= 2
    router_edges = [edge for edge in result["conditional_edges"] if edge["from"] == "router"]
    supervisor_edges = [
        edge for edge in result["conditional_edges"] if edge["from"] == "supervisor"
    ]
    assert router_edges
    assert "team_path" in router_edges[0]["branches"]
    assert router_edges[0]["branches"]["team_path"] == "supervisor"
    assert supervisor_edges
    assert "FINISH" in supervisor_edges[0]["branches"]

    registration = get_graph_design_registry().get("hybrid")
    normalized = normalize_graph_design(result, "hybrid", registration)
    issues = validate_graph_design(normalized, registration)
    assert not [issue for issue in issues if issue.severity == "error"]


def test_graph_design_exports_escape_mermaid_labels():
    """Mermaid exports should escape labels that contain quotes, brackets, or newlines."""

    result = GraphDesignResult(
        architecture_type="router",
        state_schema={"messages": "Conversation state"},
        nodes=[
            GraphNodeSpec(
                name='router "alpha"',
                purpose="Route [requests]\ncarefully",
            ),
            GraphNodeSpec(name="finish", purpose="Finish the workflow"),
        ],
        edges=[],
        conditional_edges=[
            GraphConditionalEdgeSpec.model_validate(
                {
                    "from": 'router "alpha"',
                    "condition": "Dispatch by route",
                    "branches": {
                        'team "path"\n[1]': "finish",
                        "END": "END",
                    },
                }
            )
        ],
        entry_point='router "alpha"',
        checkpointing=False,
    )

    exports = build_graph_exports(result, get_graph_design_registry().get("router"))

    assert "&quot;" in exports.mermaid
    assert "&#91;" in exports.mermaid
    assert "&#93;" in exports.mermaid
    assert "<br/>" in exports.mermaid



@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_count", "expected_fallback"),
    [
        ('[{"name":"search","category":"search","purpose":"x","configuration":{}}]', 1, False),
        ("invalid", 0, True),
    ],
)
async def test_toolchain_engineer_parsing(
    payload,
    expected_count,
    expected_fallback,
    monkeypatch,
):
    """ToolchainEngineer normalizes valid payloads and surfaces parse fallback."""
    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    result = await engineer.plan_tools({"nodes": []}, constraints)
    assert len(result.tools) == expected_count
    assert result.feedback.fallback_used is expected_fallback


@pytest.mark.asyncio
async def test_toolchain_engineer_parse_failure_uses_heuristic_fallback_for_tool_nodes(
    monkeypatch,
):
    """Parse failures should infer conservative fallback tools from workflow nodes."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm("not-json"),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {
            "nodes": [
                {"name": "researcher", "purpose": "Search docs and gather references"},
                {"name": "validator", "purpose": "Validate the final schema"},
            ]
        },
        [Constraint(type="goal", value="Build agents", priority=5)],
    )

    assert result.feedback.fallback_used is True
    assert [tool.tool_id for tool in result.tools] == ["web_search", "schema_validator"]
    assert all(tool.status == "fallback" for tool in result.tools)


@pytest.mark.asyncio
async def test_toolchain_engineer_marks_imaginary_tools_unsupported(monkeypatch):
    """Unsupported tool suggestions should surface as warnings, not valid tools."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            '[{"name":"quantum_api","category":"api","purpose":"Call an imaginary endpoint","configuration":{}}]'
        ),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {"nodes": [{"name": "fetch_data", "purpose": "Fetch remote data"}]},
        [Constraint(type="goal", value="Fetch data", priority=5)],
    )

    assert result.feedback.fallback_used is True
    assert result.feedback.unresolved_tools == ["quantum_api"]
    assert result.tools[0].tool_id == "http_client"
    assert result.tools[0].status == "fallback"
    unsupported = [tool for tool in result.tools if tool.status == "unsupported"]
    assert len(unsupported) == 1
    assert unsupported[0].name == "quantum_api"


@pytest.mark.asyncio
async def test_toolchain_engineer_normalizes_alias_to_canonical_tool_id(monkeypatch):
    """Registry aliases should resolve to canonical tool ids."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            '[{"name":"search","category":"search","purpose":"Look up docs","configuration":{}}]'
        ),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {"nodes": [{"name": "research", "purpose": "Search docs"}]},
        [Constraint(type="goal", value="Research docs", priority=5)],
    )

    assert result.feedback.fallback_used is False
    assert result.tools == [
        ToolSpec(
            tool_id="web_search",
            name="search",
            category="search",
            purpose="Look up docs",
            configuration={"backend": "duckduckgo"},
            packages=["langchain-community"],
            provider_env_vars=[],
            status="ready",
            warnings=[],
        )
    ]


def test_tool_registry_replaces_stale_aliases_and_rejects_collisions():
    """Overridden registrations should drop stale aliases and block alias collisions."""

    registry = ToolRegistry(
        [
            ToolRegistration(
                tool_id="web_search",
                name="Web Search",
                description="Search public docs.",
                category="search",
                aliases=["search", "docs_search"],
            )
        ]
    )

    registry.register(
        ToolRegistration(
            tool_id="web_search",
            name="Web Search",
            description="Search public docs.",
            category="search",
            aliases=["web_lookup"],
        )
    )

    assert registry.resolve_tool_id("search") is None
    assert registry.resolve_tool_id("docs_search") is None
    assert registry.resolve_tool_id("web_lookup") == "web_search"

    with pytest.raises(ValueError, match="Alias 'web_lookup' is already registered"):
        registry.register(
            ToolRegistration(
                tool_id="file_reader",
                name="File Reader",
                description="Read local files.",
                category="file_io",
                aliases=["web_lookup"],
            )
        )


def test_tool_registry_uses_current_plugin_settings_for_cache_keys(monkeypatch):
    """Default registry loads should refresh when plugin-module settings change."""

    module_a_name = "tests.fake_tool_registry_plugin_a"
    module_b_name = "tests.fake_tool_registry_plugin_b"
    plugin_a = types.ModuleType(module_a_name)
    plugin_b = types.ModuleType(module_b_name)

    def register_toolchain_tools_a(registry):
        registry.register(
            ToolRegistration(
                tool_id="alpha_tool",
                name="Alpha Tool",
                description="Alpha plugin tool.",
                category="search",
                aliases=["alpha"],
            )
        )

    def register_toolchain_tools_b(registry):
        registry.register(
            ToolRegistration(
                tool_id="beta_tool",
                name="Beta Tool",
                description="Beta plugin tool.",
                category="validation",
                aliases=["beta"],
            )
        )

    plugin_a.register_toolchain_tools = register_toolchain_tools_a
    plugin_b.register_toolchain_tools = register_toolchain_tools_b
    monkeypatch.setitem(sys.modules, module_a_name, plugin_a)
    monkeypatch.setitem(sys.modules, module_b_name, plugin_b)

    tool_registry_module._get_tool_registry_cached.cache_clear()
    monkeypatch.setattr(
        tool_registry_module.settings,
        "toolchain_engineer_plugin_modules",
        [module_a_name],
    )
    registry_a = get_tool_registry()
    assert "alpha_tool" in registry_a.supported_tool_ids()
    assert "beta_tool" not in registry_a.supported_tool_ids()

    monkeypatch.setattr(
        tool_registry_module.settings,
        "toolchain_engineer_plugin_modules",
        [module_b_name],
    )
    registry_b = get_tool_registry()
    assert "beta_tool" in registry_b.supported_tool_ids()
    assert "alpha_tool" not in registry_b.supported_tool_ids()

    tool_registry_module._get_tool_registry_cached.cache_clear()


@pytest.mark.asyncio
async def test_toolchain_engineer_prompt_catalog_comes_from_registry(monkeypatch):
    """Planner prompt should be generated from the current registry catalog."""

    captured_messages: list = []
    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_recording_llm("[]", captured_messages),
    )
    registry = get_tool_registry().clone()
    registry.register(
        ToolRegistration(
            tool_id="plugin_tool",
            name="Plugin Tool",
            description="Custom plugin-only capability for specialized workflows",
            category="misc",
            aliases=["plugin_alias"],
        )
    )

    engineer = toolchain_engineer.ToolchainEngineer(registry=registry)
    await engineer.plan_tools({"nodes": []}, [])

    system_prompt = captured_messages[0][0].content
    assert "- plugin_tool: Custom plugin-only capability for specialized workflows." in system_prompt
    assert "- tool_id: Canonical tool identifier or supported alias" in system_prompt
    assert "- name: Human-readable display name for the tool" in system_prompt


@pytest.mark.asyncio
async def test_toolchain_engineer_preserves_display_name_when_tool_id_present(
    monkeypatch,
):
    """Display names should not be overwritten by canonical tool ids."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            '[{"tool_id":"web_search","name":"Web Search Tool","category":"search","purpose":"Look up docs","configuration":{}}]'
        ),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {"nodes": [{"name": "research", "purpose": "Search docs"}]},
        [Constraint(type="goal", value="Research docs", priority=5)],
    )

    assert result.tools[0].tool_id == "web_search"
    assert result.tools[0].name == "Web Search Tool"


@pytest.mark.asyncio
async def test_toolchain_engineer_blocks_network_tools_for_offline_constraints(
    monkeypatch,
):
    """Offline constraints should downgrade network-dependent tools to unsupported."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            """[
                {"tool_id":"web_search","name":"web_search","category":"search","purpose":"Look up docs","configuration":{}},
                {"tool_id":"file_reader","name":"file_reader","category":"file_io","purpose":"Read local files","configuration":{}},
                {"tool_id":"http_client","name":"http_client","category":"api","purpose":"Fetch remote APIs","configuration":{}}
            ]"""
        ),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {"nodes": [{"name": "research", "purpose": "Search docs and fetch APIs"}]},
        [Constraint(type="environment", value="Offline only, no network access", priority=5)],
    )

    statuses = {tool.tool_id: tool.status for tool in result.tools}
    assert statuses["web_search"] == "unsupported"
    assert statuses["http_client"] == "unsupported"
    assert statuses["file_reader"] == "ready"
    assert any("web_search" in note for note in result.feedback.environment_notes)
    assert any("http_client" in note for note in result.feedback.environment_notes)
    assert result.feedback.unresolved_tools == ["web_search", "http_client"]


@pytest.mark.asyncio
async def test_toolchain_engineer_ignores_offline_tokens_in_non_runtime_constraints(
    monkeypatch,
):
    """Only runtime/environment constraints should trigger environment filtering."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            '[{"tool_id":"web_search","name":"Web Docs Search","category":"search","purpose":"Look up docs","configuration":{}}]'
        ),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {"nodes": [{"name": "research", "purpose": "Search docs"}]},
        [Constraint(type="goal", value="Build an offline-first assistant", priority=5)],
    )

    assert result.tools[0].tool_id == "web_search"
    assert result.tools[0].status == "ready"
    assert result.feedback.environment_notes == []
    assert result.feedback.unresolved_tools == []


@pytest.mark.asyncio
async def test_toolchain_engineer_honors_plugin_environment_metadata(
    monkeypatch,
):
    """Plugin-registered tools should honor the same environment rules as built-ins."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            """[
                {"tool_id":"internal_api","name":"internal_api","category":"api","purpose":"Call internal APIs","configuration":{}},
                {"tool_id":"web_search","name":"web_search","category":"search","purpose":"Search public docs","configuration":{}}
            ]"""
        ),
    )
    registry = get_tool_registry().clone()
    registry.register(
        ToolRegistration(
            tool_id="internal_api",
            name="Internal API Client",
            description="Call internal-only APIs over the network.",
            category="api",
            aliases=["internal_http_client"],
            default_packages=["requests"],
            environment_compatibility={
                "requires_network": True,
                "public_web": False,
                "notebook_safe": True,
            },
        )
    )

    engineer = toolchain_engineer.ToolchainEngineer(registry=registry)
    result = await engineer.plan_tools(
        {"nodes": [{"name": "fetch", "purpose": "Call internal APIs and search docs"}]},
        [Constraint(type="environment", value="Firewalled internal only runtime", priority=5)],
    )

    statuses = {tool.tool_id: tool.status for tool in result.tools}
    assert statuses["internal_api"] == "ready"
    assert statuses["web_search"] == "unsupported"
    assert any("web_search" in note for note in result.feedback.environment_notes)
    assert "internal_api" not in result.feedback.unresolved_tools


@pytest.mark.asyncio
async def test_toolchain_engineer_blocks_non_notebook_safe_tools_for_jupyter(
    monkeypatch,
):
    """Explicit notebook runtimes should downgrade non-notebook-safe tools."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            """[
                {"tool_id":"shell_runner","name":"shell_runner","category":"code_execution","purpose":"Run shell commands","configuration":{}}
            ]"""
        ),
    )
    registry = get_tool_registry().clone()
    registry.register(
        ToolRegistration(
            tool_id="shell_runner",
            name="Shell Runner",
            description="Execute local shell commands.",
            category="code_execution",
            aliases=["shell"],
            environment_compatibility={
                "requires_network": False,
                "public_web": False,
                "notebook_safe": False,
            },
        )
    )

    engineer = toolchain_engineer.ToolchainEngineer(registry=registry)
    result = await engineer.plan_tools(
        {"nodes": [{"name": "executor", "purpose": "Run shell commands"}]},
        [Constraint(type="runtime", value="Run in Jupyter notebook", priority=5)],
    )

    assert result.tools[0].status == "unsupported"
    assert any("notebook-safe tools" in note for note in result.feedback.environment_notes)
    assert result.feedback.unresolved_tools == ["shell_runner"]


@pytest.mark.asyncio
async def test_toolchain_engineer_uses_heuristic_fallback_after_environment_filtering(
    monkeypatch,
):
    """Heuristic fallback should re-run if validation/environment filtering removes all usable tools."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            """[
                {"tool_id":"http_client","name":"HTTP Client","category":"api","purpose":"Call remote APIs","configuration":{}}
            ]"""
        ),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {
            "nodes": [
                {"name": "doc_reader", "purpose": "Read local PDF documents"},
                {"name": "api_fetcher", "purpose": "Fetch remote APIs"},
            ]
        },
        [Constraint(type="environment", value="Offline only", priority=5)],
    )

    statuses = {tool.tool_id: tool.status for tool in result.tools}
    assert result.feedback.fallback_used is True
    assert "file_reader" in statuses
    assert statuses["file_reader"] == "fallback"
    assert statuses["http_client"] == "unsupported"


@pytest.mark.asyncio
async def test_toolchain_engineer_deduplicates_identical_tool_suggestions(monkeypatch):
    """Repeated canonical-equivalent suggestions should collapse into one tool spec."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            """[
                {"tool_id":"web_search","name":"Web Search","category":"search","purpose":"Look up docs","configuration":{}},
                {"name":"search","category":"search","purpose":"Look up docs","configuration":{"backend":"duckduckgo"},"provider_env_vars":["SEARCH_API_KEY"]}
            ]"""
        ),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {"nodes": [{"name": "research", "purpose": "Search docs"}]},
        [Constraint(type="goal", value="Research docs", priority=5)],
    )

    assert len(result.tools) == 1
    assert result.tools[0].tool_id == "web_search"
    assert result.tools[0].provider_env_vars == ["SEARCH_API_KEY"]


@pytest.mark.asyncio
async def test_toolchain_engineer_keeps_conflicting_tool_configs_separate(
    monkeypatch,
):
    """Conflicting configurations should remain visible instead of being merged away."""

    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(
            """[
                {"tool_id":"file_reader","name":"File Reader","category":"file_io","purpose":"Read PDFs","configuration":{"mode":"text","packages":["pypdf"]}},
                {"tool_id":"file_reader","name":"File Reader","category":"file_io","purpose":"Read PDFs quickly","configuration":{"mode":"binary","packages":["pdfminer.six"]}}
            ]"""
        ),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    result = await engineer.plan_tools(
        {"nodes": [{"name": "reader", "purpose": "Read PDF documents"}]},
        [Constraint(type="goal", value="Read PDFs", priority=5)],
    )

    assert len(result.tools) == 2
    assert any(
        "multiple configurations" in message
        for message in result.feedback.dependency_conflicts
    )
    assert any("pdf_parser" in message for message in result.feedback.dependency_conflicts)


def test_package_import_probe_maps_non_module_distribution_names():
    """Shared dependency probes should use the actual import module names."""

    assert tool_dependency_utils.package_import_probe("pdfminer.six") == "pdfminer"
    assert tool_dependency_utils.package_import_probe("pymupdf") == "fitz"


def test_requirements_analyst_uses_request_scoped_model_config(monkeypatch):
    """RequirementsAnalyst should pass request-scoped model settings to ChatOpenAI."""
    captured_kwargs = {}

    monkeypatch.setattr(
        requirements_analyst,
        "ChatOpenAI",
        make_capturing_llm(captured_kwargs),
    )

    requirements_analyst.RequirementsAnalyst(
        model_config=ModelConfig(
            model="gpt-5.2",
            temperature=0.4,
            api_base="https://example.test/v1",
            max_tokens=2048,
        )
    )

    assert captured_kwargs == {
        "model": "gpt-5.2",
        "temperature": 0.4,
        "base_url": "https://example.test/v1",
        "max_tokens": 2048,
    }


def test_architecture_selector_uses_request_scoped_model_config(monkeypatch):
    """ArchitectureSelector should pass request-scoped model settings to ChatOpenAI."""
    captured_kwargs = {}

    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_capturing_llm(captured_kwargs),
    )

    architecture_selector.ArchitectureSelector(
        model_config=ModelConfig(model="gpt-5-mini", temperature=0.2, max_tokens=1024)
    )

    assert captured_kwargs == {
        "model": "gpt-5-mini",
        "temperature": 0.2,
        "max_tokens": 1024,
    }


@pytest.mark.parametrize(
    ("module", "agent_cls"),
    [
        (graph_designer, graph_designer.GraphDesigner),
        (toolchain_engineer, toolchain_engineer.ToolchainEngineer),
        (qa_repair_agent, qa_repair_agent.QARepairAgent),
        (notebook_composer, notebook_composer.NotebookComposer),
    ],
)
def test_other_agents_use_request_scoped_model_config(
    monkeypatch,
    module,
    agent_cls,
):
    """Shared ChatOpenAI construction should preserve request-scoped settings."""
    captured_kwargs = {}

    monkeypatch.setattr(
        module,
        "ChatOpenAI",
        make_capturing_llm(captured_kwargs),
    )

    agent_cls(
        model_config=ModelConfig(
            model="gpt-5.1",
            temperature=0.3,
            api_base="https://example.test/v1",
            max_tokens=512,
        )
    )

    assert captured_kwargs == {
        "model": "gpt-5.1",
        "temperature": 0.3,
        "base_url": "https://example.test/v1",
        "max_tokens": 512,
    }
