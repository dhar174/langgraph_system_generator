"""Shared normalization constants and helpers for advanced generation options."""

from __future__ import annotations

from typing import Any, Mapping

from langgraph_system_generator.generator.architecture_registry import (
    get_default_architecture_registry,
)

SUPPORTED_OPENAI_MODELS = frozenset(
    {"gpt-5.2", "gpt-5-mini", "gpt-5-nano", "gpt-5.1"}
)

SUPPORTED_AGENT_TYPES = frozenset(
    get_default_architecture_registry().selectable_architecture_types()
)


def normalize_optional_string(value: str | None) -> str | None:
    """Strip surrounding whitespace and collapse empty strings to None."""

    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_agent_type(agent_type: str | None) -> str | None:
    """Normalize agent_type values for validation and downstream use."""

    normalized = normalize_optional_string(agent_type)
    if normalized is None:
        return None
    return normalized.lower()


def resolve_architecture_type(
    architecture_type: str | None,
    selected_patterns: Mapping[str, Any] | None = None,
    *,
    default: str = "router",
) -> str:
    """Resolve a normalized architecture id from explicit or pattern-selected state."""

    if isinstance(architecture_type, str):
        normalized_explicit = normalize_agent_type(architecture_type)
        if normalized_explicit:
            return normalized_explicit

    if isinstance(selected_patterns, Mapping):
        primary = selected_patterns.get("primary")
        if isinstance(primary, str):
            normalized_primary = normalize_agent_type(primary)
            if normalized_primary:
                return normalized_primary

    normalized_default = normalize_agent_type(default)
    return normalized_default or "router"
