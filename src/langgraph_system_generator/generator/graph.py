"""Generator graph assembly and workflow orchestration."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, StateGraph

from langgraph_system_generator.generator.nodes import (
    architecture_selection_node,
    graph_design_node,
    intake_node,
    notebook_assembly_node,
    package_outputs_node,
    rag_retrieval_node,
    repair_node,
    runtime_qa_node,
    static_qa_node,
    tooling_plan_node,
)
from langgraph_system_generator.generator.state import GeneratorState
from langgraph_system_generator.utils.config import settings


def should_repair(
    state: GeneratorState,
) -> Literal["repair", "package", "fail"]:
    """Decide if repair is needed based on QA results.

    Args:
        state: Current generator state

    Returns:
        Decision: "repair", "package", or "fail"
    """
    qa_reports = state.get("qa_reports", [])
    failed_reports = [r for r in qa_reports if not r.passed]

    # If no failures, proceed to package
    if not failed_reports:
        return "package"

    # If max repair attempts reached, fail
    if state["repair_attempts"] >= settings.max_repair_attempts:
        return "fail"

    # Otherwise, attempt repair
    return "repair"


def check_repair_success(
    state: GeneratorState,
) -> Literal["retry_qa", "fail", "success"]:
    """Check if repair was successful and decide next action.

    Args:
        state: Current generator state

    Returns:
        Decision: "retry_qa", "fail", or "success"
    """
    # After repair, retry QA
    if state["repair_attempts"] < settings.max_repair_attempts:
        return "retry_qa"

    # If we've exhausted attempts, check if we have any cells
    if len(state.get("generated_cells", [])) > 0:
        return "success"

    return "fail"


def create_generator_graph() -> StateGraph:
    """Build the outer generator graph.

    Returns:
        Compiled StateGraph ready for execution
    """
    workflow = StateGraph(GeneratorState)

    # Add all nodes
    workflow.add_node("intake", intake_node)
    workflow.add_node("rag_retrieval", rag_retrieval_node)
    workflow.add_node("architecture_selection", architecture_selection_node)
    workflow.add_node("graph_design", graph_design_node)
    workflow.add_node("tooling_plan", tooling_plan_node)
    workflow.add_node("notebook_assembly", notebook_assembly_node)
    workflow.add_node("static_qa", static_qa_node)
    workflow.add_node("runtime_qa", runtime_qa_node)
    workflow.add_node("repair", repair_node)
    workflow.add_node("package_outputs", package_outputs_node)

    # Define the linear workflow with conditional repair loop
    workflow.set_entry_point("intake")
    workflow.add_edge("intake", "rag_retrieval")
    workflow.add_edge("rag_retrieval", "architecture_selection")
    workflow.add_edge("architecture_selection", "graph_design")
    workflow.add_edge("graph_design", "tooling_plan")
    workflow.add_edge("tooling_plan", "notebook_assembly")
    workflow.add_edge("notebook_assembly", "static_qa")
    workflow.add_edge("static_qa", "runtime_qa")

    # Conditional edge after runtime_qa for repair loop
    workflow.add_conditional_edges(
        "runtime_qa",
        should_repair,
        {
            "repair": "repair",
            "package": "package_outputs",
            "fail": END,
        },
    )

    # Conditional edge after repair
    workflow.add_conditional_edges(
        "repair",
        check_repair_success,
        {
            "retry_qa": "static_qa",
            "success": "package_outputs",
            "fail": END,
        },
    )

    workflow.add_edge("package_outputs", END)

    return workflow.compile()

