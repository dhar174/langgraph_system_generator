"""Requirements Analyst agent for extracting structured constraints from user prompts."""

from __future__ import annotations

import logging
from typing import Any, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.agents._llm import build_chat_llm
from langgraph_system_generator.generator.state import (
    Constraint,
    RequirementsAnalysis,
    RequirementsFeedback,
)
from langgraph_system_generator.generator.utils import extract_json_from_llm_response
from langgraph_system_generator.utils.config import ModelConfig, settings

logger = logging.getLogger(__name__)

DEFAULT_CONSTRAINT_TYPES = (
    "goal",
    "tone",
    "length",
    "structure",
    "runtime",
    "environment",
)
CORE_CONSTRAINT_TYPES = ("goal", "runtime", "environment")
CONSTRAINT_TYPE_DESCRIPTIONS = {
    "goal": "The main objective, deliverable, or workflow outcome.",
    "tone": "Style, voice, or presentation constraints.",
    "length": "Length, scope, or detail expectations.",
    "structure": "Structural or organizational requirements.",
    "runtime": "Runtime behavior such as models, latency, budget, or iteration limits.",
    "environment": "Execution environment, dependencies, or platform targets.",
}
MISSING_INPUT_SUGGESTIONS = {
    "goal": "State the primary deliverable or workflow objective explicitly.",
    "runtime": "Add runtime constraints such as model choice, latency, budget, or retry limits.",
    "environment": "Describe the target environment, such as Colab, local Jupyter, deployment target, or required libraries.",
}


def _normalize_constraint_type(value: str) -> str:
    """Return a normalized constraint type name."""

    return value.strip().lower().replace(" ", "_")


