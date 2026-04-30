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
    GraphDesignFeedback,
    GraphExportBundle,
    NotebookCompositionFeedback,
    NotebookDependencyPlan,
    NotebookPlan,
    QAReport,
    QARepairFeedback,
    ToolPlanningFeedback,
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
    resolve_architecture_type,
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


def _qa_repair_feedback_from_state(state: GeneratorState) -> QARepairFeedback:
    """Return structured QA/repair feedback from state or a safe default."""

    feedback = state.get("qa_repair_feedback")
    if isinstance(feedback, QARepairFeedback):
        return feedback
    if isinstance(feedback, dict):
        return QARepairFeedback.model_validate(feedback)
    if hasattr(feedback, "model_dump"):
        return QARepairFeedback.model_validate(feedback.model_dump())
    return QARepairFeedback()


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


def _qa_repair_feedback_from_reports(
    reports: List[QAReport],
    *,
    repair_attempts: int,
    existing_feedback: QARepairFeedback | None = None,
    rollback_used: bool = False,
    extra_warnings: List[str] | None = None,
    extra_next_steps: List[str] | None = None,
) -> QARepairFeedback:
    """Build compact QA/repair feedback from the current report set."""

    unresolved_failures: List[str] = []
    next_steps: List[str] = []
    warnings: List[str] = []
    advisory_failures: List[str] = []

    for report in reports:
        if report.passed:
            continue

        descriptor = f"{report.check_name}: {report.message}"
        if report.severity == "error":
            if descriptor not in unresolved_failures:
                unresolved_failures.append(descriptor)
        else:
            if descriptor not in advisory_failures:
                advisory_failures.append(descriptor)

        for suggestion in report.suggestions:
            suggestion_text = str(suggestion or "").strip()
            if suggestion_text and suggestion_text not in next_steps:
                next_steps.append(suggestion_text)

    if unresolved_failures:
        warnings.append("Blocking QA issues remain after validation or repair.")
    if advisory_failures:
        warnings.append("Additional non-blocking QA advisories were recorded.")
    if rollback_used:
        warnings.append("A repair rollback preserved the previous notebook snapshot.")
    for warning in extra_warnings or []:
        warning_text = str(warning or "").strip()
        if warning_text and warning_text not in warnings:
            warnings.append(warning_text)
    for step in extra_next_steps or []:
        step_text = str(step or "").strip()
        if step_text and step_text not in next_steps:
            next_steps.append(step_text)

    prior = existing_feedback or QARepairFeedback()
    return QARepairFeedback(
        repair_attempts=repair_attempts,
        rollback_used=prior.rollback_used or rollback_used,
        unrepaired_failures=unresolved_failures,
        next_steps=next_steps,
        warnings=warnings,
    )


def _qa_repair_summary_markdown(
    feedback: QARepairFeedback,
    *,
    status: str,
) -> str:
    """Render a notebook-visible QA and repair summary."""

    if status == "applied":
        status_line = "Applied a non-regressive deterministic repair."
    elif status == "rolled_back":
        status_line = "Rolled back the repair candidate to preserve the last safe notebook snapshot."
    elif status == "skipped":
        status_line = "Skipped repair because no safe deterministic fix matched the current QA failures."
    else:
        status_line = "No repair was needed for the current notebook snapshot."

    lines = [
        "## QA and Repair Summary",
        "",
        f"Status: {status_line}",
        f"Repair attempts so far: {feedback.repair_attempts}",
        f"Rollback used: {'Yes' if feedback.rollback_used else 'No'}",
    ]

    if feedback.unrepaired_failures:
        lines.extend(
            [
                "",
                "Blocking unresolved failures:",
                *[f"- {failure}" for failure in feedback.unrepaired_failures],
            ]
        )
    else:
        lines.extend(["", "Blocking unresolved failures: none."])

    if feedback.next_steps:
        lines.extend(
            [
                "",
                "Next steps:",
                *[f"- {step}" for step in feedback.next_steps],
            ]
        )
    elif status == "applied":
        lines.extend(["", "Next steps: no manual follow-up is currently required."])

    return "\n".join(lines)


