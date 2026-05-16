"""Graph Designer agent for designing the inner workflow structure."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from langgraph_system_generator.generator.agents._llm import build_chat_llm
from langgraph_system_generator.generator.graph_design_registry import (
    GraphDesignRegistration,
    GraphDesignRegistry,
    build_graph_exports,
    domain_terms_for_constraints,
    get_graph_design_registry,
    graph_design_issue_messages,
    normalize_graph_design,
    validate_graph_design,
)
from langgraph_system_generator.generator.state import (
    Constraint,
    GraphDesignFeedback,
    GraphDesignResult,
)
from langgraph_system_generator.generator.utils import extract_json_from_llm_response
from langgraph_system_generator.utils.config import ModelConfig, settings
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.generation_options import resolve_architecture_type

logger = logging.getLogger(__name__)


class GraphDesigner:
    """Design the workflow graph for the selected architecture."""

    def __init__(
        self,
        model: str | None = None,
        model_config: ModelConfig | None = None,
        registry: GraphDesignRegistry | None = None,
    ):
        self.llm = build_chat_llm(
            model=model,
            model_config=model_config,
            chat_openai_class=ChatOpenAI,
        )
        if registry is None:
            plugin_modules = tuple(settings.graph_designer_plugin_modules)
            if plugin_modules:
                importlib.invalidate_caches()
            self.registry = get_graph_design_registry(plugin_modules=plugin_modules)
        else:
            self.registry = registry

    async def design_workflow(
        self, architecture: Dict[str, Any], constraints: List[Constraint]
    ) -> GraphDesignResult:
        """Create a complete, validated graph specification."""

        selected_patterns = architecture.get("selected_patterns", {}) or {}
        architecture_type = resolve_architecture_type(
            architecture.get("architecture_type"),
            selected_patterns,
        )
        registration = self._registration_for(architecture_type)
        secondary_patterns = list(selected_patterns.get("secondary") or [])
        justification = architecture.get("justification", "")

        constraints_text = "\n".join(
            [
                f"- [{constraint.type}] {constraint.value} (priority: {constraint.priority})"
                for constraint in constraints
            ]
        )

        design_prompt = SystemMessage(
            content=(
                "You are a LangGraph workflow designer.\n"
                "Design a complete graph specification for the requested architecture.\n\n"
                f"Architecture id: {registration.architecture_id}\n"
                f"Supported entry shapes: {registration.supported_entry_shapes}\n"
                f"Supported exit shapes: {registration.supported_exit_shapes}\n"
                f"Composition strategy: {registration.composition_strategy}\n"
                f"Cycles allowed: {registration.cycles_allowed}\n\n"
                "For the workflow, specify:\n"
                "1. state_schema: TypedDict fields needed for the workflow\n"
                "2. nodes: List of node names and their purposes\n"
                "3. edges: Direct edges between nodes\n"
                "4. conditional_edges: Conditional routing logic with conditions\n"
                "5. entry_point: Starting node\n"
                "6. checkpointing: Whether to enable checkpointing\n\n"
                "Return a JSON object with this structure:\n"
                "{\n"
                '  "state_schema": {"field_name": "description"},\n'
                '  "nodes": [{"name": "node_name", "purpose": "description"}],\n'
                '  "edges": [{"from": "node_a", "to": "node_b"}],\n'
                '  "conditional_edges": [\n'
                "    {\n"
                '      "from": "node_name",\n'
                '      "condition": "condition_description",\n'
                '      "branches": {"branch_name": "target_node", "FINISH": "END"}\n'
                "    }\n"
                "  ],\n"
                '  "entry_point": "start_node",\n'
                '  "checkpointing": true\n'
                "}\n"
            )
        )

        user_message = HumanMessage(
            content=(
                f"Architecture Type: {architecture_type}\n"
                f"Architecture Justification: {justification}\n"
                f"Selected Patterns: primary={selected_patterns.get('primary', architecture_type)}, "
                f"secondary={secondary_patterns}\n\n"
                f"Requirements:\n{constraints_text}\n\n"
                "Design the workflow graph."
            )
        )

        live_issues = []
        fallback_reason: str | None = None

        try:
            response = await self.llm.ainvoke([design_prompt, user_message])
            payload = extract_json_from_llm_response(response.content)
            live_result = normalize_graph_design(payload, architecture_type, registration)
            if not live_result.domain_terms:
                live_result = live_result.model_copy(
                    update={"domain_terms": domain_terms_for_constraints(constraints)}
                )
            live_issues = validate_graph_design(live_result, registration)
            if self._has_blocking_issues(live_issues):
                fallback_reason = "Live graph design validation failed."
                logger.warning(
                    "Graph design validation failed for %s: %s",
                    architecture_type,
                    graph_design_issue_messages(live_issues),
                )
                return self._finalize_fallback(
                    registration,
                    architecture,
                    constraints,
                    fallback_reason=fallback_reason,
                    live_issues=live_issues,
                )
            return self._finalize_result(
                live_result,
                registration,
                fallback_used=False,
                fallback_reason=None,
                validation_issues=live_issues,
            )
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            fallback_reason = f"Graph design parsing failed: {exc}"
            logger.warning(
                "Graph design parsing failed for %s: %s",
                architecture_type,
                exc,
            )
            return self._finalize_fallback(
                registration,
                architecture,
                constraints,
                fallback_reason=fallback_reason,
                live_issues=live_issues,
            )

    def _registration_for(self, architecture_type: str) -> GraphDesignRegistration:
        """Return the registry entry for the selected architecture."""

        try:
            return self.registry.get(architecture_type)
        except KeyError as exc:
            raise GenerationError(
                f"Unsupported graph design architecture '{architecture_type}'.",
                code="unsupported_graph_architecture",
                phase="graph_design",
                hint="Select a registered architecture type before graph design.",
                details={
                    "architecture_type": architecture_type,
                    "supported_architecture_types": self.registry.supported_architecture_types(),
                },
                status_code=400,
            ) from exc

    def _finalize_result(
        self,
        result: GraphDesignResult,
        registration: GraphDesignRegistration,
        *,
        fallback_used: bool,
        fallback_reason: str | None,
        validation_issues: List[Any],
        warnings: List[str] | None = None,
    ) -> GraphDesignResult:
        """Attach feedback and exports to the normalized graph design."""

        warning_messages = list(warnings or [])
        warning_messages.extend(
            graph_design_issue_messages(validation_issues, severity="warning")
        )
        warning_messages = list(dict.fromkeys(warning_messages))
        feedback = GraphDesignFeedback(
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            validation_errors=graph_design_issue_messages(
                validation_issues, severity="error"
            ),
            warnings=warning_messages,
            validation_issues=validation_issues,
            composition_strategy=registration.composition_strategy,
        )
        exports = build_graph_exports(
            result,
            registration,
            validation_issues,
            warning_messages,
        )
        return result.model_copy(update={"feedback": feedback, "exports": exports})

    def _finalize_fallback(
        self,
        registration: GraphDesignRegistration,
        architecture: Dict[str, Any],
        constraints: List[Constraint],
        *,
        fallback_reason: str,
        live_issues: List[Any],
    ) -> GraphDesignResult:
        """Build, validate, and return the deterministic fallback graph design."""

        fallback_payload = self._fallback_design(
            registration.architecture_id,
            architecture=architecture,
            constraints=constraints,
        )
        fallback_result = normalize_graph_design(
            fallback_payload,
            registration.architecture_id,
            registration,
        )
        fallback_issues = validate_graph_design(fallback_result, registration)
        if self._has_blocking_issues(fallback_issues):
            blocking_messages = graph_design_issue_messages(
                fallback_issues, severity="error"
            )
            raise GenerationError(
                (
                    "Graph designer fallback produced an invalid workflow and could not "
                    "recover safely."
                ),
                code="graph_design_fallback_invalid",
                phase="graph_design",
                hint="Inspect the fallback builder or registry registration for this architecture.",
                details={
                    "architecture_type": registration.architecture_id,
                    "fallback_reason": fallback_reason,
                    "validation_errors": blocking_messages,
                },
                status_code=500,
            )

        warnings = [f"Recovered using deterministic {registration.architecture_id} fallback."]
        return self._finalize_result(
            fallback_result,
            registration,
            fallback_used=True,
            fallback_reason=fallback_reason,
            validation_issues=[*live_issues, *fallback_issues],
            warnings=warnings,
        )

    @staticmethod
    def _has_blocking_issues(validation_issues: List[Any]) -> bool:
        """Return True when validation includes blocking errors."""

        return any(issue.severity == "error" for issue in validation_issues)

    def _fallback_design(
        self,
        architecture_type: str,
        *,
        architecture: Dict[str, Any] | None = None,
        constraints: List[Constraint] | None = None,
    ) -> Dict[str, Any]:
        """Provide a deterministic registry-backed fallback design."""

        registration = self._registration_for(architecture_type)
        return registration.fallback_builder(
            architecture=architecture or {},
            constraints=constraints or [],
        )