class RequirementsAnalyst:
    """Extracts structured constraints from user prompt."""

    def __init__(
        self,
        model: str | None = None,
        model_config: ModelConfig | None = None,
    ):
        self.llm = build_chat_llm(
            model=model,
            model_config=model_config,
            chat_openai_class=ChatOpenAI,
        )
        self.constraint_types = self._constraint_type_registry()

    def _constraint_type_registry(self) -> List[str]:
        """Return the current ordered registry of supported constraint types."""

        registry: List[str] = []
        for raw_type in [*DEFAULT_CONSTRAINT_TYPES, *settings.requirements_constraint_types]:
            normalized = _normalize_constraint_type(raw_type)
            if normalized and normalized not in registry:
                registry.append(normalized)
        return registry

    def _build_analysis_prompt(self) -> SystemMessage:
        """Return the system prompt used for requirements extraction."""

        type_lines = []
        for constraint_type in self.constraint_types:
            description = CONSTRAINT_TYPE_DESCRIPTIONS.get(
                constraint_type,
                "Project-specific requirement category configured for this repository.",
            )
            type_lines.append(f'- "{constraint_type}": {description}')

        return SystemMessage(
            content=(
                "You are a requirements analyst. Extract structured constraints from the user's project description.\n\n"
                "Available constraint types:\n"
                f"{chr(10).join(type_lines)}\n\n"
                "Return a JSON object with this shape:\n"
                "{\n"
                '  "constraints": [\n'
                "    {\n"
                '      "type": "goal",\n'
                '      "value": "description",\n'
                '      "priority": 5,\n'
                '      "confidence": 0.0,\n'
                '      "explanation": "why this constraint was extracted"\n'
                "    }\n"
                "  ]\n"
                "}\n\n"
                "Rules:\n"
                "- Use only the available constraint types listed above.\n"
                "- Omit any constraint type that is not justified by the prompt.\n"
                "- Priority is 1 (low) to 5 (high). Goals are usually priority 5.\n"
                "- Confidence is optional and should be between 0.0 and 1.0.\n"
                "- Explanations should be short and actionable.\n"
                "- Return valid JSON only."
            )
        )

    def _parse_constraints_payload(self, payload: Any) -> List[Constraint]:
        """Convert model JSON into a list of constraints."""

        if isinstance(payload, dict):
            if "constraints" in payload:
                payload = payload["constraints"]
            elif {"type", "value"}.issubset(payload):
                payload = [payload]
            else:
                raise ValueError("Requirements payload did not contain a constraints array.")

        if not isinstance(payload, list):
            raise ValueError("Requirements payload must be a list of constraints.")

        constraints: List[Constraint] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Each extracted constraint must be an object.")
            normalized_type = _normalize_constraint_type(str(item.get("type", "")))
            constraint = Constraint(
                **{
                    **item,
                    "type": normalized_type,
                }
            )
            constraints.append(constraint)

        return constraints

    def _fallback_constraint(self, prompt: str) -> Constraint:
        """Create a conservative fallback constraint from the raw prompt."""

        return Constraint(
            type="goal",
            value=prompt[:200] if len(prompt) > 200 else prompt,
            priority=5,
            confidence=0.15,
            explanation=(
                "Fallback goal created from the raw prompt because structured "
                "requirements extraction was unavailable."
            ),
        )

    def _detect_conflicts(self, constraints: List[Constraint]) -> List[str]:
        """Return conflicts where the same constraint type has divergent values."""

        values_by_type: dict[str, set[str]] = {}
        for constraint in constraints:
            values_by_type.setdefault(constraint.type, set()).add(
                constraint.value.strip().lower()
            )

        conflicts = []
        for constraint_type, distinct_values in values_by_type.items():
            if len(distinct_values) > 1:
                conflicts.append(
                    f"Conflicting {constraint_type} constraints were extracted from the prompt."
                )
        return conflicts

    def _missing_core_inputs(self, constraints: List[Constraint]) -> List[str]:
        """Return missing core requirement categories."""

        present = {_normalize_constraint_type(constraint.type) for constraint in constraints}
        return [constraint_type for constraint_type in CORE_CONSTRAINT_TYPES if constraint_type not in present]

    def _build_feedback(
        self,
        constraints: List[Constraint],
        *,
        fallback_used: bool,
        fallback_reason: str | None,
    ) -> RequirementsFeedback:
        """Build structured advisory feedback from parsed constraints."""

        missing_inputs = self._missing_core_inputs(constraints)
        conflicts = self._detect_conflicts(constraints)

        suggestions: List[str] = []
        if fallback_used:
            suggestions.append(
                "Clarify the main goal, runtime expectations, and target environment to improve requirements extraction."
            )
        for missing_input in missing_inputs:
            suggestion = MISSING_INPUT_SUGGESTIONS.get(missing_input)
            if suggestion and suggestion not in suggestions:
                suggestions.append(suggestion)
        if conflicts:
            suggestions.append(
                "Resolve conflicting prompt instructions so the generator can pick a single interpretation."
            )

        return RequirementsFeedback(
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            missing_inputs=missing_inputs,
            conflicts=conflicts,
            suggestions=suggestions,
            available_constraint_types=list(self.constraint_types),
        )

    async def analyze(self, prompt: str) -> RequirementsAnalysis:
        """Extract structured constraints and feedback from a user prompt."""

        analysis_prompt = self._build_analysis_prompt()
        user_message = HumanMessage(content=prompt)
        response = await self.llm.ainvoke([analysis_prompt, user_message])

        fallback_used = False
        fallback_reason: str | None = None

        try:
            constraints_data = extract_json_from_llm_response(response.content)
            constraints = self._parse_constraints_payload(constraints_data)
            if not constraints:
                raise ValueError("No constraints were extracted from the model response.")
        except (ValueError, KeyError, TypeError) as exc:
            fallback_used = True
            fallback_reason = f"Requirements extraction fallback used: {exc}"
            logger.warning(fallback_reason)
            constraints = [self._fallback_constraint(prompt)]

        feedback = self._build_feedback(
            constraints,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
        return RequirementsAnalysis(constraints=constraints, feedback=feedback)
