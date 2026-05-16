"""Generator graph assembly and workflow orchestration."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from langgraph_system_generator.generator.nodes import (
    architecture_selection_node,
    context_pack_node,
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
from langgraph_system_generator.qa.summary import has_blocking_failures
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
    blocking_reports = [
        report for report in failed_reports if report.severity == "error"
    ]

    # If there are no blocking failures, proceed to package. Warning/info
    # findings are advisory and remain visible through qa_summary.
    if not has_blocking_failures(qa_reports):
        return "package"

    # Environment/runtime support failures in live mode are product-gate failures
    # and should not enter the repair loop because repair cannot provision kernels
    # or missing execution dependencies.
    for report in blocking_reports:
        evidence = report.evidence
        if (
            report.check_name == "Runtime Check"
            and evidence.get("failure_kind") == "runtime_unavailable"
            and evidence.get("generation_mode") == "live"
        ):
            return "fail"

    # If max repair attempts reached, fail
    if state["repair_attempts"] >= settings.max_repair_attempts:
        return "fail"

    # Otherwise, attempt repair
    return "repair"


def should_retry_after_repair(
    state: GeneratorState,
) -> Literal["retry_qa", "fail", "success"]:
    """Decide whether to retry QA after repair attempt.

    Args:
        state: Current generator state

    Returns:
        Decision: "retry_qa", "fail", or "success"
    """
    # After repair, retry QA if we haven't exhausted attempts
    if state["repair_attempts"] < settings.max_repair_attempts:
        return "retry_qa"

    # If we've exhausted attempts, proceed with best effort if we have cells
    if len(state.get("generated_cells", [])) > 0:
        return "success"

    return "fail"


def create_generator_graph(*, generation_config=None) -> StateGraph:
    """Build the outer generator graph.

    Returns:
        Compiled StateGraph ready for execution
    """
    workflow = StateGraph(GeneratorState)

    # Add all nodes
    workflow.add_node("intake", intake_node)
    workflow.add_node("rag_retrieval", rag_retrieval_node)
    workflow.add_node("context_pack", context_pack_node)
    workflow.add_node("architecture_selection", architecture_selection_node)
    workflow.add_node("graph_design", graph_design_node)
    workflow.add_node("tooling_plan", tooling_plan_node)
    workflow.add_node("notebook_assembly", notebook_assembly_node)
    workflow.add_node("static_qa", static_qa_node)
    workflow.add_node("runtime_qa", runtime_qa_node)
    workflow.add_node("repair", repair_node)
    workflow.add_node("package_outputs", package_outputs_node)

    # Define the linear workflow with conditional repair loop
    workflow.add_edge(START, "intake")
    workflow.add_edge("intake", "rag_retrieval")
    workflow.add_edge("rag_retrieval", "architecture_selection")
    workflow.add_edge("architecture_selection", "context_pack")
    workflow.add_edge("context_pack", "graph_design")
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
        should_retry_after_repair,
        {
            "retry_qa": "static_qa",
            "success": "package_outputs",
            "fail": END,
        },
    )

    workflow.add_edge("package_outputs", END)

    return workflow.compile()
