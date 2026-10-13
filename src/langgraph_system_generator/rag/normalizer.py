"""Normalization utilities for retrieved documentation snippets."""

from __future__ import annotations

from typing import Any, Optional

from langgraph_system_generator.generator.state import DocSnippet
from langgraph_system_generator.utils.config import settings


def normalize_snippet_content(content: str, max_chars: Optional[int] = None) -> str:
    """Trim snippet text to bounded length, avoiding mid-word cutting if possible."""
    limit = max_chars or settings.docs_max_snippet_chars
    if not content:
        return ""
    text = str(content).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def normalize_relevance_score(score: Any, is_distance: bool = False) -> float:
    """Normalize score or distance to a float bounded to [0.0, 1.0]."""
    try:
        val = float(score)
    except (TypeError, ValueError):
        return 0.0

    if is_distance:
        # For FAISS L2 distances d >= 0, convert to similarity [0, 1]
        non_neg = max(0.0, val)
        return round(1.0 / (1.0 + non_neg), 4)

    # If already a similarity score, clamp between 0.0 and 1.0
    return round(max(0.0, min(1.0, val)), 4)


def create_normalized_doc_snippet(
    content: str,
    source: str,
    source_kind: str,
    relevance_score: float = 0.0,
    heading: Optional[str] = None,
    max_chars: Optional[int] = None,
    is_distance: bool = False,
) -> DocSnippet:
    """Create a bounded DocSnippet instance with normalized fields."""
    return DocSnippet(
        content=normalize_snippet_content(content, max_chars=max_chars),
        source=str(source or "").strip(),
        source_kind=str(source_kind or "").strip(),
        relevance_score=normalize_relevance_score(relevance_score, is_distance=is_distance),
        heading=str(heading).strip() if heading else None,
    )
