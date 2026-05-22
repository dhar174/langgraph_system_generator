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


def _route_specs(
    routes: List[str],
    *,
    include_fallback: bool = True,
    fallback_route: str = "fallback",
) -> List[tuple[str, str]]:
    """Return ``(label, node_name)`` pairs for generated routes."""
    values = routes or ["default"]
    labels: List[str] = []
    for route in [*values, *(["fallback"] if include_fallback else [])]:
        label = fallback_route if route == "fallback" else route
        if label not in labels:
            labels.append(label)
    return [(route, sanitize_identifier(route)) for route in labels]


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
        use_notebook_helper: bool = False,
        include_fallback: bool = True,
        fallback_route: str = "fallback",
    ) -> str:
        """Generate a router node that returns ``Command``."""
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config

        specs = _route_specs(
            routes,
            include_fallback=include_fallback,
            fallback_route=fallback_route,
        )
        route_literals = ", ".join(double_quoted_literal(label) for label, _ in specs)
        route_help = "\n".join(
            (
                f"- {label}: Handle unclear, conversational, unsupported, or out-of-domain requests."
                if label == fallback_route
                else f"- {label}: Handle {label}-specific requests."
            )
            for label, _ in specs
        )
        route_names = ", ".join(label for label, _ in specs)
        llm_init = build_llm_init(
            config.model,
            0,
            config.api_base,
            config.max_tokens,
            use_notebook_helper=use_notebook_helper,
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


def router_node(state: WorkflowState, window_size: int = 5) -> WorkflowState:
    """Routes requests to appropriate specialist based on input classification.
    
    Analyzes the user's message and determines which specialized agent
    should handle the request based on content and intent.
    """
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    window_size = max(window_size, 1)
    recent_messages = messages[-window_size:] if messages else []
    conversation_history = "\\n".join(
        f"{{getattr(message, 'type', message.__class__.__name__)}}: {{message.content}}"
        for message in recent_messages
    ) or "No prior conversation available."
    
    # Initialize LLM with structured output
    llm = {llm_init}
    structured_llm = llm.with_structured_output(RouteDecision)
    
    # Classification prompt
    system_prompt = SystemMessage(content="""You are a routing classifier.
Analyze the recent conversation and select the most appropriate route.
Resolve coreferences such as "it", "that", and "the one" using the conversation history.
Use the {fallback_route} route for greetings, generic chat, unsupported requests, missing-tool requests, or anything that does not clearly belong to a specialist.
Respond using the provided RouteDecision schema.""")

    classification_prompt = f"""Analyze the following conversation and determine which route should handle the user's latest request.

Available routes:
{route_help}

Recent conversation (last {{window_size}} messages):
{{conversation_history}}

Latest user request: {{last_message}}

Select the most appropriate route and explain your reasoning."""
    
    # Get classification
    decision = structured_llm.invoke([system_prompt, HumanMessage(content=classification_prompt)])
    
    return {{
        "route": decision.route,
        "route_reasoning": decision.reasoning,
        "route_history": [decision.route],
        "messages": [AIMessage(content=f"Routing to: {{decision.route}} ({{decision.reasoning}})")],
    }}'''
        else:
            return f'''from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def router_node(state: WorkflowState, window_size: int = 5) -> WorkflowState:
    """Routes requests to appropriate specialist based on input classification."""
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    window_size = max(window_size, 1)
    recent_messages = messages[-window_size:] if messages else []
    conversation_history = "\\n".join(
        f"{{getattr(message, 'type', message.__class__.__name__)}}: {{message.content}}"
        for message in recent_messages
    ) or "No prior conversation available."
    
    llm = {llm_init}
    
    # Classification prompt
    system_prompt = SystemMessage(content=f"""You are a routing classifier.
Analyze the recent conversation and select the appropriate route from: {route_names}
Resolve coreferences such as "it", "that", and "the one" using the conversation history.
Use {fallback_route} for greetings, generic chat, unsupported requests, missing-tool requests, or anything that does not clearly belong to a specialist.
Respond with ONLY the route name.""")
    
    user_prompt = HumanMessage(content=f"""Recent conversation (last {{window_size}} messages):
{{conversation_history}}

Latest user request: {{last_message}}
Route:""")
    
    # Get classification
    response = llm.invoke([system_prompt, user_prompt])
    selected_route = response.content.strip().lower()
    
    # Validate route
    valid_routes = [r.lower() for r in {repr([label for label, _ in specs])}]
    if not valid_routes:
        raise ValueError("Router configuration must include at least one route.")
    if selected_route not in valid_routes:
        selected_route = {double_quoted_literal(fallback_route)}  # Safe general route
    
    return {{
        "route": selected_route,
        "route_history": [selected_route],
    }}'''

    @staticmethod
    def generate_route_node_code(
        route_name: str,
        route_purpose: str,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_notebook_helper: bool = False,
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
            use_notebook_helper=use_notebook_helper,
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
        include_fallback: bool = True,
        fallback_route: str = "fallback",
    ) -> str:
        """Generate a graph using dynamic ``Command``-based routing."""
        specs = _route_specs(
            routes,
            include_fallback=include_fallback,
            fallback_route=fallback_route,
        )
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
                    f"if route == {double_quoted_literal(route)}:\n"
                    f"        return {double_quoted_literal(node_name)}"
                    for route, node_name in specs
                ]
            )
            path_map_entries = ", ".join(
                f"{double_quoted_literal(node_name)}: {double_quoted_literal(node_name)}"
                for _, node_name in specs
            )

            return f'''from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver


def route_decision(state: WorkflowState) -> str:
    """Determine next node based on router decision."""
    route = state.get("route", "")
    {route_conditions}
    return {double_quoted_literal(sanitize_identifier(fallback_route)) if include_fallback else "END"}


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
    {{{path_map_entries}, "END": END}}
)

