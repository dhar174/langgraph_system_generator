"""Shared utilities for pattern generators."""

from __future__ import annotations

import json
import re
from typing import Dict, Optional


def build_llm_init(
    model: str,
    temperature: float,
    api_base: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Build a ChatOpenAI initialization expression."""
    params = [f"temperature={temperature}"]
    if max_tokens:
        params.append(f"max_tokens={max_tokens}")
    return f"make_llm({', '.join(params)})"


def sanitize_identifier(value: str) -> str:
    """Return a stable snake_case identifier for generated node names."""
    identifier = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip().lower())
    identifier = re.sub(r"_+", "_", identifier).strip("_")
    if not identifier:
        return "default"
    if identifier[0].isdigit():
        return f"node_{identifier}"
    return identifier


def double_quoted_literal(value: str) -> str:
    """Return a safely escaped double-quoted Python string literal."""
    return json.dumps(value)


def collapse_whitespace(value: str) -> str:
    """Return text with internal whitespace normalized to single spaces."""
    return " ".join(str(value).split())


def infer_state_field_type(field_name: str, description: str = "") -> str:
    """Infer a useful generated state type for a graph-spec field."""

    normalized = sanitize_identifier(field_name)
    lowered_name = normalized.lower()
    lowered_text = f"{lowered_name} {description}".lower()

    if lowered_name in {"messages"}:
        return "Annotated[List[BaseMessage], add_messages]"

    list_markers = {
        "history",
        "logs",
        "memories",
        "memory_updates",
        "retrieved_memories",
        "notes_list",
        "events",
        "warnings",
    }
    list_suffixes = (
        "_history",
        "_log",
        "_logs",
        "_memories",
        "_updates",
        "_events",
        "_warnings",
    )
    if lowered_name in list_markers or lowered_name.endswith(list_suffixes):
        return "Annotated[List[str], operator.add]"

    dict_markers = {
        "results",
        "task_results",
        "verification",
        "verifications",
        "metadata",
        "payload",
        "context",
        "profile_data",
        "tool_outputs",
    }
    if any(marker in lowered_name for marker in dict_markers):
        return "Dict[str, object]"

    bool_markers = {
        "approved",
        "attempted",
        "complete",
        "completed",
        "done",
        "failed",
        "passed",
        "pending",
        "success",
        "needs_",
        "requires_",
        "should_",
        "has_",
        "is_",
    }
    if any(lowered_name == marker or lowered_name.startswith(marker) for marker in bool_markers):
        return "bool"
    if any(lowered_name.endswith(f"_{marker}") for marker in {"passed", "pending", "complete"}):
        return "bool"

    int_markers = {
        "count",
        "counter",
        "iteration",
        "iterations",
        "attempt",
        "attempts",
        "turn",
        "turns",
        "retry",
        "retries",
        "step",
        "steps",
    }
    if any(marker in lowered_name for marker in int_markers):
        return "int"

    if any(marker in lowered_text for marker in {"score", "confidence", "probability"}):
        return "float"

    return "str"


def render_additional_fields(additional_fields: Optional[Dict[str, str]]) -> str:
    """Render optional TypedDict fields with inline descriptions."""
    if not additional_fields:
        return ""
    rendered = []
    for field_name, description in additional_fields.items():
        comment = collapse_whitespace(description)
        field_type = infer_state_field_type(field_name, description)
        rendered.append(
            f"    {sanitize_identifier(field_name)}: {field_type}  # {comment}"
        )
    return "\n".join(rendered) + "\n"
