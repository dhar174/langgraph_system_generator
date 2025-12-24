"""Utility functions for LLM response parsing."""

import json
from typing import Any, Dict, List


def extract_json_from_llm_response(content: str) -> Any:
    """Extract JSON from LLM response, handling markdown code blocks.

    Args:
        content: LLM response content that may contain JSON in markdown blocks

    Returns:
        Parsed JSON object (dict, list, etc.)

    Raises:
        json.JSONDecodeError: If JSON cannot be parsed
    """
    if not isinstance(content, str):
        raise ValueError("Content must be a string")

    # Try to extract JSON from markdown code blocks
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    return json.loads(content)
