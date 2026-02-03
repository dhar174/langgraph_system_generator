"""Tests for generator agents fallback behavior."""

from __future__ import annotations

import pytest

from langgraph_system_generator.generator.agents import (
    architecture_selector,
    graph_designer,
    requirements_analyst,
    toolchain_engineer,
)
from langgraph_system_generator.generator.state import Constraint


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
@pytest.mark.parametrize(
    ("payload", "expected_value"),
    [
        ('[{"type":"goal","value":"from-json","priority":5}]', "from-json"),
        ("not json", "x"),
    ],
)
async def test_requirements_analyst_parsing(payload, expected_value, monkeypatch):
    """RequirementsAnalyst returns parsed constraints or fallback on errors."""
    monkeypatch.setattr(
        requirements_analyst,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    analyst = requirements_analyst.RequirementsAnalyst()
    results = await analyst.analyze("x")
    assert results[0].value == expected_value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_arch"),
    [
        (
            '{"architecture_type":"subagents","patterns":{"primary":"subagents","secondary":[]},"justification":"x"}',
            "subagents",
        ),
        ("nope", "router"),
    ],
)
async def test_architecture_selector_parsing(payload, expected_arch, monkeypatch):
    """ArchitectureSelector falls back to router on parse errors."""
    monkeypatch.setattr(
        architecture_selector,
        "ChatOpenAI",
        make_stub_llm(payload),
    )
    selector = architecture_selector.ArchitectureSelector()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    result = await selector.select_architecture(constraints, [])
    assert result["architecture_type"] == expected_arch


@pytest.mark.asyncio
async def test_graph_designer_fallback_router(monkeypatch):
    """GraphDesigner falls back to router design when parsing fails."""
    monkeypatch.setattr(
        graph_designer,
        "ChatOpenAI",
        make_stub_llm("invalid"),
    )
    designer = graph_designer.GraphDesigner()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    architecture = {"architecture_type": "router", "justification": "x"}
    expected = designer._fallback_design("router")
    result = await designer.design_workflow(architecture, constraints)
    assert result == expected


@pytest.mark.asyncio
async def test_graph_designer_fallback_subagents(monkeypatch):
    """GraphDesigner falls back to subagents design when parsing fails."""
    monkeypatch.setattr(
        graph_designer,
        "ChatOpenAI",
        make_stub_llm("invalid"),
    )
    designer = graph_designer.GraphDesigner()
    constraints = [Constraint(type="goal", value="x", priority=5)]
    architecture = {"architecture_type": "subagents", "justification": "x"}
    expected = designer._fallback_design("subagents")
    result = await designer.design_workflow(architecture, constraints)
    assert result == expected


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
