"""Shared utility functions for notebook generation."""

from __future__ import annotations

from typing import Tuple


def escape_xml_chars(text: str) -> str:
    """Escape special XML/HTML characters for safe use in markup.

    Args:
        text: Text that may contain special characters.

    Returns:
        Text with special characters escaped.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def parse_markdown_heading(line: str) -> Tuple[int, str] | None:
    """Parse a markdown heading line and return its level and text.

    Args:
        line: A line of text that may be a markdown heading.

    Returns:
        Tuple of (level, text) if line is a heading, None otherwise.
        Level is 1 for #, 2 for ##, 3 for ###, etc.
    """
    line = line.strip()
    if not line:
        return None

    if line.startswith("### "):
        return (3, line[4:])
    elif line.startswith("## "):
        return (2, line[3:])
    elif line.startswith("# "):
        return (1, line[2:])

    return None
