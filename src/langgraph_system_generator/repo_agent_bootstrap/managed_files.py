from __future__ import annotations

import re

MANAGED_START = "<!-- repo-agent-bootstrap:managed:start -->"
MANAGED_END = "<!-- repo-agent-bootstrap:managed:end -->"


def wrap_managed_block(body: str, *, file_kind: str, provenance: str) -> str:
    """Wrap generated content in a managed block that maintenance runs can replace."""

    body = body.strip() + "\n"
    return (
        f"<!-- repo-agent-bootstrap:file-kind={file_kind} -->\n"
        f"<!-- repo-agent-bootstrap:provenance={provenance} -->\n"
        f"{MANAGED_START}\n"
        f"{body}"
        f"{MANAGED_END}\n"
    )


def merge_managed_text(existing_text: str, new_text: str) -> str:
    """Replace only the managed block when one exists, preserving user prose around it."""

    existing_block = _extract_managed_block(existing_text)
    new_block = _extract_managed_block(new_text)

    if not new_block:
        return new_text

    if existing_block:
        start, end, _ = existing_block
        return existing_text[:start] + new_block[2] + existing_text[end:]

    existing_text = existing_text.rstrip()
    if not existing_text:
        return new_text
    return existing_text + "\n\n" + new_block


def _extract_managed_block(text: str) -> tuple[int, int, str] | None:
    pattern = re.compile(
        r"<!-- repo-agent-bootstrap:file-kind=.*?-->\s*"
        r"<!-- repo-agent-bootstrap:provenance=.*?-->\s*"
        r"<!-- repo-agent-bootstrap:managed:start -->.*?<!-- repo-agent-bootstrap:managed:end -->\n?",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    return match.start(), match.end(), match.group(0)
