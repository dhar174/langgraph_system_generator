"""Tests for START/END sentinel-edge normalization."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from langgraph_system_generator.generator.agents.graph_designer import GraphDesigner
from langgraph_system_generator.generator.graph_sentinels import normalize_sentinel_edges
from langgraph_system_generator.generator.state import (
    GraphCommandRouteSpec,
    GraphConditionalEdgeSpec,
    GraphDesignResult,
    GraphEdgeSpec,
    GraphNodeSpec,
)


class DummyResponse:
    """Simple LLM response stub."""

    def __init__(self, content: str):
        self.content = content


class StubLLM:
    """Return one fixed graph-design payload."""

    def __init__(self, payload: dict):
        self.payload = payload

    async def ainvoke(self, _messages):
        return DummyResponse(json.dumps(self.payload))


def make_result(
    *,
    edges: list[GraphEdgeSpec],
    entry_point: str = "",
    conditional_edges: list[GraphConditionalEdgeSpec] | None = None,
    command_routes: list[GraphCommandRouteSpec] | None = None,
) -> GraphDesignResult:
    """Build a compact graph result for normalization tests."""

    return GraphDesignResult(
        architecture_type="router",
        state_schema={"messages": "Message history"},
        nodes=[
            GraphNodeSpec(name="intake", purpose="Accept the task"),
            GraphNodeSpec(name="finalize", purpose="Finalize the result"),
            GraphNodeSpec(name="repair", purpose="Repair a failed result"),
        ],
        edges=edges,
        conditional_edges=conditional_edges or [],
        command_routes=command_routes or [],
        entry_point=entry_point,
    )


def test_start_edge_sets_entry_point_and_is_removed():
    result = make_result(edges=[GraphEdgeSpec(**{"from": "START", "to": "intake"})])

    normalized = normalize_sentinel_edges(result)

    assert normalized.entry_point == "intake"
    assert normalized.edges == []


def test_lowercase_langgraph_start_sentinel_is_supported():
    result = make_result(
        edges=[GraphEdgeSpec(**{"from": "__start__", "to": "intake"})]
    )

    normalized = normalize_sentinel_edges(result)

    assert normalized.entry_point == "intake"


def test_end_edge_makes_source_terminal_by_removing_edge():
    result = make_result(
        entry_point="intake",
        edges=[
            GraphEdgeSpec(**{"from": "intake", "to": "finalize"}),
            GraphEdgeSpec(**{"from": "finalize", "to": "END"}),
        ],
    )

    normalized = normalize_sentinel_edges(result)

    assert [(edge.source, edge.target) for edge in normalized.edges] == [
        ("intake", "finalize")
    ]


def test_conflicting_start_edge_and_entry_point_fails():
    result = make_result(
        entry_point="finalize",
        edges=[GraphEdgeSpec(**{"from": "START", "to": "intake"})],
    )

    with pytest.raises(ValueError, match="Conflicting entry points"):
        normalize_sentinel_edges(result)


def test_multiple_start_destinations_fail():
    result = make_result(
        edges=[
            GraphEdgeSpec(**{"from": "START", "to": "intake"}),
            GraphEdgeSpec(**{"from": "__start__", "to": "finalize"}),
        ]
    )

    with pytest.raises(ValueError, match="Conflicting START edge targets"):
        normalize_sentinel_edges(result)


def test_start_cannot_be_an_edge_target():
    result = make_result(
        entry_point="intake",
        edges=[GraphEdgeSpec(**{"from": "intake", "to": "START"})],
    )

    with pytest.raises(ValueError, match="START may only be used as an edge source"):
        normalize_sentinel_edges(result)


def test_end_cannot_be_an_edge_source():
    result = make_result(
        entry_point="intake",
        edges=[GraphEdgeSpec(**{"from": "END", "to": "finalize"})],
    )

    with pytest.raises(ValueError, match="END may only be used as an edge target"):
        normalize_sentinel_edges(result)


def test_unknown_end_edge_source_fails_before_edge_is_removed():
    result = make_result(
        entry_point="intake",
        edges=[GraphEdgeSpec(**{"from": "missing", "to": "END"})],
    )

    with pytest.raises(ValueError, match="does not match any declared node"):
        normalize_sentinel_edges(result)


def test_unconditional_end_cannot_coexist_with_direct_route():
    result = make_result(
        entry_point="intake",
        edges=[
            GraphEdgeSpec(**{"from": "intake", "to": "END"}),
            GraphEdgeSpec(**{"from": "intake", "to": "repair"}),
        ],
    )

    with pytest.raises(ValueError, match="another outgoing route"):
        normalize_sentinel_edges(result)


def test_unconditional_end_cannot_coexist_with_conditional_route():
    result = make_result(
        entry_point="intake",
        edges=[GraphEdgeSpec(**{"from": "intake", "to": "END"})],
        conditional_edges=[
            GraphConditionalEdgeSpec(
                **{
                    "from": "intake",
                    "condition": "Repair when needed",
                    "branches": {"repair": "repair", "finish": "END"},
                }
            )
        ],
    )

    with pytest.raises(ValueError, match="another outgoing route"):
        normalize_sentinel_edges(result)


@pytest.mark.asyncio
async def test_graph_designer_accepts_direct_start_and_end_shorthand():
    payload = {
        "state_schema": {"messages": "Message history"},
        "nodes": [
            {"name": "intake", "purpose": "Accept the task", "role": "router"},
            {"name": "finalize", "purpose": "Finalize the result", "role": "worker"},
        ],
        "edges": [
            {"from": "START", "to": "intake"},
            {"from": "intake", "to": "finalize"},
            {"from": "finalize", "to": "END"},
        ],
        "conditional_edges": [],
        "command_routes": [],
        "tool_reachability": [],
        "entry_point": "",
        "compiled_graph_variable": "graph",
        "checkpointing": True,
    }

    with patch(
        "langgraph_system_generator.generator.agents.graph_designer.build_chat_llm",
        return_value=StubLLM(payload),
    ):
        designer = GraphDesigner()

    result = await designer.design_workflow(
        {"architecture_type": "router", "selected_patterns": {}},
        [],
    )

    assert result.feedback.fallback_used is False
    assert result.entry_point == "intake"
    assert [(edge.source, edge.target) for edge in result.edges] == [
        ("intake", "finalize")
    ]
    assert result.exports.schema["terminal_nodes"] == ["finalize"]
