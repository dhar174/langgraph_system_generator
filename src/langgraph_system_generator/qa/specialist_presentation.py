"""Bounded, inert projections of host-admitted semantic feedback."""

from __future__ import annotations

import html
import re
from typing import Any

from langgraph_system_generator.qa.specialist_models import SemanticReviewFeedback


def feedback_payload(value: Any) -> dict[str, Any] | None:
    """Do not expose disabled/default metadata or unchecked response payloads."""
    if value is None:
        return None
    feedback = (
        value
        if isinstance(value, SemanticReviewFeedback)
        else SemanticReviewFeedback.model_validate(value)
    )
    if feedback.effective_mode == "off":
        return None
    return feedback.model_dump(mode="json")


def inert_markdown(text: str) -> str:
    """Model text is prose, never HTML, Markdown links, images or code fences."""
    escaped = html.escape(text, quote=True)
    return re.sub(r"([\\`*_{}\[\]()#!|>])", r"\\\1", escaped).replace("\n", " ")


def semantic_markdown(value: Any) -> str:
    payload = feedback_payload(value)
    if payload is None:
        return ""
    status = inert_markdown(payload["status"])
    reason = inert_markdown(payload["reason_code"])
    lines = [
        "",
        "Semantic review (advisory only): " + status + " / " + reason + ".",
        "Reviewer: "
        + inert_markdown(payload["reviewer_id"])
        + " version "
        + inert_markdown(payload["reviewer_version"])
        + ".",
        "Docs alignment: " + inert_markdown(payload["docs_alignment"]) + ".",
        "Semantic review is an LLM opinion; requirements remain unverified.",
    ]
    if payload["status"] == "reviewed" and not payload["findings"]:
        lines.append(
            "The model reported no concerns; this does not prove requirements are satisfied."
        )
    if payload.get("context_digest"):
        lines.append("Review context digest: " + payload["context_digest"] + ".")
    return "\n".join(lines)
