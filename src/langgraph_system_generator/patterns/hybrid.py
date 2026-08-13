"""Hybrid pattern generator combining router and supervisor/team flows."""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from langgraph_system_generator.patterns.router import RouterPattern
from langgraph_system_generator.patterns.subagents import SubagentsPattern
from langgraph_system_generator.patterns.utils import (
    double_quoted_literal,
    render_additional_fields,
    sanitize_identifier,
)
from langgraph_system_generator.utils.config import ModelConfig


def _hybrid_specs(
    values: List[str] | None,
    default: List[str],
) -> List[tuple[str, str]]:
    """Return ``(label, node_name)`` pairs for hybrid direct or worker nodes."""

    labels = list(values or default)
    return [(label, sanitize_identifier(label)) for label in labels]


class HybridPattern:
    """Template generator for mixed direct-routing plus worker-team workflows."""

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate a TypedDict state schema for hybrid workflows."""

        additional = render_additional_fields(additional_fields)
        return f'''import operator
from typing import Annotated, Dict, List
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_dicts(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    """Reducer used to merge hybrid workflow outputs."""
    merged = dict(left or {{}})
    merged.update(right or {{}})
    return merged


class WorkflowState(TypedDict, total=False):
    """State schema for a hybrid router plus worker-team workflow."""

    messages: Annotated[List[BaseMessage], add_messages]
    route: str
    route_reasoning: str
    route_history: Annotated[List[str], operator.add]
    next_agent: str
    next_agents: List[str]
    instructions: str
    iterations: int
    dispatch_log: Annotated[List[str], operator.add]
    results: Annotated[Dict[str, str], merge_dicts]
    task_results: Annotated[Dict[str, str], merge_dicts]
    final_output: str
{additional}'''

    @staticmethod
    def generate_router_node_code(
        direct_specialists: List[str],
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_notebook_helper: bool = False,
    ) -> str:
        """Generate a router capable of choosing direct work or the team path."""

        routes = [*direct_specialists, "team_path"]
        return RouterPattern.generate_router_node_code(
            routes=routes,
            model_config=model_config,
            use_notebook_helper=use_notebook_helper,
            include_fallback=False,
        )

    @staticmethod
    def generate_direct_specialist_code(
        specialist_name: str,
        specialist_purpose: str,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_notebook_helper: bool = False,
    ) -> str:
        """Generate a direct specialist node implementation."""

        return RouterPattern.generate_route_node_code(
            specialist_name,
            specialist_purpose,
            model_config=model_config,
            use_notebook_helper=use_notebook_helper,
        )

    @staticmethod
    def generate_supervisor_code(
        team_workers: List[str],
        worker_descriptions: Optional[Dict[str, str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_notebook_helper: bool = False,
    ) -> str:
        """Generate the supervisor node for the worker-team branch."""

        return SubagentsPattern.generate_supervisor_code(
            subagents=team_workers,
            subagent_descriptions=worker_descriptions,
            model_config=model_config,
            use_notebook_helper=use_notebook_helper,
        )

    @staticmethod
    def generate_worker_code(
        worker_name: str,
        worker_description: str,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_notebook_helper: bool = False,
    ) -> str:
        """Generate a worker node implementation."""

        return SubagentsPattern.generate_subagent_code(
            agent_name=worker_name,
            agent_description=worker_description,
            model_config=model_config,
            use_notebook_helper=use_notebook_helper,
        )

    @staticmethod
    def generate_graph_code(
        direct_specialists: List[str],
        team_workers: List[str],
        max_iterations: int = 10,
    ) -> str:
        """Generate graph wiring for the hybrid workflow."""

        direct_specialist_specs = _hybrid_specs(
            direct_specialists,
            ["specialist_1"],
        )
        team_worker_specs = _hybrid_specs(
            team_workers,
            ["worker"],
        )
        direct_node_additions = "\n".join(
            f'workflow.add_node("{node_name}", {node_name}_node)'
            for _, node_name in direct_specialist_specs
        )
        worker_node_additions = "\n".join(
            f'workflow.add_node("{node_name}", {node_name}_node)'
            for _, node_name in team_worker_specs
        )
        router_branch_map = ", ".join(
            [
                f"{double_quoted_literal(label)}: {double_quoted_literal(node_name)}"
                for label, node_name in direct_specialist_specs
            ]
            + ['"team_path": "supervisor"', '"END": END']
        )
        direct_finish_edges = "\n".join(
            f'workflow.add_edge("{node_name}", "finish")'
            for _, node_name in direct_specialist_specs
        )
        worker_return_edges = "\n".join(
            f'workflow.add_edge("{node_name}", "supervisor")'
            for _, node_name in team_worker_specs
        )
        direct_route_labels = ", ".join(
            double_quoted_literal(label) for label, _ in direct_specialist_specs
        )
        supervisor_route_map = ",\n        ".join(
            [
                f"{double_quoted_literal(label)}: {double_quoted_literal(node_name)}"
                for label, node_name in team_worker_specs
            ]
            + [
                f"{double_quoted_literal(node_name)}: {double_quoted_literal(node_name)}"
                for _, node_name in team_worker_specs
            ]
            + ['"FINISH": "finish"', '"finish": "finish"']
        )
        worker_nodes_literal = (
            "{"
            + ", ".join(
                double_quoted_literal(node_name) for _, node_name in team_worker_specs
            )
            + "}"
        )
        supervisor_path_map = ", ".join(
            [
                f"{double_quoted_literal(node_name)}: {double_quoted_literal(node_name)}"
                for _, node_name in team_worker_specs
            ]
            + ['"finish": "finish"']
        )

        return f'''from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Send


def route_from_router(state: WorkflowState) -> str:
    """Route either to a direct specialist or the supervisor team path."""
    route = state.get("route", "")
    if route == "team_path":
        return "team_path"
    if route in {{{direct_route_labels}}}:
        return route
    return "END"


def finish_node(state: WorkflowState) -> dict:
    """Merge direct specialist and worker-team outputs into a final answer."""
    direct_results = state.get("results", {{}})
    team_results = state.get("task_results", {{}})
    sections = []
    for agent, output in direct_results.items():
        sections.append(f"## {{agent}}\\n{{output}}")
    for agent, output in team_results.items():
        sections.append(f"## {{agent}}\\n{{output}}")
    final_output = "\\n\\n".join(sections) if sections else "No workflow results were produced."
    return {{
        "final_output": final_output,
        "messages": [],
    }}


def supervisor_router(state: WorkflowState):
    """Fan out to selected worker nodes or finish the hybrid workflow."""
    route_map = {{
        {supervisor_route_map}
    }}
    worker_nodes = {worker_nodes_literal}
    requested_agents = state.get("next_agents") or []
    if not requested_agents and state.get("next_agent"):
        requested_agents = [state.get("next_agent")]

    destinations = []
    for agent_name in requested_agents:
        target = route_map.get(agent_name)
        if target == "finish":
            return "finish"
        if target in worker_nodes and target not in destinations:
            destinations.append(target)

    if not destinations:
        return "finish"
    return [Send(destination, state) for destination in destinations]


workflow = StateGraph(WorkflowState)
checkpointer = InMemorySaver()

workflow.add_node("router", router_node)
{direct_node_additions}
workflow.add_node("supervisor", supervisor_node)
{worker_node_additions}
workflow.add_node("finish", finish_node)

workflow.add_edge(START, "router")
workflow.add_conditional_edges(
    "router",
    route_from_router,
    {{{router_branch_map}}},
)
workflow.add_conditional_edges(
    "supervisor",
    supervisor_router,
    {{{supervisor_path_map}}},
)
{direct_finish_edges}
{worker_return_edges}
workflow.add_edge("finish", END)

graph = workflow.compile(checkpointer=checkpointer)

MAX_ITERATIONS = {max_iterations}'''
