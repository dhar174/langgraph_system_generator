"""Focused router-pattern tests."""

from __future__ import annotations

from langgraph_system_generator.patterns import RouterPattern


def test_router_graph_code_uses_dynamic_command_routing():
    code = RouterPattern.generate_graph_code(["search", "analyze", "summarize"])

    assert "StateGraph(WorkflowState)" in code
    assert "InMemorySaver" in code
    assert 'workflow.add_node("router", router_node)' in code
    assert 'workflow.add_edge("search", END)' in code
    assert "add_conditional_edges" not in code


def test_router_complete_example_contains_async_entrypoint():
    code = RouterPattern.generate_complete_example(
        ["search", "analyze"],
        {
            "search": "Retrieve supporting context",
            "analyze": "Interpret the request",
        },
    )

    assert "async def run_example" in code
    assert "build_initial_state" in code
    assert "Router Pattern Example" in code
    compile(code, "<router-example>", "exec")
