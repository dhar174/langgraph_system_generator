"""Utility functions for LLM response parsing."""

import json
from collections.abc import Mapping
from typing import Any, Dict, List


def get_message_text(message: Any) -> str:
    """Read only textual content from a model message.

    LangChain's ``responses/v1`` messages can contain structured content
    blocks. Avoid ``str(message.content)``, which would expose Python list and
    dict representations to downstream parsers and may include non-text data.
    """
    if isinstance(message, str):
        return message

    text = getattr(message, "text", None)
    if isinstance(text, str):
        return str(text)

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if not isinstance(content, (list, tuple)):
        return ""

    text_parts = []
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
        elif (
            isinstance(block, Mapping)
            and block.get("type") in {"text", "output_text"}
            and isinstance(block.get("text"), str)
        ):
            text_parts.append(block["text"])
    return "".join(text_parts)


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
