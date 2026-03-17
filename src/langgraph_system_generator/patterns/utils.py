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
    params = [f"model={repr(model)}", f"temperature={temperature}"]
    if api_base:
        params.append(f"base_url={repr(api_base)}")
    if max_tokens:
        params.append(f"max_tokens={max_tokens}")
    return f"ChatOpenAI({', '.join(params)})"


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


def render_additional_fields(additional_fields: Optional[Dict[str, str]]) -> str:
    """Render optional TypedDict fields with inline descriptions."""
    if not additional_fields:
        return ""
    rendered = []
    for field_name, description in additional_fields.items():
        comment = collapse_whitespace(description)
        rendered.append(f"    {sanitize_identifier(field_name)}: str  # {comment}")
    return "\n".join(rendered) + "\n"
