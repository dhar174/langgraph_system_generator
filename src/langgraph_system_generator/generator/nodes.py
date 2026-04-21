"""Generator graph nodes implementing the workflow pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List

import nbformat

from langgraph_system_generator.generator.agents import (
    ArchitectureSelector,
    GraphDesigner,
    NotebookComposer,
    RequirementsAnalyst,
    ToolchainEngineer,
)
from langgraph_system_generator.generator.architecture_registry import (
    get_default_architecture_registry,
)
from langgraph_system_generator.generator.state import (
    ArchitectureFeedback,
    CellSpec,
    DocSnippet,
    GeneratorState,
    NotebookPlan,
    QAReport,
)
from langgraph_system_generator.notebook.composer import (
    NotebookComposer as NotebookFileComposer,
)
from langgraph_system_generator.notebook.runtime import (
    inspect_notebook_runtime_support,
    run_notebook_smoke_test,
)
from langgraph_system_generator.qa import NotebookRepairAgent, NotebookValidator
from langgraph_system_generator.rag.embeddings import VectorStoreManager
from langgraph_system_generator.rag.retriever import DocsRetriever
from langgraph_system_generator.utils.generation_options import (
    SUPPORTED_AGENT_TYPES,
    normalize_agent_type,
)
from langgraph_system_generator.utils.config import settings

logger = logging.getLogger(__name__)

RUNTIME_UNAVAILABLE_PREFIX = "runtime validation unavailable"
TRUSTED_SMOKE_TEST_SCOPE = "trusted_smoke_test"
ARCHITECTURE_REGISTRY = get_default_architecture_registry()


def _resolve_model_config(state: GeneratorState):
    """Build a per-request model config for live agent construction."""
    generation_config = state.get("generation_config")
    if generation_config is None:
        return None
    return generation_config.to_model_config(settings.default_model)


def _requested_architecture_type(state: GeneratorState) -> str | None:
    """Return an explicit architecture override when provided."""
    generation_config = state.get("generation_config")
    if generation_config is None:
        return None

    requested = normalize_agent_type(generation_config.agent_type)
    if requested in SUPPORTED_AGENT_TYPES:
        return requested
    return None


def _runtime_qa_suggestions(message: str) -> List[str]:
    """Return remediation guidance tailored to the runtime QA failure message."""

    normalized = message.lower()
    if "kernel" in normalized and (
        "not registered" in normalized
        or "no launch command" in normalized
        or "missing executable" in normalized
    ):
        return [
            "Install a healthy python3 Jupyter kernel before running runtime QA.",
            "Refresh the kernel spec with: python -m ipykernel install --user --name python3",
        ]

    if (
        "missing jupyter_client" in normalized
        or "missing notebook execution dependency" in normalized
    ):
        return [
            "Install notebook runtime dependencies such as jupyter_client and nbclient.",
            'Reinstall the project extras with: pip install -e ".[full]"',
        ]

    return [
        "Review the runtime QA error details and rerun notebook execution after fixing the reported issue.",
        "If the environment is managed externally, verify the selected python3 kernel can execute notebooks successfully.",
    ]


def _generation_mode(state: GeneratorState) -> str:
    """Return the current generation mode with a safe live default."""

    raw_mode = state.get("generation_mode")
    normalized_mode = raw_mode.strip().lower() if isinstance(raw_mode, str) else ""
    return "stub" if normalized_mode == "stub" else "live"


def _qa_history_from_state(state: GeneratorState) -> List[QAReport]:
    """Return accumulated QA history, falling back to legacy qa_reports state."""

    if "qa_history" in state and state.get("qa_history") is not None:
        return list(state.get("qa_history") or [])
    return list(state.get("qa_reports") or [])


def _stamp_report(
    report: QAReport,
    *,
    stage: str,
    attempt: int,
    evidence: Dict[str, Any] | None = None,
) -> QAReport:
    """Attach structured QA metadata while preserving any existing evidence."""

    merged_evidence = report.evidence.copy()
    if evidence:
        merged_evidence.update(evidence)

    return report.model_copy(
        update={
            "stage": report.stage or stage,
            "attempt": attempt if report.attempt is None else report.attempt,
            "evidence": merged_evidence,
        }
    )


def _stamp_reports(
    reports: List[QAReport],
    *,
    stage: str,
    attempt: int,
) -> List[QAReport]:
    """Attach stage/attempt metadata to a batch of reports."""

    return [_stamp_report(report, stage=stage, attempt=attempt) for report in reports]


async def intake_node(state: GeneratorState) -> Dict[str, Any]:
    """Initial intake and constraint extraction.

    Args:
        state: Current generator state

    Returns:
        Updated state with extracted constraints
    """
    analyst = RequirementsAnalyst(model_config=_resolve_model_config(state))
    analysis = await analyst.analyze(state["user_prompt"])

    return {
        "constraints": analysis.constraints,
        "requirements_feedback": analysis.feedback,
    }


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
        logger.warning("RAG retrieval failed: %s", e)
        # If RAG fails, continue without docs
        return {"docs_context": []}


async def architecture_selection_node(state: GeneratorState) -> Dict[str, Any]:
    """Select optimal architecture pattern.

    Args:
        state: Current generator state

    Returns:
        Updated state with architecture selection and justification
    """
    requested_architecture = _requested_architecture_type(state)
    if requested_architecture:
        primary, secondary = ARCHITECTURE_REGISTRY.normalize_patterns(
            requested_architecture
        )
        return {
            "selected_patterns": {"primary": primary, "secondary": secondary},
            "architecture_type": primary,
            "architecture_justification": (
                f"Architecture forced by request-scoped agent_type override: {primary}."
            ),
            "architecture_feedback": ArchitectureFeedback(
                confidence=1.0,
                tradeoffs=[
                    "Selection was forced by request-scoped agent_type override; automatic ranking was skipped."
                ],
                docs_considered=[],
            ),
        }

    try:
        vector_store_manager = VectorStoreManager(settings.vector_store_path)
        retriever = DocsRetriever(vector_store_manager)
    except Exception as e:
        logger.warning(
            "Failed to load vector store for architecture selection: %s",
            e,
        )
        retriever = None

    selector = ArchitectureSelector(
        docs_retriever=retriever,
        model_config=_resolve_model_config(state),
    )

    architecture = await selector.select_architecture(
        state["constraints"], state["docs_context"]
    )

    selected_patterns = architecture.patterns.model_dump()
    architecture_type = architecture.architecture_type

    return {
        "selected_patterns": selected_patterns,
        "architecture_type": architecture_type,
        "architecture_justification": architecture.justification,
        "architecture_feedback": architecture.feedback,
    }


async def graph_design_node(state: GeneratorState) -> Dict[str, Any]:
    """Design the inner workflow.

    Args:
        state: Current generator state

    Returns:
        Updated state with workflow design and notebook plan
    """
    designer = GraphDesigner(model_config=_resolve_model_config(state))

    selected_patterns = state.get("selected_patterns", {}) or {}
    architecture_type = state.get("architecture_type")
    if not architecture_type:
        architecture_type = selected_patterns.get("primary", "router")
    architecture = {
        "architecture_type": architecture_type,
        "justification": state["architecture_justification"],
        "selected_patterns": selected_patterns,
    }

    workflow_design = await designer.design_workflow(architecture, state["constraints"])
    if selected_patterns.get("primary") == "hybrid":
        workflow_design.setdefault("selected_patterns", selected_patterns)

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
        patterns_used=[state.get("selected_patterns", {}).get("primary", "router")],
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
    engineer = ToolchainEngineer(model_config=_resolve_model_config(state))

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
    composer = NotebookComposer(model_config=_resolve_model_config(state))

    notebook_plan = state.get("notebook_plan")
    workflow_design = state.get("workflow_design", {})
    tools_plan = state.get("tools_plan", [])

    architecture = {
        "architecture_type": state.get("architecture_type")
        or state.get("selected_patterns", {}).get("primary", "router"),
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
        raise type(e)(
            f"Failed to read notebook from {path}: {type(e).__name__}: {e}"
        ) from e

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

    annotated_reports = _stamp_reports(
        reports,
        stage="static",
        attempt=int(state.get("repair_attempts", 0)),
    )
    qa_history = [*_qa_history_from_state(state), *annotated_reports]

    return {
        "qa_reports": annotated_reports,
        "qa_history": qa_history,
    }


async def runtime_qa_node(state: GeneratorState) -> Dict[str, Any]:
    """Run runtime quality checks with a trusted notebook smoke test.

    Args:
        state: Current generator state

    Returns:
        Updated state with additional QA reports
    """
    attempt = int(state.get("repair_attempts", 0))
    generation_mode = _generation_mode(state)
    existing_reports = list(state.get("qa_reports") or [])

    if not state.get("generated_cells"):
        report = _stamp_report(
            QAReport(
                check_name="Runtime Check",
                passed=True,
                message="Runtime checks skipped: no generated cells to execute.",
            ),
            stage="runtime",
            attempt=attempt,
            evidence={"generation_mode": generation_mode, "failure_kind": "no_cells"},
        )
    else:
        preflight_ok, preflight_message, preflight_evidence = await asyncio.to_thread(
            inspect_notebook_runtime_support
        )

        if not preflight_ok:
            suggestions = _runtime_qa_suggestions(preflight_message)
            passed = generation_mode != "live"
            message = (
                f"Runtime checks skipped: {preflight_message}"
                if passed
                else preflight_message
            )
            report = _stamp_report(
                QAReport(
                    check_name="Runtime Check",
                    passed=passed,
                    message=message,
                    suggestions=suggestions,
                ),
                stage="runtime",
                attempt=attempt,
                evidence={
                    "generation_mode": generation_mode,
                    "failure_kind": "runtime_unavailable",
                    "preflight": preflight_evidence,
                },
            )
        else:
            smoke_passed, smoke_message = await asyncio.to_thread(run_notebook_smoke_test)
            runtime_unavailable = smoke_message.lower().startswith(
                RUNTIME_UNAVAILABLE_PREFIX
            )
            passed = smoke_passed or (runtime_unavailable and generation_mode != "live")
            message = (
                f"Runtime checks skipped: {smoke_message}"
                if runtime_unavailable and passed
                else smoke_message
            )
            failure_kind = (
                "runtime_unavailable"
                if runtime_unavailable
                else ("execution_passed" if passed else "execution_failed")
            )
            report = _stamp_report(
                QAReport(
                    check_name="Runtime Check",
                    passed=passed,
                    message=message,
                    suggestions=[] if passed else _runtime_qa_suggestions(smoke_message),
                ),
                stage="runtime",
                attempt=attempt,
                evidence={
                    "generation_mode": generation_mode,
                    "failure_kind": failure_kind,
                    "preflight": preflight_evidence,
                    "execution": {
                        "execution_scope": TRUSTED_SMOKE_TEST_SCOPE,
                        "message": smoke_message,
                    },
                },
            )

    qa_history = [*_qa_history_from_state(state), report]
    return {"qa_reports": [*existing_reports, report], "qa_history": qa_history}


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
    qa_reports = list(state.get("qa_reports", []))
    attempt = int(state.get("repair_attempts", 0))

    with TemporaryDirectory() as temp_dir:
        notebook = notebook_builder.build_notebook(cells)
        notebook_path = Path(temp_dir) / "generated.ipynb"
        notebook_builder.write(notebook, notebook_path)

        repair_success, updated_reports = repair_agent.repair_notebook(
            notebook_path,
            qa_reports,
            attempt=attempt,
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
                f"Repair attempt {attempt} failed. "
                "Keeping original cells for potential retry."
            )
            regenerated_cells = cells

    normalized_reports = _stamp_reports(
        updated_reports,
        stage="static",
        attempt=attempt + 1,
    )
    repair_summary = _stamp_report(
        QAReport(
            check_name="Repair Attempt",
            passed=repair_success,
            message=(
                "Notebook repair produced an updated notebook snapshot."
                if repair_success
                else "Notebook repair could not resolve the current QA failures."
            ),
            suggestions=[] if repair_success else ["Inspect the latest QA reports before retrying."],
        ),
        stage="repair",
        attempt=attempt,
        evidence={
            "repair_success": repair_success,
            "input_report_count": len(qa_reports),
            "output_report_count": len(normalized_reports),
            "regenerated_cell_count": len(regenerated_cells),
        },
    )

    return {
        "generated_cells": regenerated_cells,
        "qa_reports": normalized_reports,
        "qa_history": [*_qa_history_from_state(state), repair_summary],
        "repair_attempts": attempt + 1,
    }


async def package_outputs_node(state: GeneratorState) -> Dict[str, Any]:
    """Package outputs into artifacts manifest.

    Args:
        state: Current generator state

    Returns:
        Updated state with artifacts manifest and completion flag
    """
    # Create artifacts manifest
    requirements_feedback = state.get("requirements_feedback")
    architecture_feedback = state.get("architecture_feedback")
    manifest = {
        "notebook_plan": str(state.get("notebook_plan")),
        "cell_count": str(len(state.get("generated_cells", []))),
        "architecture_type": state.get("architecture_type")
        or state.get("selected_patterns", {}).get("primary", "router"),
        "constraints_count": str(len(state.get("constraints", []))),
        "requirements_feedback": (
            requirements_feedback.model_dump()
            if hasattr(requirements_feedback, "model_dump")
            else (requirements_feedback or {})
        ),
        "architecture_feedback": (
            architecture_feedback.model_dump()
            if hasattr(architecture_feedback, "model_dump")
            else (architecture_feedback or {})
        ),
    }

    return {
        "artifacts_manifest": manifest,
        "generation_complete": True,
        "error_message": None,
    }
