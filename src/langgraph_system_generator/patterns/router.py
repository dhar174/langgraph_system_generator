"""Router pattern generator aligned with current LangGraph graph APIs."""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from langgraph_system_generator.patterns.utils import (
    build_llm_init,
    double_quoted_literal,
    render_additional_fields,
    sanitize_identifier,
)
from langgraph_system_generator.utils.config import ModelConfig


def _route_specs(routes: List[str]) -> List[tuple[str, str]]:
    """Return ``(label, node_name)`` pairs for generated routes."""
    values = routes or ["default"]
    return [(route, sanitize_identifier(route)) for route in values]


class RouterPattern:
    """Template generator for router-based multi-agent patterns."""

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate a TypedDict state schema for router workflows."""
        additional = render_additional_fields(additional_fields)
        return f'''import operator
from typing import Annotated, Dict, List
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_dicts(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    """Reducer used to merge route outputs into a single state field."""
    merged = dict(left or {{}})
    merged.update(right or {{}})
    return merged


class WorkflowState(TypedDict, total=False):
    """State schema for a router workflow."""

    messages: Annotated[List[BaseMessage], add_messages]
    route: str
    route_reasoning: str
    route_history: Annotated[List[str], operator.add]
    results: Annotated[Dict[str, str], merge_dicts]
    final_output: str
{additional}'''

    @staticmethod
    def generate_router_node_code(
        routes: List[str],
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
    ) -> str:
        """Generate a router node that returns ``Command``."""
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config

        specs = _route_specs(routes)
        route_literals = ", ".join(double_quoted_literal(label) for label, _ in specs)
        node_literals = ", ".join(double_quoted_literal(node_name) for _, node_name in specs)
        route_map_lines = ",\n        ".join(
            f"{double_quoted_literal(label)}: {double_quoted_literal(node_name)}"
            for label, node_name in specs
        )
        route_help = "\n".join(
            f"- {label}: Handle {label}-specific requests." for label, _ in specs
        )
        llm_init = build_llm_init(
            config.model,
            0,
            config.api_base,
            config.max_tokens,
        )

        if use_structured_output:
            return f'''from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Typed routing decision returned by the classifier."""

    route: Literal[{route_literals}] = Field(
        description="Which specialist should handle the request."
    )
    reasoning: str = Field(
        description="Why this route is the best match for the request."
    )


def router_node(state: WorkflowState) -> Command[Literal[{node_literals}]]:
    """Classify the request and route to the matching specialist."""
    route_map = {{
        {route_map_lines}
    }}
    messages = state.get("messages", [])
    request_text = messages[-1].content if messages else "Route the incoming request."

    llm = {llm_init}
    decision = llm.with_structured_output(RouteDecision).invoke([
        SystemMessage(
            content="""You are a router for a LangGraph workflow.

Available specialists:
{route_help}
"""
        ),
        HumanMessage(content=f"Request: {{request_text}}"),
    ])

    return Command(
        update={{
            "route": decision.route,
            "route_reasoning": decision.reasoning,
            "route_history": [decision.route],
            "messages": [
                AIMessage(
                    content=f"Router selected {{decision.route}} because: {{decision.reasoning}}"
                )
            ],
        }},
        goto=route_map[decision.route],
    )'''

        fallback_route = specs[0][0]
        return f'''from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command


def router_node(state: WorkflowState) -> Command[Literal[{node_literals}]]:
    """Fallback router that asks the model for a route label."""
    route_map = {{
        {route_map_lines}
    }}
    valid_routes = list(route_map)
    messages = state.get("messages", [])
    request_text = messages[-1].content if messages else "Route the incoming request."

    llm = {llm_init}
    response = llm.invoke([
        SystemMessage(
            content="""You are a router for a LangGraph workflow.
Reply with only one route label from: {", ".join(label for label, _ in specs)}."""
        ),
        HumanMessage(content=f"Request: {{request_text}}"),
    ])
    selected_route = response.content.strip()
    if selected_route not in route_map:
        selected_route = {double_quoted_literal(fallback_route)}

    return Command(
        update={{
            "route": selected_route,
            "route_reasoning": f"Model selected {{selected_route}}",
            "route_history": [selected_route],
            "messages": [AIMessage(content=f"Router selected {{selected_route}}")],
        }},
        goto=route_map[selected_route],
    )'''

    @staticmethod
    def generate_route_node_code(
        route_name: str,
        route_purpose: str,
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate a specialist node for a single route."""
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config

        node_name = sanitize_identifier(route_name)
        llm_init = build_llm_init(
            config.model,
            config.temperature,
            config.api_base,
            config.max_tokens,
        )

        return f'''from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI


