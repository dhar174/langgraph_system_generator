"""Tests for modernized pattern generator output."""

from __future__ import annotations

from langgraph_system_generator.patterns import (
    CritiqueLoopPattern,
    RouterPattern,
    SubagentsPattern,
)


def test_router_pattern_emits_typed_state_and_command_routing():
    state_code = RouterPattern.generate_state_code(
        additional_fields={"user_id": "User identifier"}
    )
    router_code = RouterPattern.generate_router_node_code(["search", "analyze"])
    graph_code = RouterPattern.generate_graph_code(["search", "analyze"])

    assert "TypedDict" in state_code
    assert "add_messages" in state_code
    assert "route_history" in state_code
    assert "user_id: str" in state_code

    assert "Command" in router_code
    assert "RouteDecision" in router_code
    assert "with_structured_output" in router_code

    assert "InMemorySaver" in graph_code
    assert 'workflow.add_node("router", router_node)' in graph_code
    assert "add_conditional_edges" not in graph_code


def test_subagents_pattern_emits_supervisor_command_flow_and_finish_node():
    state_code = SubagentsPattern.generate_state_code(
        additional_fields={"priority": "Task priority"}
    )
    supervisor_code = SubagentsPattern.generate_supervisor_code(
        ["researcher", "writer"],
        {"researcher": "Gather evidence", "writer": "Draft answer"},
    )
    tool_agent_code = SubagentsPattern.generate_subagent_code(
        "researcher",
        "Gather evidence",
        include_tools=True,
    )
    graph_code = SubagentsPattern.generate_graph_code(["researcher", "writer"])

    assert "TypedDict" in state_code
    assert "next_agent: str" in state_code
    assert "dispatch_log" in state_code
    assert "priority: str" in state_code

    assert "SupervisorDecision" in supervisor_code
    assert "Command" in supervisor_code
    assert "with_structured_output" in supervisor_code
    assert "MAX_ITERATIONS" in supervisor_code

    assert "llm.bind_tools(tools)" in tool_agent_code
    assert "lookup_context" in tool_agent_code

    assert "finish_node" in graph_code
    assert "InMemorySaver" in graph_code
    assert 'workflow.add_edge("researcher", "supervisor")' in graph_code


def test_critique_loop_pattern_emits_structured_judging_and_finalize_path():
    state_code = CritiqueLoopPattern.generate_state_code(
        additional_fields={"audience": "Target audience"}
    )
    critique_code = CritiqueLoopPattern.generate_critique_node_code(
        criteria=["Accuracy", "Clarity"],
        max_revisions=2,
        min_quality_score=0.9,
    )
    helper_code = CritiqueLoopPattern.generate_conditional_edge_code(
        max_revisions=2,
        min_quality_score=0.9,
    )
    graph_code = CritiqueLoopPattern.generate_graph_code(
        max_revisions=2,
        min_quality_score=0.9,
    )

    assert "TypedDict" in state_code
    assert "revision_history" in state_code
    assert "audience: str" in state_code

    assert "CritiqueAssessment" in critique_code
    assert "Command" in critique_code
    assert "with_structured_output" in critique_code
    assert 'goto="finalize" if should_finalize else "revise"' in critique_code

    assert "should_continue" in helper_code
    assert "quality_score >= 0.9" in helper_code
    assert "finalize_node" in graph_code
    assert "InMemorySaver" in graph_code


def test_generated_pattern_sections_compile_as_python():
    snippets = [
        RouterPattern.generate_state_code(),
        RouterPattern.generate_router_node_code(["search"]),
        RouterPattern.generate_graph_code(["search"]),
        RouterPattern.generate_complete_example(["search"]),
        SubagentsPattern.generate_state_code(),
        SubagentsPattern.generate_supervisor_code(["researcher"]),
        SubagentsPattern.generate_graph_code(["researcher"]),
        SubagentsPattern.generate_complete_example(["researcher"]),
        CritiqueLoopPattern.generate_state_code(),
        CritiqueLoopPattern.generate_generation_node_code(),
        CritiqueLoopPattern.generate_critique_node_code(),
        CritiqueLoopPattern.generate_graph_code(),
        CritiqueLoopPattern.generate_complete_example(),
    ]

    for snippet in snippets:
        compile(snippet, "<generated-pattern>", "exec")
