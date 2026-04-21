"""Shared normalization constants and helpers for advanced generation options."""

from __future__ import annotations

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
