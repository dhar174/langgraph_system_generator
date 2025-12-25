"""Generator graph nodes implementing the workflow pipeline."""

from __future__ import annotations

from typing import Any, Dict

from langgraph_system_generator.generator.agents import (
    ArchitectureSelector,
    GraphDesigner,
    NotebookComposer,
    QARepairAgent,
    RequirementsAnalyst,
    ToolchainEngineer,
)
from langgraph_system_generator.generator.state import (
    DocSnippet,
    GeneratorState,
    NotebookPlan,
    QAReport,
)
from langgraph_system_generator.rag.embeddings import VectorStoreManager
from langgraph_system_generator.rag.retriever import DocsRetriever
from langgraph_system_generator.utils.config import settings


async def intake_node(state: GeneratorState) -> Dict[str, Any]:
    """Initial intake and constraint extraction.

    Args:
        state: Current generator state

    Returns:
        Updated state with extracted constraints
    """
    analyst = RequirementsAnalyst()
    constraints = await analyst.analyze(state["user_prompt"])

    return {"constraints": constraints}


async def rag_retrieval_node(state: GeneratorState) -> Dict[str, Any]:
    """Retrieve relevant documentation.

    Args:
        state: Current generator state

    Returns:
        Updated state with retrieved documentation
    """
    try:
        vector_store_manager = VectorStoreManager(settings.vector_store_path)
        retriever = DocsRetriever(vector_store_manager)

        # Retrieve general docs based on user prompt
        snippets = retriever.retrieve(state["user_prompt"], k=10)

        # Convert to DocSnippet format
        docs = [
            DocSnippet(
                content=s["content"],
                source=s["source"],
                relevance_score=s["relevance_score"],
                heading=s.get("heading"),
            )
            for s in snippets
        ]

        return {"docs_context": docs}
    except Exception as e:
        # Log the error for debugging
        import logging

        logging.warning(f"RAG retrieval failed: {e}")
        # If RAG fails, continue without docs
        return {"docs_context": []}


async def architecture_selection_node(state: GeneratorState) -> Dict[str, Any]:
    """Select optimal architecture pattern.

    Args:
        state: Current generator state

    Returns:
        Updated state with architecture selection and justification
    """
    try:
        vector_store_manager = VectorStoreManager(settings.vector_store_path)
        retriever = DocsRetriever(vector_store_manager)
    except Exception as e:
        import logging

        logging.warning(f"Failed to load vector store for architecture selection: {e}")
        retriever = None

    selector = ArchitectureSelector(docs_retriever=retriever)

    architecture = await selector.select_architecture(
        state["constraints"], state["docs_context"]
    )

    selected_patterns = architecture.get("patterns", {}) or {}
    architecture_type = architecture.get("architecture_type") or "router"

    return {
        "selected_patterns": selected_patterns,
        "architecture_type": architecture_type,
        "architecture_justification": architecture.get("justification", ""),
    }


async def graph_design_node(state: GeneratorState) -> Dict[str, Any]:
    """Design the inner workflow.

    Args:
        state: Current generator state

    Returns:
        Updated state with workflow design and notebook plan
    """
    designer = GraphDesigner()

    selected_patterns = state.get("selected_patterns", {}) or {}
    architecture_type = state.get("architecture_type")
    if not architecture_type:
        architecture_type = selected_patterns.get("primary", "router")
    architecture = {
        "architecture_type": architecture_type,
        "justification": state["architecture_justification"],
    }

    workflow_design = await designer.design_workflow(architecture, state["constraints"])

    # Create notebook plan
    notebook_plan = NotebookPlan(
        title=f"LangGraph Workflow: {state['user_prompt'][:50]}",
        sections=[
            "Setup",
            "State Definition",
            "Tools",
            "Nodes",
            "Graph Construction",
            "Execution",
        ],
        cell_count_estimate=len(workflow_design.get("nodes", [])) * 3 + 10,
        patterns_used=[state["selected_patterns"].get("primary", "router")],
        architecture_type=architecture["architecture_type"],
    )

    return {
        "workflow_design": workflow_design,
        "notebook_plan": notebook_plan,
    }


async def tooling_plan_node(state: GeneratorState) -> Dict[str, Any]:
    """Plan tools needed for the workflow.

    Args:
        state: Current generator state

    Returns:
        Updated state with tools plan
    """
    engineer = ToolchainEngineer()

    workflow_design = state.get("workflow_design", {})
    tools = await engineer.plan_tools(workflow_design, state["constraints"])

    return {"tools_plan": tools}


async def notebook_assembly_node(state: GeneratorState) -> Dict[str, Any]:
    """Generate notebook cells.

    Args:
        state: Current generator state

    Returns:
        Updated state with generated cells
    """
    composer = NotebookComposer()

    notebook_plan = state.get("notebook_plan")
    workflow_design = state.get("workflow_design", {})
    tools_plan = state.get("tools_plan", [])

    architecture = {
        "architecture_type": state["selected_patterns"].get("primary", "router"),
        "justification": state["architecture_justification"],
    }

    cells = await composer.compose_notebook(
        notebook_plan, workflow_design, tools_plan, architecture
    )

    return {"generated_cells": cells}


async def static_qa_node(state: GeneratorState) -> Dict[str, Any]:
    """Run static quality checks.

    Args:
        state: Current generator state

    Returns:
        Updated state with QA reports
    """
    qa_agent = QARepairAgent()

    cells = state.get("generated_cells", [])
    reports = await qa_agent.validate(cells)
    existing_reports = state.get("qa_reports") or []

    return {"qa_reports": [*existing_reports, *reports]}


async def runtime_qa_node(state: GeneratorState) -> Dict[str, Any]:
    """Run runtime quality checks (placeholder for now).

    Args:
        state: Current generator state

    Returns:
        Updated state with additional QA reports
    """
    # Placeholder: In a full implementation, this would execute the notebook
    # and check for runtime errors
    report = QAReport(
        check_name="Runtime Check",
        passed=True,
        message="Runtime checks placeholder (not yet implemented)",
    )

    existing_reports = state.get("qa_reports") or []
    return {"qa_reports": [*existing_reports, report]}


async def repair_node(state: GeneratorState) -> Dict[str, Any]:
    """Attempt to repair issues found in QA.

    Args:
        state: Current generator state

    Returns:
        Updated state with incremented repair attempts

    Note:
        Currently, this is a placeholder that increments repair_attempts.
        Full repair implementation would parse LLM suggestions and apply fixes.
        Due to operator.add on generated_cells, we only return repair_attempts.
    """
    qa_agent = QARepairAgent()

    cells = state.get("generated_cells", [])
    qa_reports = state.get("qa_reports", [])

    # Attempt repair (currently returns original cells as placeholder)
    await qa_agent.repair(cells, qa_reports)

    # Only increment repair attempts; don't return generated_cells to avoid
    # unwanted accumulation due to operator.add in state definition
    return {
        "repair_attempts": state["repair_attempts"] + 1,
    }


async def package_outputs_node(state: GeneratorState) -> Dict[str, Any]:
    """Package outputs into artifacts manifest.

    Args:
        state: Current generator state

    Returns:
        Updated state with artifacts manifest and completion flag
    """
    # Create artifacts manifest
    manifest = {
        "notebook_plan": str(state.get("notebook_plan")),
        "cell_count": str(len(state.get("generated_cells", []))),
        "architecture_type": state.get("architecture_type")
        or state.get("selected_patterns", {}).get("primary", "router"),
        "constraints_count": str(len(state.get("constraints", []))),
    }

    return {
        "artifacts_manifest": manifest,
        "generation_complete": True,
        "error_message": None,
    }
