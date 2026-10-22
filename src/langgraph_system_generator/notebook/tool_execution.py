"""Render only explicitly declared chatbot ToolNode execution contracts."""

from __future__ import annotations

from typing import Any


def chatbot_tool_node_code(
    node: dict[str, Any], schema: dict[str, Any], function_name: str
) -> str | None:
    """Return narrow tool-loop nodes, leaving other chatbot contracts alone."""
    entries = [
        entry
        for entry in schema.get("tool_reachability", [])
        if entry.get("execution_path") == "tool_node" and entry.get("node")
    ]
    executors = {entry["node"] for entry in entries}
    name = node.get("name")
    if name in executors:
        return f"""from langgraph.prebuilt import ToolNode

# Register the declared ToolNode directly as the generated graph handler.
{function_name} = ToolNode(TOOLS, handle_tool_errors=True)
"""
    tool_ids = {entry["tool_id"] for entry in entries}
    if node.get("role") != "assistant" or not (
        tool_ids & set(node.get("required_tools", []))
    ):
        return None
    branches: dict[str, Any] = next(
        (
            edge.get("branches", {})
            for edge in schema.get("conditional_edges", [])
            if edge.get("from", edge.get("source")) == name
        ),
        {},
    )
    tool_routes = [key for key, target in branches.items() if target in executors]
    end_routes = [
        key for key, target in branches.items() if target in {"END", "__end__"}
    ]
    if len(tool_routes) != 1 or len(end_routes) != 1:
        return None
    return f'''def {function_name}(state: WorkflowState) -> dict:
    """Produce a response or dispatch an explicit model tool request."""
    response = make_llm().bind_tools(TOOLS).invoke(state.get("messages", []))
    calls = getattr(response, "tool_calls", [])
    return {{
        "messages": [response],
        "route": {tool_routes[0]!r} if calls else {end_routes[0]!r},
        "final_response": "" if calls else str(response.content),
        "turn_count": int(state.get("turn_count", 0)) + (0 if calls else 1),
    }}
'''
