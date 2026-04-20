"""Tests for generator agents fallback behavior."""

from __future__ import annotations

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
from langgraph_system_generator.generator.state import (
    ArchitectureSelectionResult,
    Constraint,
)
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
    assert result.feedback.docs_considered == [
        "shared.md#Overview",
        "subagents.md#Team",
    ]
    assert "Subagent team guidance should win the dedupe race." in captured_messages[0][1].content
    assert "AutoAgent notes." not in captured_messages[0][1].content


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
    """GraphDesigner falls back to the correct design when parsing fails."""
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
    assert result == expected


def test_graph_designer_hybrid_fallback_contains_router_supervisor_and_team():
    """Hybrid fallback should produce a real mixed routing/team workflow shape."""
    designer = graph_designer.GraphDesigner()

    result = designer._fallback_design("hybrid")

    node_names = [node["name"] for node in result["nodes"]]
    assert node_names.count("router") == 1
    assert node_names.count("supervisor") == 1
    assert len([name for name in node_names if name.startswith("specialist_")]) >= 1
    assert len(
        [name for name in node_names if name not in {"router", "supervisor"} and not name.startswith("specialist_")]
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_count"),
    [
        ('[{"name":"tool","category":"misc","purpose":"x","configuration":{}}]', 1),
        ("invalid", 0),
    ],
)
async def test_toolchain_engineer_parsing(payload, expected_count, monkeypatch):
    """ToolchainEngineer returns empty list on parse errors."""
    monkeypatch.setattr(
        toolchain_engineer,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    engineer = toolchain_engineer.ToolchainEngineer()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    result = await engineer.plan_tools({"nodes": []}, constraints)
    assert len(result) == expected_count


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