def {node_name}_node(state: WorkflowState) -> dict:
    """Execute the {route_name} specialist."""
    messages = state.get("messages", [])
    llm = {llm_init}

    response = llm.invoke([
        SystemMessage(
            content="""You are the {route_name} specialist.

Responsibility:
{route_purpose}
"""
        ),
        *messages,
    ])

    return {{
        "results": {{"{route_name}": response.content}},
        "final_output": response.content,
        "messages": [AIMessage(content=f"{route_name} specialist completed the task.")],
    }}'''

    @staticmethod
    def generate_graph_code(
        routes: List[str],
        entry_point: str = "router",
        use_conditional_edges: bool = True,
    ) -> str:
        """Generate a graph using dynamic ``Command``-based routing."""
        del use_conditional_edges
        specs = _route_specs(routes)
        entry_node = sanitize_identifier(entry_point or "router")
        node_additions = "\n".join(
            f'workflow.add_node("{node_name}", {node_name}_node)'
            for _, node_name in specs
        )
        terminal_edges = "\n".join(
            f'workflow.add_edge("{node_name}", END)' for _, node_name in specs
        )

        if use_conditional_edges:
            # Generate conditional routing function
            route_conditions = "\n    ".join(
                [
                    f'if route == "{route}":\n        return "{route.lower().replace(" ", "_")}"'
                    for route in routes
                ]
            )

            return f'''from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver


def route_decision(state: WorkflowState) -> str:
    """Determine next node based on router decision."""
    route = state.get("route", "")
    {route_conditions}
    return END


# Create graph
workflow = StateGraph(WorkflowState)
memory = InMemorySaver()

# Add router node
workflow.add_node("router", router_node)

# Add route-specific nodes
{node_additions}

# Connect start to router
workflow.add_edge(START, "router")

# Add conditional edges from router to routes
workflow.add_conditional_edges(
    "router",
    route_decision,
    {{{", ".join([f'"{route.lower().replace(" ", "_")}": "{route.lower().replace(" ", "_")}"' for route in routes])}, "END": END}}
)

# Connect all routes to END
{chr(10).join([f'workflow.add_edge("{route.lower().replace(" ", "_")}", END)' for route in routes])}

# Compile graph
graph = workflow.compile(checkpointer=memory)'''
        else:
            # Simple edge-based routing (less common, included for completeness)
            return f"""from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

workflow = StateGraph(WorkflowState)
memory = InMemorySaver()

# Add router node
workflow.add_node("router", router_node)

workflow.add_node("{entry_node}", router_node)
{node_additions}

workflow.add_edge(START, "{entry_node}")
{terminal_edges}

graph = workflow.compile(checkpointer=checkpointer)'''

    @staticmethod
    def generate_complete_example(
        routes: List[str],
        route_purposes: Optional[Dict[str, str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate a full runnable router example."""
        specs = _route_specs(routes)
        if route_purposes is None:
            route_purposes = {
                label: f"Handle {label}-related tasks with clear specialist reasoning."
                for label, _ in specs
            }

        state_code = RouterPattern.generate_state_code()
        router_code = RouterPattern.generate_router_node_code(
            [label for label, _ in specs],
            model_config=model_config,
        )
        route_nodes = "\n\n".join(
            RouterPattern.generate_route_node_code(
                label,
                route_purposes.get(
                    label,
                    f"Handle {label}-related tasks with clear specialist reasoning.",
                ),
                model_config=model_config,
            )
            for label, _ in specs
        )
        graph_code = RouterPattern.generate_graph_code(
            [label for label, _ in specs],
        )

        return f'''"""Router Pattern Example."""

from __future__ import annotations

import argparse
import asyncio

from langchain_core.messages import HumanMessage

{state_code}

{router_code}

{route_nodes}

{graph_code}


def build_initial_state(user_request: str) -> WorkflowState:
    """Create an initial workflow state for the demo."""
    return {{
        "messages": [HumanMessage(content=user_request)],
        "results": {{}},
        "route_history": [],
        "final_output": "",
    }}


async def run_example(user_request: str) -> WorkflowState:
    """Run the router workflow and return the final state."""
    return await graph.ainvoke(build_initial_state(user_request))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the router pattern example.")
    parser.add_argument("prompt", nargs="?", default="Summarize the latest product feedback.")
    args = parser.parse_args()

    result = asyncio.run(run_example(args.prompt))
    print("Route:", result.get("route"))
    print("Reasoning:", result.get("route_reasoning"))
    print("Final Output:")
    print(result.get("final_output", ""))


if __name__ == "__main__":
    main()
'''