def _upsert_qa_repair_summary_cell(
    cells: List[CellSpec],
    feedback: QARepairFeedback,
    *,
    status: str,
) -> List[CellSpec]:
    """Replace any existing QA repair summary cell with the latest summary."""

    retained_cells = [
        cell.model_copy(deep=True)
        for cell in cells
        if cell.section != "qa_repair_summary"
        and cell.metadata.get("kind") != "qa_repair_summary"
        and cell.metadata.get("section") != "qa_repair_summary"
    ]
    retained_cells.append(
        CellSpec(
            cell_type="markdown",
            content=_qa_repair_summary_markdown(feedback, status=status),
            metadata={"section": "qa_repair_summary", "kind": "qa_repair_summary"},
            section="qa_repair_summary",
        )
    )
    return retained_cells


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
    architecture_type = resolve_architecture_type(
        state.get("architecture_type"),
        selected_patterns,
    )
    architecture = {
        "architecture_type": architecture_type,
        "justification": state["architecture_justification"],
        "selected_patterns": selected_patterns,
    }

    design_result = await designer.design_workflow(architecture, state["constraints"])
    workflow_design = design_result.to_workflow_design_payload()
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
        cell_count_estimate=len(design_result.nodes) * 3 + 10,
        patterns_used=[architecture_type],
        architecture_type=architecture["architecture_type"],
    )

    return {
        "workflow_design": workflow_design,
        "graph_design_feedback": design_result.feedback,
        "graph_exports": design_result.exports,
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

    workflow_design = state.get("workflow_design") or {}
    planning = await engineer.plan_tools(workflow_design, state["constraints"])

    return {
        "tools_plan": planning.to_tools_plan_payload(),
        "tool_planning_feedback": planning.feedback,
    }


async def notebook_assembly_node(state: GeneratorState) -> Dict[str, Any]:
    """Generate notebook cells.

    Args:
        state: Current generator state

    Returns:
        Updated state with generated cells
    """
    composer = NotebookComposer(model_config=_resolve_model_config(state))

    notebook_plan = state.get("notebook_plan")
    workflow_design = dict(state.get("workflow_design", {}) or {})
    graph_exports = state.get("graph_exports")
    if graph_exports and "graph_exports" not in workflow_design:
        workflow_design["graph_exports"] = (
            graph_exports.model_dump(by_alias=True)
            if hasattr(graph_exports, "model_dump")
            else graph_exports
        )
    tools_plan = state.get("tools_plan", [])
    tool_planning_feedback = state.get("tool_planning_feedback")

    architecture = {
        "architecture_type": resolve_architecture_type(
            state.get("architecture_type"),
            state.get("selected_patterns", {}) or {},
        ),
        "justification": state["architecture_justification"],
    }

    composition = await composer.compose_notebook(
        notebook_plan,
        workflow_design,
        tools_plan,
        architecture,
        tool_planning_feedback=tool_planning_feedback,
    )

    return {
        "generated_cells": composition.cells,
        "notebook_composition_feedback": composition.feedback,
        "notebook_dependency_plan": composition.dependency_plan,
    }


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
    qa_repair_feedback = _qa_repair_feedback_from_reports(
        annotated_reports,
        repair_attempts=int(state.get("repair_attempts", 0)),
        existing_feedback=_qa_repair_feedback_from_state(state),
    )

    return {
        "qa_reports": annotated_reports,
        "qa_history": qa_history,
        "qa_repair_feedback": qa_repair_feedback,
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
                rule_id="runtime_smoke_test",
                severity="info",
                category="runtime",
                repairable=False,
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
                    rule_id="runtime_smoke_test",
                    severity="info" if passed else "error",
                    category="runtime",
                    repairable=False,
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
                    rule_id="runtime_smoke_test",
                    severity="info" if passed else "error",
                    category="runtime",
                    repairable=False,
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

    combined_reports = [*existing_reports, report]
    qa_history = [*_qa_history_from_state(state), report]
    qa_repair_feedback = _qa_repair_feedback_from_reports(
        combined_reports,
        repair_attempts=attempt,
        existing_feedback=_qa_repair_feedback_from_state(state),
    )
    return {
        "qa_reports": combined_reports,
        "qa_history": qa_history,
        "qa_repair_feedback": qa_repair_feedback,
    }


async def repair_node(state: GeneratorState) -> Dict[str, Any]:
    """Attempt to repair issues found in QA.

    Args:
        state: Current generator state

    Returns:
        Updated state with incremented repair attempts and repaired notebook data.
    """
    repair_agent = NotebookRepairAgent()

    cells = state.get("generated_cells", [])
    qa_reports = list(state.get("qa_reports", []))
    attempt = int(state.get("repair_attempts", 0))
    outcome = repair_agent.repair_cells(cells, qa_reports, attempt=attempt)

    normalized_reports = _stamp_reports(
        outcome.qa_reports,
        stage="static",
        attempt=attempt + 1,
    )
    extra_warnings: List[str] = []
    if outcome.status == "rolled_back":
        extra_warnings.append(
            "Repair candidate was rolled back after validation to preserve the last safe notebook snapshot."
        )
    elif outcome.status == "skipped":
        extra_warnings.append(outcome.message)

    repair_summary = _stamp_report(
        QAReport(
            check_name="Repair Attempt",
            passed=outcome.success,
            message=outcome.message,
            rule_id="repair_attempt",
            severity="info" if outcome.success else "warning",
            category="repair",
            repairable=False,
            suggestions=outcome.next_steps,
        ),
        stage="repair",
        attempt=attempt + 1,
        evidence={
            "repair_success": outcome.success,
            "repair_status": outcome.status,
            "attempted_fixes": outcome.attempted_fixes,
            "validation_after_repair": outcome.validation_summary,
            "rollback_used": outcome.rollback_used,
            "persisted_repaired_cells": outcome.persisted,
            "input_report_count": len(qa_reports),
            "output_report_count": len(normalized_reports),
            "regenerated_cell_count": len(outcome.cells),
        },
    )
    qa_repair_feedback = _qa_repair_feedback_from_reports(
        normalized_reports,
        repair_attempts=attempt + 1,
        existing_feedback=_qa_repair_feedback_from_state(state),
        rollback_used=outcome.rollback_used,
        extra_warnings=extra_warnings,
        extra_next_steps=outcome.next_steps,
    )
    regenerated_cells = _upsert_qa_repair_summary_cell(
        outcome.cells,
        qa_repair_feedback,
        status=outcome.status,
    )

    return {
        "generated_cells": regenerated_cells,
        "qa_reports": normalized_reports,
        "qa_history": [*_qa_history_from_state(state), repair_summary],
        "repair_attempts": attempt + 1,
        "qa_repair_feedback": qa_repair_feedback,
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
    graph_design_feedback = state.get("graph_design_feedback")
    graph_exports = state.get("graph_exports")
    tool_planning_feedback = state.get("tool_planning_feedback")
    notebook_composition_feedback = state.get("notebook_composition_feedback")
    notebook_dependency_plan = state.get("notebook_dependency_plan")
    qa_repair_feedback = state.get("qa_repair_feedback")
    manifest = {
        "notebook_plan": str(state.get("notebook_plan")),
        "cell_count": str(len(state.get("generated_cells", []))),
        "architecture_type": resolve_architecture_type(
            state.get("architecture_type"),
            state.get("selected_patterns", {}) or {},
        ),
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
        "graph_design_feedback": (
            graph_design_feedback.model_dump()
            if hasattr(graph_design_feedback, "model_dump")
            else (
                graph_design_feedback
                or GraphDesignFeedback(fallback_used=False).model_dump()
            )
        ),
        "graph_exports": (
            graph_exports.model_dump(by_alias=True)
            if hasattr(graph_exports, "model_dump")
            else (graph_exports or GraphExportBundle().model_dump(by_alias=True))
        ),
        "tool_planning_feedback": (
            tool_planning_feedback.model_dump()
            if hasattr(tool_planning_feedback, "model_dump")
            else (
                tool_planning_feedback
                or ToolPlanningFeedback(available_tool_ids=[]).model_dump()
            )
        ),
        "notebook_composition_feedback": (
            notebook_composition_feedback.model_dump()
            if hasattr(notebook_composition_feedback, "model_dump")
            else (
                notebook_composition_feedback
                or NotebookCompositionFeedback(fallback_used=False).model_dump()
            )
        ),
        "notebook_dependency_plan": (
            notebook_dependency_plan.model_dump()
            if hasattr(notebook_dependency_plan, "model_dump")
            else (
                notebook_dependency_plan or NotebookDependencyPlan().model_dump()
            )
        ),
        "qa_repair_feedback": (
            qa_repair_feedback.model_dump()
            if hasattr(qa_repair_feedback, "model_dump")
            else (
                qa_repair_feedback or QARepairFeedback().model_dump()
            )
        ),
    }

    return {
        "artifacts_manifest": manifest,
        "generation_complete": True,
        "error_message": None,
    }