# Connect all routes to END
{terminal_edges}

# Compile graph
graph = workflow.compile(checkpointer=memory)'''
        else:
            # Simple edge-based routing (less common, included for completeness)
            return f"""from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

workflow = StateGraph(WorkflowState)
checkpointer = InMemorySaver()

# Add router node
workflow.add_node('router', router_node)

workflow.add_node('{entry_node}', router_node)
{node_additions}

workflow.add_edge(START, '{entry_node}')
{terminal_edges}

graph = workflow.compile(checkpointer=checkpointer)"""

    @staticmethod
    def generate_complete_example(
        routes: List[str],
        route_purposes: Optional[Dict[str, str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        include_fallback: bool = True,
        fallback_route: str = "fallback",
    ) -> str:
        """Generate a full runnable router example."""
        specs = _route_specs(
            routes,
            include_fallback=include_fallback,
            fallback_route=fallback_route,
        )
        if route_purposes is None:
            route_purposes = {
                label: (
                    "Handle general, unsupported, or unclear requests safely."
                    if label == fallback_route
                    else f"Handle {label}-related tasks with clear specialist reasoning."
                )
                for label, _ in specs
            }

        state_code = RouterPattern.generate_state_code()
        router_code = RouterPattern.generate_router_node_code(
            [label for label, _ in specs],
            model_config=model_config,
            include_fallback=include_fallback,
            fallback_route=fallback_route,
        )
        route_nodes = "\n\n".join(
            RouterPattern.generate_route_node_code(
                label,
                route_purposes.get(
                    label,
                    (
                        "Handle general, unsupported, or unclear requests safely."
                        if label == fallback_route
                        else f"Handle {label}-related tasks with clear specialist reasoning."
                    ),
                ),
                model_config=model_config,
            )
            for label, _ in specs
        )
        graph_code = RouterPattern.generate_graph_code(
            [label for label, _ in specs],
            include_fallback=include_fallback,
            fallback_route=fallback_route,
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
    main()'''
