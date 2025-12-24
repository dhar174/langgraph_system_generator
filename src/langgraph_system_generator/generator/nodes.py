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
    CellSpec,
    GeneratorState,
    NotebookPlan,
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
        from langgraph_system_generator.generator.state import DocSnippet

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
    except Exception:
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
    except Exception:
        retriever = None

    selector = ArchitectureSelector(docs_retriever=retriever)

    architecture = await selector.select_architecture(
        state["constraints"], state["docs_context"]
    )

    return {
        "selected_patterns": architecture.get("patterns", {}),
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

    architecture = {
        "architecture_type": state["selected_patterns"].get("primary", "router"),
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

    return {"qa_reports": reports}


async def runtime_qa_node(state: GeneratorState) -> Dict[str, Any]:
    """Run runtime quality checks (placeholder for now).

    Args:
        state: Current generator state

    Returns:
        Updated state with additional QA reports
    """
    # Placeholder: In a full implementation, this would execute the notebook
    # and check for runtime errors
    from langgraph_system_generator.generator.state import QAReport

    report = QAReport(
        check_name="Runtime Check",
        passed=True,
        message="Runtime checks placeholder (not yet implemented)",
    )

    return {"qa_reports": [report]}


async def repair_node(state: GeneratorState) -> Dict[str, Any]:
    """Attempt to repair issues found in QA.

    Args:
        state: Current generator state

    Returns:
        Updated state with repaired cells and incremented repair attempts
    """
    qa_agent = QARepairAgent()

    cells = state.get("generated_cells", [])
    qa_reports = state.get("qa_reports", [])

    repaired_cells = await qa_agent.repair(cells, qa_reports)

    return {
        "generated_cells": repaired_cells,
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
        "architecture": state["selected_patterns"].get("primary", "router"),
        "constraints_count": str(len(state.get("constraints", []))),
    }

    return {
        "artifacts_manifest": manifest,
        "generation_complete": True,
        "error_message": None,
    }

