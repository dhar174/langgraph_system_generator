"""Command-line interface for LangGraph Notebook Foundry.

Provides lightweight commands to generate notebook artifacts (stub by default)
and to build the documentation index from cached docs.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Literal, TypedDict

from langgraph_system_generator.generator.state import (
    ArchitectureFeedback,
    build_constraint_type_registry,
    CellSpec,
    Constraint,
    NotebookPlan,
    RequirementsFeedback,
)
from langgraph_system_generator.generator.architecture_registry import (
    get_default_architecture_registry,
)
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.config import GenerationConfig, settings
from langgraph_system_generator.utils.generation_options import (
    SUPPORTED_AGENT_TYPES,
    normalize_agent_type,
)
from langgraph_system_generator.utils.logging import configure_logging
from langgraph_system_generator.utils.optional_deps import (
    OptionalDependencyError,
    require_optional_module,
)

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = (BASE_DIR / "data" / "cached_docs").resolve()
logger = logging.getLogger(__name__)

GenerationMode = Literal["stub", "live"]


class GenerationArtifacts(TypedDict):
    """Serialized generation results written by the CLI/API."""

    mode: GenerationMode
    prompt: str
    manifest: Dict[str, Any]
    manifest_path: str
    output_dir: str
    result: Dict[str, Any]


def _available_constraint_types() -> List[str]:
    """Return the normalized intake constraint registry for manifests and defaults."""

    return build_constraint_type_registry(settings.requirements_constraint_types)


def _default_state(
    prompt: str,
    generation_config: GenerationConfig | None = None,
    generation_mode: GenerationMode = "live",
) -> Dict[str, Any]:
    """Return a baseline GeneratorState payload."""

    return {
        "user_prompt": prompt,
        "uploaded_files": None,
        "constraints": [],
        "requirements_feedback": RequirementsFeedback(
            fallback_used=False,
            available_constraint_types=_available_constraint_types(),
        ),
        "architecture_feedback": ArchitectureFeedback(fallback_used=False),
        "selected_patterns": {},
        "docs_context": [],
        "notebook_plan": None,
        "architecture_justification": "",
        "architecture_type": None,
        "generation_config": generation_config,
        "generation_mode": generation_mode,
        "workflow_design": None,
        "tools_plan": None,
        "generated_cells": [],
        "qa_reports": [],
        "qa_history": [],
        "repair_attempts": 0,
        "artifacts_manifest": {},
        "generation_complete": False,
        "error_message": None,
    }


def _serialize(obj: Any) -> Any:
    """Recursively convert Pydantic models and objects into plain dicts/lists."""

    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _serialize(val) for key, val in obj.items()}
    return obj


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _utc_now_iso() -> str:
    """Return a UTC timestamp string for telemetry payloads."""

    return datetime.now(timezone.utc).isoformat()


def _normalize_generation_error(
    exc: Exception,
    *,
    phase: str,
    default_code: str = "generation_error",
    default_status_code: int = 500,
) -> GenerationError:
    """Normalize arbitrary exceptions into a structured generation error."""

    if isinstance(exc, GenerationError):
        return exc

    if isinstance(exc, OptionalDependencyError):
        details = {}
        if exc.dependency:
            details["dependency"] = exc.dependency
        if exc.extra:
            details["extra"] = exc.extra
        if exc.feature:
            details["feature"] = exc.feature
        return GenerationError(
            str(exc),
            code="dependency_unavailable",
            phase=phase,
            hint=exc.hint,
            details=details,
            status_code=503,
        )

    return GenerationError(
        str(exc),
        code=default_code,
        phase=phase,
        details={"error_type": type(exc).__name__},
        status_code=default_status_code,
    )


def _requirements_warning_entries(
    feedback: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    """Convert structured requirements feedback into manifest warnings."""

    if not isinstance(feedback, dict):
        return []

    warnings: List[Dict[str, Any]] = []
    suggestions = list(feedback.get("suggestions") or [])
    if feedback.get("fallback_used"):
        warnings.append(
            {
                "code": "requirements_fallback",
                "phase": "intake",
                "message": feedback.get("fallback_reason")
                or "Requirements extraction used a fallback goal constraint.",
                "suggestions": suggestions,
            }
        )

    missing_inputs = list(feedback.get("missing_inputs") or [])
    if missing_inputs:
        warnings.append(
            {
                "code": "requirements_missing_inputs",
                "phase": "intake",
                "message": "Missing core requirement categories: "
                + ", ".join(missing_inputs),
                "missing_inputs": missing_inputs,
                "suggestions": suggestions,
            }
        )

    conflicts = list(feedback.get("conflicts") or [])
    if conflicts:
        warnings.append(
            {
                "code": "requirements_conflicts",
                "phase": "intake",
                "message": "Conflicting requirements were detected during intake.",
                "conflicts": conflicts,
                "suggestions": suggestions,
            }
        )

    return warnings


def _architecture_warning_entries(
    feedback: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    """Convert structured architecture feedback into manifest warnings."""

    if not isinstance(feedback, dict):
        return []

    warnings: List[Dict[str, Any]] = []
    tradeoffs = list(feedback.get("tradeoffs") or [])
    docs_considered = list(feedback.get("docs_considered") or [])

    if feedback.get("fallback_used"):
        warnings.append(
            {
                "code": "architecture_fallback",
                "phase": "architecture_selection",
                "message": feedback.get("fallback_reason")
                or "Architecture selection used a router fallback.",
                "tradeoffs": tradeoffs,
                "docs_considered": docs_considered,
            }
        )

    validation_errors = list(feedback.get("validation_errors") or [])
    if validation_errors:
        warnings.append(
            {
                "code": "architecture_validation",
                "phase": "architecture_selection",
                "message": "Architecture selection reported validation issues.",
                "validation_errors": validation_errors,
                "tradeoffs": tradeoffs,
                "docs_considered": docs_considered,
            }
        )

    return warnings


class _PhaseTracker:
    """Track structured phase telemetry across generation and export steps."""

    def __init__(self, progress_callback: Any | None = None) -> None:
        self.progress_callback = progress_callback
        self._active: Dict[str, tuple[float, str]] = {}
        self.summary: List[Dict[str, Any]] = []

    def _emit_progress(
        self,
        phase: str,
        percentage: int,
        message: str,
        *,
        status: str = "running",
        event: str = "progress",
        details: Dict[str, Any] | None = None,
    ) -> None:
        if not self.progress_callback:
            return

        payload = {
            "event": event,
            "phase": phase,
            "node": phase,
            "percentage": min(100, max(0, percentage)),
            "message": message,
            "status": status,
        }
        if details:
            payload["details"] = details

        try:
            self.progress_callback(payload)
        except TypeError:
            self.progress_callback(phase, payload["percentage"], message)
        except Exception:
            logger.warning(
                "Progress callback failed for phase=%s percentage=%s",
                phase,
                percentage,
                exc_info=True,
            )

    def _log_phase(
        self,
        phase: str,
        status: str,
        message: str,
        *,
        duration_ms: int = 0,
        details: Dict[str, Any] | None = None,
    ) -> None:
        logger.info(
            "Generation phase %s: %s",
            status,
            phase,
            extra={
                "phase": phase,
                "status": status,
                "duration_ms": duration_ms,
                "phase_message": message,
                "phase_details": details or {},
            },
        )

    def start(
        self,
        phase: str,
        message: str,
        *,
        percentage: int | None = None,
        details: Dict[str, Any] | None = None,
    ) -> None:
        started_at = _utc_now_iso()
        self._active[phase] = (perf_counter(), started_at)
        self._log_phase(phase, "started", message, details=details)
        if percentage is not None:
            self._emit_progress(
                phase,
                percentage,
                message,
                status="running",
                details=details,
            )

    def finish(
        self,
        phase: str,
        message: str,
        *,
        percentage: int | None = None,
        status: str = "completed",
        details: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        timer_start, started_at = self._active.pop(phase, (perf_counter(), _utc_now_iso()))
        duration_ms = int((perf_counter() - timer_start) * 1000)
        finished_at = _utc_now_iso()
        entry = {
            "phase": phase,
            "status": status,
            "message": message,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "details": details or {},
        }
        self.summary.append(entry)
        self._log_phase(
            phase,
            status,
            message,
            duration_ms=duration_ms,
            details=details,
        )
        if percentage is not None:
            event_type = "log" if status == "warning" else "progress"
            self._emit_progress(
                phase,
                percentage,
                message,
                status=status,
                event=event_type,
                details=details,
            )
        return entry


def _infer_stub_architecture(prompt: str) -> tuple[str, str]:
    """Lightweight heuristic to pick an architecture in stub mode."""

    text = prompt.lower()
    if "autoagent" in text or "auto agent" in text:
        return (
            "autoagent",
            "AutoAgent pattern selected based on explicit AutoAgent intent in the prompt.",
        )
    if any(
        keyword in text for keyword in ["delegate", "supervisor", "team", "subagent"]
    ):
        return (
            "subagents",
            "Subagents pattern selected based on collaborative/delegation cues in the prompt.",
        )
    if any(keyword in text for keyword in ["hybrid", "combined", "mix", "multi-stage"]):
        return (
            "hybrid",
            "Hybrid pattern selected for mixed or multi-stage requirements detected in the prompt.",
        )
    if any(
        keyword in text
        for keyword in ["router", "route", "triage", "dispatch", "classification"]
    ):
        return (
            "router",
            "Router pattern selected for routing/triage style requests in the prompt.",
        )
    return (
        "router",
        "Router pattern selected as a sensible default for general workflows.",
    )


def _load_patterns() -> tuple[Any, Any, Any, Any]:
    """Import pattern generators lazily to preserve minimal installs."""
    patterns_module = require_optional_module(
        "langgraph_system_generator.patterns",
        feature="Stub artifact generation",
        extra="full",
    )
    return (
        patterns_module.RouterPattern,
        patterns_module.SubagentsPattern,
        patterns_module.HybridPattern,
        patterns_module.AutoAgentPattern,
    )


def _load_generator_graph() -> Any:
    """Import the live generator graph lazily."""
    graph_module = require_optional_module(
        "langgraph_system_generator.generator.graph",
        feature="Live generation",
        extra="full",
    )
    return graph_module.create_generator_graph


def _build_stub_result(prompt: str, agent_type: str | None = None) -> Dict[str, Any]:
    """Create a deterministic, offline-friendly generation result."""
    RouterPattern, SubagentsPattern, HybridPattern, AutoAgentPattern = _load_patterns()
    architecture_registry = get_default_architecture_registry()

    normalized_agent_type = normalize_agent_type(agent_type)
    if normalized_agent_type in SUPPORTED_AGENT_TYPES:
        architecture_type = normalized_agent_type
        _, secondary_patterns = architecture_registry.normalize_patterns(architecture_type)
        justification = (
            f"{normalized_agent_type.title()} pattern selected from the requested "
            "agent_type override."
        )
        architecture_feedback = ArchitectureFeedback(
            confidence=1.0,
            tradeoffs=[
                "Selection was forced by request-scoped agent_type override; heuristic ranking was skipped."
            ],
            docs_considered=[],
        )
    else:
        architecture_type, justification = _infer_stub_architecture(prompt)
        _, secondary_patterns = architecture_registry.normalize_patterns(architecture_type)
        architecture_feedback = ArchitectureFeedback(
            confidence=0.45,
            tradeoffs=[
                "Stub mode uses heuristic architecture inference instead of live architecture ranking."
            ],
            docs_considered=[],
        )

    constraints = [
        Constraint(type="goal", value=f"Deliver a notebook for: {prompt}", priority=5),
        Constraint(
            type="environment",
            value="Designed to run in Jupyter/Colab without extra setup",
            priority=3,
        ),
    ]

    plan = NotebookPlan(
        title=f"LangGraph Workflow: {prompt[:48]}",
        sections=[
            "Setup",
            "State Definition",
            "Tools",
            "Nodes",
            "Graph Construction",
            "Execution",
        ],
        cell_count_estimate=12,
        patterns_used=[architecture_type],
        architecture_type=architecture_type,
    )

    cells: List[CellSpec] = [
        CellSpec(
            cell_type="markdown",
            content=f"# {plan.title}\nGenerated by LangGraph Notebook Foundry",
            section="intro",
        ),
        CellSpec(
            cell_type="code",
            content="!pip install -q langgraph langchain-openai",
            section="setup",
        ),
    ]

    if architecture_type == "router":
        routes = ["search", "analyze", "summarize"]
        route_purposes = {
            "search": "Search for information",
            "analyze": "Analyze data and identify patterns",
            "summarize": "Condense content into summaries",
        }

        # State
        cells.append(
            CellSpec(
                cell_type="code",
                content=RouterPattern.generate_state_code(),
                section="state_definition",
            )
        )

        # Router node
        cells.append(
            CellSpec(
                cell_type="code",
                content=RouterPattern.generate_router_node_code(routes),
                section="nodes",
            )
        )

        # Route nodes
        for route in routes:
            cells.append(
                CellSpec(
                    cell_type="code",
                    content=RouterPattern.generate_route_node_code(
                        route, route_purposes[route]
                    ),
                    section="nodes",
                )
            )

        # Graph
        cells.append(
            CellSpec(
                cell_type="code",
                content=RouterPattern.generate_graph_code(routes),
                section="graph",
            )
        )

    elif architecture_type == "subagents":
        subagents = ["researcher", "writer", "reviewer"]
        descriptions = {
            "researcher": "Gathers information",
            "writer": "Drafts content",
            "reviewer": "Reviews content",
        }

        # State
        cells.append(
            CellSpec(
                cell_type="code",
                content=SubagentsPattern.generate_state_code(),
                section="state_definition",
            )
        )

        # Supervisor
        cells.append(
            CellSpec(
                cell_type="code",
                content=SubagentsPattern.generate_supervisor_code(
                    subagents, descriptions
                ),
                section="nodes",
            )
        )

        # Subagents
        for agent in subagents:
            cells.append(
                CellSpec(
                    cell_type="code",
                    content=SubagentsPattern.generate_subagent_code(
                        agent, descriptions[agent]
                    ),
                    section="nodes",
                )
            )

        # Graph
        cells.append(
            CellSpec(
                cell_type="code",
                content=SubagentsPattern.generate_graph_code(subagents),
                section="graph",
            )
        )
    elif architecture_type == "hybrid":
        direct_specialists = ["specialist_1"]
        team_workers = ["researcher", "reviewer"]
        direct_descriptions = {
            "specialist_1": "Handle direct specialist work without team coordination",
        }
        worker_descriptions = {
            "researcher": "Gather supporting information",
            "reviewer": "Review worker output before finishing",
        }

        cells.append(
            CellSpec(
                cell_type="code",
                content=HybridPattern.generate_state_code(),
                section="state_definition",
            )
        )
        cells.append(
            CellSpec(
                cell_type="code",
                content=HybridPattern.generate_router_node_code(direct_specialists),
                section="nodes",
            )
        )
        for specialist in direct_specialists:
            cells.append(
                CellSpec(
                    cell_type="code",
                    content=HybridPattern.generate_direct_specialist_code(
                        specialist,
                        direct_descriptions[specialist],
                    ),
                    section="nodes",
                )
            )
        cells.append(
            CellSpec(
                cell_type="code",
                content=HybridPattern.generate_supervisor_code(
                    team_workers,
                    worker_descriptions,
                ),
                section="nodes",
            )
        )
        for worker in team_workers:
            cells.append(
                CellSpec(
                    cell_type="code",
                    content=HybridPattern.generate_worker_code(
                        worker,
                        worker_descriptions[worker],
                    ),
                    section="nodes",
                )
            )
        cells.append(
            CellSpec(
                cell_type="code",
                content=HybridPattern.generate_graph_code(
                    direct_specialists,
                    team_workers,
                ),
                section="graph",
            )
        )
    elif architecture_type == "autoagent":
        workers = ["planner", "executor", "critic"]
        worker_descriptions = {
            "planner": "Breaks goals into concrete execution steps",
            "executor": "Implements and runs the selected action plan",
            "critic": "Reviews output quality and requests refinements when needed",
        }

        cells.append(
            CellSpec(
                cell_type="code",
                content=AutoAgentPattern.generate_state_code(),
                section="state_definition",
            )
        )

        cells.append(
            CellSpec(
                cell_type="code",
                content=AutoAgentPattern.generate_coordinator_code(
                    workers, worker_descriptions
                ),
                section="nodes",
            )
        )

        for worker in workers:
            cells.append(
                CellSpec(
                    cell_type="code",
                    content=AutoAgentPattern.generate_worker_code(
                        worker, worker_descriptions[worker]
                    ),
                    section="nodes",
                )
            )

        cells.append(
            CellSpec(
                cell_type="code",
                content=AutoAgentPattern.generate_graph_code(workers),
                section="graph",
            )
        )
    else:
        cells.append(
            CellSpec(
                cell_type="code",
                content="from langgraph.graph import StateGraph\n\n# Define your workflow here",
                section="graph",
            )
        )

    return {
        "constraints": constraints,
        "requirements_feedback": RequirementsFeedback(
            fallback_used=False,
            available_constraint_types=_available_constraint_types(),
        ),
        "architecture_feedback": architecture_feedback,
        "selected_patterns": {
            "primary": architecture_type,
            "secondary": secondary_patterns,
        },
        "docs_context": [],
        "notebook_plan": plan,
        "architecture_type": plan.architecture_type,
        "architecture_justification": justification,
        "generation_config": None,
        "generation_mode": "stub",
        "workflow_design": {
            "entry_point": architecture_type,
            "nodes": [
                {
                    "name": architecture_type,
                    "purpose": (
                        "Dispatch to specialists"
                        if architecture_type == "router"
                        else (
                            "Coordinate AutoAgent workers"
                            if architecture_type == "autoagent"
                            else "Coordinate sub-agents"
                        )
                    ),
                }
            ],
        },
        "tools_plan": [],
        "generated_cells": cells,
        "qa_reports": [],
        "qa_history": [],
        "repair_attempts": 0,
        "artifacts_manifest": {},
        "generation_complete": True,
        "error_message": None,
    }


async def generate_artifacts(
    prompt: str,
    *,
    output_dir: str | Path,
    mode: GenerationMode = "stub",
    formats: List[str] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    agent_type: str | None = None,
    custom_endpoint: str | None = None,
    progress_callback: Any | None = None,
) -> GenerationArtifacts:
    """Generate notebook artifacts either in stub or live mode.

    Stub mode produces deterministic outputs without external API calls.
    Live mode invokes the generator graph and requires configured LLM credentials.

    Args:
        prompt: User prompt describing the desired system
        output_dir: Directory to write generation artifacts
        mode: Generation mode ('stub' or 'live')
        formats: List of output formats to generate (ipynb, html, markdown, pdf, docx, zip).
                 If None or empty, generates all formats.
        model: LLM model to use (optional, uses default if not specified)
        temperature: Temperature for LLM sampling (0.0-2.0, optional)
        max_tokens: Maximum tokens for LLM response (optional)
        agent_type: Type of agent architecture (optional, auto-detected if not specified)
        custom_endpoint: Custom API endpoint URL (optional)
        progress_callback: Optional callback function(node, percentage, message) for progress tracking
    """

    require_optional_module(
        "langgraph_system_generator.notebook.composer",
        feature="Artifact generation",
        extra="full",
    )
    require_optional_module(
        "langgraph_system_generator.notebook.exporters",
        feature="Artifact generation",
        extra="full",
    )

    from langgraph_system_generator.notebook.composer import NotebookComposer
    from langgraph_system_generator.notebook.exporters import NotebookExporter

    generation_config = GenerationConfig(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_base=custom_endpoint,
        agent_type=agent_type,
    )

    tracker = _PhaseTracker(progress_callback)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    tracker.start("init", "Initializing generation...", percentage=5)
    tracker.finish(
        "init",
        "Generation initialized.",
        percentage=10,
        details={"mode": mode},
    )

    if mode == "live":
        create_generator_graph = _load_generator_graph()
        if not custom_endpoint and not os.environ.get("OPENAI_API_KEY"):
            raise GenerationError(
                "LLM API credentials are required for live generation mode.",
                code="credentials_required",
                phase="graph_init",
                hint="Set OPENAI_API_KEY or provide a custom_endpoint with an explicit model.",
                status_code=503,
            )
        tracker.start("graph_init", "Creating generator graph...", percentage=12)
        graph = create_generator_graph()
        tracker.finish("graph_init", "Generator graph created.", percentage=15)
        tracker.start("graph_invoke", "Invoking generator graph...", percentage=18)
        result = await graph.ainvoke(
            _default_state(prompt, generation_config, generation_mode="live")
        )
        tracker.finish("graph_invoke", "Generator graph completed.", percentage=60)
    else:
        tracker.start("stub_build", "Building stub result...", percentage=30)
        result = _build_stub_result(prompt, agent_type=agent_type)
        tracker.finish("stub_build", "Stub generation complete.", percentage=60)

    tracker.start("serialize", "Serializing generation results...", percentage=62)
    serialized = _serialize(result)
    tracker.finish("serialize", "Serialized generation results.", percentage=64)
    if "architecture_type" in serialized and serialized.get("architecture_type"):
        architecture_type = serialized.get("architecture_type")
    else:
        selected_patterns = serialized.get("selected_patterns") or {}
        architecture_type = selected_patterns.get("primary") or "router"

    plan_title = (
        serialized.get("notebook_plan", {}).get("title") or "Generated Notebook"
    )
    requirements_feedback = serialized.get("requirements_feedback") or {}
    architecture_feedback = serialized.get("architecture_feedback") or {}

    manifest: Dict[str, Any] = {
        "prompt": prompt,
        "mode": mode,
        "architecture_type": architecture_type,
        "cell_count": len(serialized.get("generated_cells", []) or []),
        "plan_title": plan_title,
        "requirements_feedback": requirements_feedback,
        "architecture_feedback": architecture_feedback,
        "warnings": [
            *_requirements_warning_entries(requirements_feedback),
            *_architecture_warning_entries(architecture_feedback),
        ],
        "export_results": {},
    }

    # Persist request metadata for reproducibility and downstream consumers.
    if model:
        manifest["model"] = model
    if temperature is not None:
        manifest["temperature"] = temperature
    if max_tokens is not None:
        manifest["max_tokens"] = max_tokens
    if agent_type:
        manifest["agent_type"] = agent_type
    if custom_endpoint:
        manifest["custom_endpoint"] = custom_endpoint

    # Persist helpful artifacts for downstream consumers
    plan = serialized.get("notebook_plan")
    if plan:
        plan_path = target / "notebook_plan.json"
        _write_json(plan_path, plan)
        manifest["plan_path"] = str(plan_path)

    cells = serialized.get("generated_cells")
    if isinstance(cells, list):
        cells_path = target / "generated_cells.json"
        _write_json(cells_path, cells)
        manifest["cells_path"] = str(cells_path)

    default_formats = ["ipynb", "html", "markdown", "docx", "zip"]
    requested_formats = list(formats or default_formats)
    explicit_request = bool(formats)

    if cells:
        tracker.start("compose", "Composing notebook...", percentage=65)
        cell_specs = [CellSpec(**cell) for cell in cells]
        composer = NotebookComposer(colab_friendly=True)
        notebook = composer.build_notebook(cell_specs, ensure_minimum_sections=True)
        tracker.finish(
            "compose",
            "Notebook composed successfully.",
            percentage=70,
            details={"cell_count": len(cell_specs)},
        )

        exporter = NotebookExporter()
        ipynb_path: Path | None = None

        def _record_export_success(
            format_name: str,
            phase: str,
            *,
            path: Path,
            manifest_key: str,
            percentage: int,
        ) -> None:
            manifest[manifest_key] = str(path)
            manifest["export_results"][format_name] = {
                "requested": explicit_request and format_name in requested_formats,
                "status": "completed",
                "path": str(path),
            }
            tracker.finish(
                phase,
                f"{format_name.upper()} export completed.",
                percentage=percentage,
                details={"format": format_name, "path": str(path)},
            )

        def _handle_export_failure(
            format_name: str,
            phase: str,
            exc: Exception,
            *,
            percentage: int,
        ) -> None:
            error = _normalize_generation_error(
                exc,
                phase=phase,
                default_code="requested_export_failed",
                default_status_code=500,
            )
            requested = explicit_request and format_name in requested_formats
            manifest["export_results"][format_name] = {
                "requested": requested,
                "status": "failed",
                "path": None,
                "error": error.to_payload(),
            }
            manifest[f"{format_name}_error"] = str(error)

            # PDF export remains best-effort because the webpdf toolchain depends on
            # host Playwright/browser support that is not guaranteed across environments.
            requested_is_fatal = requested and format_name != "pdf"

            if requested_is_fatal:
                tracker.finish(
                    phase,
                    str(error),
                    percentage=percentage,
                    status="failed",
                    details=error.to_payload(),
                )
                raise error

            manifest["warnings"].append(
                {
                    "code": error.code,
                    "phase": phase,
                    "format": format_name,
                    "message": str(error),
                    "hint": error.hint,
                }
            )
            tracker.finish(
                phase,
                f"{format_name.upper()} export unavailable; continuing with remaining exports.",
                percentage=percentage,
                status="warning",
                details=error.to_payload(),
            )

        if "ipynb" in requested_formats:
            phase = "export_ipynb"
            tracker.start(phase, "Exporting to Jupyter notebook...", percentage=72)
            try:
                ipynb_path = target / "notebook.ipynb"
                exporter.export_ipynb(notebook, ipynb_path)
                _record_export_success(
                    "ipynb",
                    phase,
                    path=ipynb_path,
                    manifest_key="notebook_path",
                    percentage=74,
                )
            except Exception as exc:
                _handle_export_failure("ipynb", phase, exc, percentage=74)

        if "html" in requested_formats:
            phase = "export_html"
            tracker.start(phase, "Exporting to HTML...", percentage=78)
            try:
                html_path = target / "notebook.html"
                exporter.export_to_html(notebook, html_path)
                _record_export_success(
                    "html",
                    phase,
                    path=html_path,
                    manifest_key="html_path",
                    percentage=80,
                )
            except Exception as exc:
                _handle_export_failure("html", phase, exc, percentage=80)

        if "markdown" in requested_formats:
            phase = "export_markdown"
            tracker.start(phase, "Exporting to Markdown...", percentage=81)
            try:
                markdown_path = target / "notebook.md"
                exporter.export_to_markdown(notebook, markdown_path)
                _record_export_success(
                    "markdown",
                    phase,
                    path=markdown_path,
                    manifest_key="markdown_path",
                    percentage=83,
                )
            except Exception as exc:
                _handle_export_failure("markdown", phase, exc, percentage=83)

        if "docx" in requested_formats:
            phase = "export_docx"
            tracker.start(phase, "Exporting to Word document...", percentage=84)
            try:
                docx_path = target / "notebook.docx"
                exporter.export_notebook_to_docx(notebook, docx_path, title=plan_title)
                _record_export_success(
                    "docx",
                    phase,
                    path=docx_path,
                    manifest_key="docx_path",
                    percentage=87,
                )
            except Exception as exc:
                _handle_export_failure("docx", phase, exc, percentage=87)

        if "pdf" in requested_formats:
            phase = "export_pdf"
            tracker.start(phase, "Exporting to PDF...", percentage=90)
            try:
                if ipynb_path is None:
                    ipynb_path = target / "notebook.ipynb"
                    exporter.export_ipynb(notebook, ipynb_path)
                    manifest["notebook_path"] = str(ipynb_path)
                    manifest["export_results"]["ipynb"] = {
                        "requested": False,
                        "status": "completed",
                        "path": str(ipynb_path),
                    }
                pdf_path = target / "notebook.pdf"
                exporter.export_to_pdf(ipynb_path, pdf_path, method="webpdf")
                _record_export_success(
                    "pdf",
                    phase,
                    path=pdf_path,
                    manifest_key="pdf_path",
                    percentage=92,
                )
            except Exception as exc:
                _handle_export_failure("pdf", phase, exc, percentage=92)

        if "zip" in requested_formats:
            phase = "export_zip"
            tracker.start(phase, "Creating ZIP archive...", percentage=95)
            try:
                extra_files = []
                if manifest.get("plan_path"):
                    extra_files.append(manifest["plan_path"])
                if manifest.get("cells_path"):
                    extra_files.append(manifest["cells_path"])
                for format_name, export_result in manifest["export_results"].items():
                    if export_result.get("status") == "completed" and export_result.get(
                        "path"
                    ):
                        if format_name not in {"ipynb", "zip"}:
                            extra_files.append(export_result["path"])

                zip_path = target / "notebook_bundle.zip"
                exporter.export_zip(notebook, zip_path, extra_files=extra_files)
                _record_export_success(
                    "zip",
                    phase,
                    path=zip_path,
                    manifest_key="zip_path",
                    percentage=97,
                )
            except Exception as exc:
                _handle_export_failure("zip", phase, exc, percentage=97)

    tracker.start("finalize", "Finalizing artifacts...", percentage=98)
    tracker.finish("finalize", "Artifacts finalized.", percentage=100)
    manifest["phase_summary"] = list(tracker.summary)
    manifest_path = target / "manifest.json"
    _write_json(manifest_path, manifest)

    return GenerationArtifacts(
        mode=mode,
        prompt=prompt,
        manifest=manifest,
        manifest_path=str(manifest_path),
        output_dir=str(target),
        result=serialized,
    )


async def _handle_build_index(
    cache_path: str,
    store_path: str,
    use_openai: bool,
    chunk_size: int,
    chunk_overlap: int,
) -> str:
    """Build a documentation index from cached docs."""

    embeddings_module = require_optional_module(
        "langchain_community.embeddings",
        feature="Index building",
        extra="full",
    )
    indexer_module = require_optional_module(
        "langgraph_system_generator.rag.indexer",
        feature="Index building",
        extra="full",
    )
    cache = str(Path(cache_path).resolve())
    store = str(Path(store_path).resolve())
    embeddings = None if use_openai else embeddings_module.FakeEmbeddings(size=32)
    manager = await indexer_module.build_index_from_cache(
        cache_path=cache,
        store_path=store,
        embeddings=embeddings,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return manager.store_path


def _run_generate(args: argparse.Namespace) -> int:
    try:
        artifacts = asyncio.run(
            generate_artifacts(
                args.prompt,
                output_dir=args.output,
                mode=args.mode,
                formats=args.formats,
                agent_type=args.agent_type,
            )
        )
    except GenerationError as exc:
        print(f"✗ Failed to generate artifacts: {exc}")
        if exc.hint:
            print(f"  Hint: {exc.hint}")
        return 1
    except OptionalDependencyError as exc:
        print(f"✗ Failed to generate artifacts: {exc}")
        if exc.hint:
            print(f"  Hint: {exc.hint}")
        return 1

    print(f"✓ Generated artifacts in {artifacts['output_dir']}")
    print(f"  Manifest: {artifacts['manifest_path']}")
    if artifacts["manifest"].get("plan_path"):
        print(f"  Plan: {artifacts['manifest']['plan_path']}")
    if artifacts["manifest"].get("cells_path"):
        print(f"  Cells: {artifacts['manifest']['cells_path']}")
    if artifacts["manifest"].get("notebook_path"):
        print(f"  Notebook: {artifacts['manifest']['notebook_path']}")
    if artifacts["manifest"].get("html_path"):
        print(f"  HTML: {artifacts['manifest']['html_path']}")
    if artifacts["manifest"].get("markdown_path"):
        print(f"  Markdown: {artifacts['manifest']['markdown_path']}")
    if artifacts["manifest"].get("docx_path"):
        print(f"  DOCX: {artifacts['manifest']['docx_path']}")
    if artifacts["manifest"].get("pdf_path"):
        print(f"  PDF: {artifacts['manifest']['pdf_path']}")
    if artifacts["manifest"].get("zip_path"):
        print(f"  ZIP Bundle: {artifacts['manifest']['zip_path']}")
    for warning in artifacts["manifest"].get("warnings", []):
        print(f"  Warning: {warning['message']}")
    return 0


def _run_build_index(args: argparse.Namespace) -> int:
    try:
        path = asyncio.run(
            _handle_build_index(
                cache_path=args.cache,
                store_path=args.store,
                use_openai=args.use_openai,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
        )
        print(f"✓ Vector index written to {path}")
        return 0
    except (
        FileNotFoundError,
        OptionalDependencyError,
        RuntimeError,
        ValueError,
    ) as exc:  # pragma: no cover - defensive
        print(f"✗ Failed to build index: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LangGraph Notebook Foundry CLI")
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=None,
        help=(
            "Set CLI logging verbosity. "
            "Defaults to LNF_LOG_LEVEL/LOG_LEVEL env var, otherwise INFO."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate", help="Generate notebook artifacts")
    gen.add_argument(
        "prompt", type=str, help="User prompt describing the system to build"
    )
    gen.add_argument(
        "-o",
        "--output",
        default=str((BASE_DIR / "output").resolve()),
        help="Directory to write artifacts (default: <project>/output)",
    )
    gen.add_argument(
        "--mode",
        choices=["stub", "live"],
        default="stub",
        help="Generation mode. 'stub' avoids external API calls (default).",
    )
    gen.add_argument(
        "--formats",
        nargs="+",
        choices=["ipynb", "html", "markdown", "pdf", "docx", "zip"],
        default=None,
        help=(
            "Output formats to generate "
            "(default: ipynb html markdown docx zip; PDF only when requested). "
            "Specify one or more."
        ),
    )
    gen.add_argument(
        "--agent-type",
        choices=["router", "subagents", "hybrid", "autoagent"],
        default=None,
        help="Override architecture selection for generation.",
    )
    gen.set_defaults(func=_run_generate)

    idx = subparsers.add_parser(
        "build-index", help="Build vector index from cached docs"
    )
    idx.add_argument(
        "--cache",
        default=str(DEFAULT_CACHE_PATH),
        help="Path to cached docs directory (defaults to package data/cached_docs)",
    )
    idx.add_argument(
        "--store",
        default=str(Path(settings.vector_store_path).resolve()),
        help="Path to save the vector index",
    )
    idx.add_argument(
        "--use-openai",
        action="store_true",
        help="Use OpenAI embeddings instead of local fake embeddings.",
    )
    idx.add_argument(
        "--chunk-size", type=int, default=500, help="Chunk size for document splitting"
    )
    idx.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Chunk overlap for document splitting",
    )
    idx.set_defaults(func=_run_build_index)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
