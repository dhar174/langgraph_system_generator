"""Generator graph nodes implementing the workflow pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List

import nbformat

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
    DocSnippet,
    GeneratorState,
    NotebookPlan,
    QAReport,
)
from langgraph_system_generator.notebook.composer import (
    NotebookComposer as NotebookFileComposer,
)
from langgraph_system_generator.notebook.runtime import run_notebook_smoke_test
from langgraph_system_generator.qa import NotebookRepairAgent, NotebookValidator
from langgraph_system_generator.rag.embeddings import VectorStoreManager
from langgraph_system_generator.rag.retriever import DocsRetriever
from langgraph_system_generator.utils.config import settings

logger = logging.getLogger(__name__)


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


def _cells_from_notebook(path: Path) -> List[CellSpec]:
    """Read cells from a notebook file and convert to CellSpec list.
    
    Args:
        path: Path to the notebook file
        
    Returns:
        List of CellSpec objects parsed from the notebook
        
    Raises:
        ValueError: If the notebook cannot be read or parsed
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            notebook = nbformat.read(handle, as_version=4)
    except Exception as e:
        raise type(e)(f"Failed to read notebook from {path}: {type(e).__name__}: {e}") from e

    regenerated_cells: List[CellSpec] = []
    for cell in notebook.cells:
        metadata = dict(cell.metadata or {})
        section = metadata.pop("section", None)
        if isinstance(cell.source, str):
            content = cell.source
        else:
            # In nbformat, list elements represent lines and may not include trailing newlines.
            # If elements already contain newlines, preserve them; otherwise, join with "\n".
            if any("\n" in part for part in cell.source):
                content = "".join(cell.source)
            else:
                content = "\n".join(cell.source)
        regenerated_cells.append(
            CellSpec(
                cell_type=cell.cell_type,
                content=content,
                metadata=metadata,
                section=section,
            )
        )
    return regenerated_cells


async def static_qa_node(state: GeneratorState) -> Dict[str, Any]:
    """Run static quality checks.

    Args:
        state: Current generator state

    Returns:
        Updated state with QA reports
    """
    notebook_builder = NotebookFileComposer()
    validator = NotebookValidator()

    cells = state.get("generated_cells", [])
    with TemporaryDirectory() as temp_dir:
        notebook = notebook_builder.build_notebook(cells)
        notebook_path = Path(temp_dir) / "generated.ipynb"
        notebook_builder.write(notebook, notebook_path)
        
        # Log temp path for debugging failed validations
        logger.debug(f"Running validation on temporary notebook: {notebook_path}")
        
        reports = validator.validate_all(notebook_path)
        
        # If validation fails, log details for debugging
        if any(not r.passed for r in reports):
            logger.info(
                "Validation failed for temporary notebook at %s "
                "(stored in a TemporaryDirectory that will be removed after this step).",
                notebook_path,
            )
    
    existing_reports = state.get("qa_reports") or []

    return {"qa_reports": [*existing_reports, *reports]}


async def runtime_qa_node(state: GeneratorState) -> Dict[str, Any]:
    """Run runtime quality checks using a notebook execution smoke test.

    Args:
        state: Current generator state

    Returns:
        Updated state with additional QA reports
    """
    if not state.get("generated_cells"):
        message = "Runtime checks skipped: no generated cells to execute."
        report = QAReport(
            check_name="Runtime Check",
            passed=True,
            message=message,
        )
    else:
        passed, message = run_notebook_smoke_test()
        suggestions = []
        if not passed:
            suggestions = [
                "Install a healthy python3 Jupyter kernel before running runtime QA.",
                "Refresh the kernel spec with: python -m ipykernel install --user --name python3",
            ]
        report = QAReport(
            check_name="Runtime Check",
            passed=passed,
            message=message,
            suggestions=suggestions,
        )

    existing_reports = state.get("qa_reports") or []
    return {"qa_reports": [*existing_reports, report]}


async def repair_node(state: GeneratorState) -> Dict[str, Any]:
    """Attempt to repair issues found in QA.

    Args:
        state: Current generator state

    Returns:
        Updated state with incremented repair attempts and repaired notebook data.
    """
    repair_agent = NotebookRepairAgent()
    notebook_builder = NotebookFileComposer()

    cells = state.get("generated_cells", [])
    qa_reports = state.get("qa_reports", [])

    with TemporaryDirectory() as temp_dir:
        notebook = notebook_builder.build_notebook(cells)
        notebook_path = Path(temp_dir) / "generated.ipynb"
        notebook_builder.write(notebook, notebook_path)

        repair_success, updated_reports = repair_agent.repair_notebook(
            notebook_path,
            qa_reports,
            attempt=state["repair_attempts"],
        )
        
        # Only reload cells if repair was successful
        if repair_success:
            try:
                regenerated_cells = _cells_from_notebook(notebook_path)
            except ValueError as e:
                # If cell rehydration fails after successful repair, log and keep original cells
                logger.warning(f"Failed to reload cells after repair: {e}")
                regenerated_cells = cells
        else:
            # If repair failed (e.g., notebook not safely written), keep original cells
            logger.info(
                f"Repair attempt {state['repair_attempts']} failed. "
                "Keeping original cells for potential retry."
            )
            regenerated_cells = cells

    return {
        "generated_cells": regenerated_cells,
        "qa_reports": updated_reports,
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
