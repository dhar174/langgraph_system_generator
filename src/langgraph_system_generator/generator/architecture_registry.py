"""Internal registry for supported architecture-selection metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Mapping


def _normalize_architecture_id(value: str) -> str:
    """Return a normalized architecture identifier."""

    if value is None:
        normalized = None
    else:
        normalized = str(value).strip().lower() or None
    if not normalized:
        raise ValueError("Architecture registrations must include a non-empty architecture_id.")
    return normalized


def _normalize_patterns(values: Iterable[str] | None) -> list[str]:
    """Return an ordered, de-duplicated architecture-id list."""

    normalized_patterns: list[str] = []
    for raw_value in values or []:
        normalized = str(raw_value or "").strip().lower() or None
        if normalized and normalized not in normalized_patterns:
            normalized_patterns.append(normalized)
    return normalized_patterns


def _normalize_queries(values: Iterable[str] | None) -> list[str]:
    """Return an ordered, de-duplicated list of non-empty query strings."""

    normalized_queries: list[str] = []
    for raw_value in values or []:
        text = str(raw_value or "").strip()
        if text and text not in normalized_queries:
            normalized_queries.append(text)
    return normalized_queries


@dataclass(frozen=True)
class ArchitectureRegistration:
    """Metadata describing a supported architecture selection option."""

    architecture_id: str
    selector_prompt_description: str
    default_secondary_patterns: list[str] = field(default_factory=list)
    docs_queries: list[str] = field(default_factory=list)
    docs_weight: float = 1.0
    deterministic: bool = True

    def normalized(self) -> "ArchitectureRegistration":
        """Return a normalized copy suitable for registry storage."""

        architecture_id = _normalize_architecture_id(self.architecture_id)
        description = str(self.selector_prompt_description or "").strip()
        if not description:
            raise ValueError(
                f"Architecture registration '{architecture_id}' must include a prompt description."
            )
        return ArchitectureRegistration(
            architecture_id=architecture_id,
            selector_prompt_description=description,
            default_secondary_patterns=_normalize_patterns(
                self.default_secondary_patterns
            ),
            docs_queries=_normalize_queries(self.docs_queries),
            docs_weight=1.0 if self.docs_weight is None else float(self.docs_weight),
            deterministic=bool(self.deterministic),
        )


class ArchitectureRegistry:
    """Mutable in-memory registry for architecture metadata."""

    def __init__(self, registrations: Iterable[ArchitectureRegistration] | None = None):
        self._registrations: dict[str, ArchitectureRegistration] = {}
        for registration in registrations or []:
            self.register(registration)

    def clone(self) -> "ArchitectureRegistry":
        """Return a shallow copy of the registry."""

        return ArchitectureRegistry(self._registrations.values())

    def register(self, registration: ArchitectureRegistration) -> ArchitectureRegistration:
        """Register or replace an architecture entry."""

        normalized = registration.normalized()
        self._registrations[normalized.architecture_id] = normalized
        return normalized

    def get(self, architecture_id: str) -> ArchitectureRegistration:
        """Return a registered architecture entry."""

        normalized = _normalize_architecture_id(architecture_id)
        return self._registrations[normalized]

    def supported_architecture_types(self) -> list[str]:
        """Return registered architecture identifiers in insertion order."""

        return list(self._registrations.keys())

    def selectable_architecture_types(self) -> list[str]:
        """Return architectures that the current generator can produce deterministically."""

        return [
            architecture_id
            for architecture_id, registration in self._registrations.items()
            if registration.deterministic
        ]

    def normalize_patterns(
        self,
        architecture_id: str,
        secondary_patterns: Iterable[str] | None = None,
    ) -> tuple[str, list[str]]:
        """Normalize a pattern selection against the registry defaults."""

        normalized_primary = _normalize_architecture_id(architecture_id)
        registration = self.get(normalized_primary)
        normalized_secondary = list(registration.default_secondary_patterns)
        for raw_value in secondary_patterns or []:
            normalized = str(raw_value or "").strip().lower() or None
            if (
                normalized
                and normalized != normalized_primary
                and normalized in self._registrations
                and normalized not in normalized_secondary
            ):
                normalized_secondary.append(normalized)
        return normalized_primary, normalized_secondary

    def docs_queries_for(
        self,
        architecture_id: str,
        query_overrides: Mapping[str, list[str]] | None = None,
    ) -> list[str]:
        """Return effective docs queries for an architecture."""

        normalized = _normalize_architecture_id(architecture_id)
        if query_overrides and normalized in query_overrides:
            override_queries = _normalize_queries(query_overrides[normalized])
            if override_queries:
                return override_queries
        return list(self.get(normalized).docs_queries)

    def docs_weight_for(
        self,
        architecture_id: str,
        weight_overrides: Mapping[str, float] | None = None,
    ) -> float:
        """Return the effective docs weight for an architecture."""

        normalized = _normalize_architecture_id(architecture_id)
        if weight_overrides and normalized in weight_overrides:
            try:
                return float(weight_overrides[normalized])
            except (TypeError, ValueError):
                return self.get(normalized).docs_weight
        return self.get(normalized).docs_weight

    def render_selector_prompt_catalog(self) -> str:
        """Render a human-readable selector catalog from registry entries."""

        lines = []
        for architecture_id, registration in self._registrations.items():
            determinism = (
                "deterministic notebook generation supported"
                if registration.deterministic
                else "selector metadata only"
            )
            lines.append(
                f"- **{architecture_id}**: {registration.selector_prompt_description} ({determinism})"
            )
        return "\n".join(lines)


def _default_registrations() -> list[ArchitectureRegistration]:
    """Return the built-in architecture catalog."""

    return [
        ArchitectureRegistration(
            architecture_id="router",
            selector_prompt_description=(
                "Single router that classifies incoming work and dispatches it to direct specialists."
            ),
            default_secondary_patterns=[],
            docs_queries=[
                "LangGraph router pattern implementation best practices",
                "LangGraph routing workflow conditional edges",
            ],
            docs_weight=1.0,
            deterministic=True,
        ),
        ArchitectureRegistration(
            architecture_id="subagents",
            selector_prompt_description=(
                "Supervisor coordinating multiple specialist workers that operate with their own focused contexts."
            ),
            default_secondary_patterns=[],
            docs_queries=[
                "LangGraph subagents supervisor pattern implementation best practices",
                "LangGraph supervisor multi-agent workflow",
            ],
            docs_weight=1.0,
            deterministic=True,
        ),
        ArchitectureRegistration(
            architecture_id="hybrid",
            selector_prompt_description=(
                "Composed workflow that uses a router entry point plus a supervisor-led worker team for deeper branches."
            ),
            default_secondary_patterns=["router", "subagents"],
            docs_queries=[
                "LangGraph router supervisor hybrid workflow",
                "LangGraph supervisor multi-agent workflow",
            ],
            docs_weight=1.15,
            deterministic=True,
        ),
        ArchitectureRegistration(
            architecture_id="autoagent",
            selector_prompt_description=(
                "Coordinator-driven planner/executor/critic team for iterative autonomous execution."
            ),
            default_secondary_patterns=[],
            docs_queries=[
                "LangGraph autoagent planner executor critic workflow",
                "LangGraph plan execute critique loop",
            ],
            docs_weight=0.95,
            deterministic=True,
        ),
        ArchitectureRegistration(
            architecture_id="deepagents",
            selector_prompt_description=(
                "Experimental Deep Agents harness for complex, multi-step work that benefits from "
                "built-in planning, file/context management, and optional subagent delegation."
            ),
            default_secondary_patterns=["subagents"],
            docs_queries=[
                "LangChain Deep Agents create_deep_agent planning subagents",
                "Deep Agents SDK built in planning filesystem subagents",
            ],
            docs_weight=1.05,
            deterministic=True,
        ),
    ]


@lru_cache(maxsize=1)
def get_default_architecture_registry() -> ArchitectureRegistry:
    """Return the default built-in architecture registry."""

    return ArchitectureRegistry(_default_registrations())
