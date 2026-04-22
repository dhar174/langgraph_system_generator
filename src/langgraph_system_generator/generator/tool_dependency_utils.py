"""Shared dependency normalization helpers for tool planning and notebooks."""

from __future__ import annotations

from dataclasses import dataclass, field
import keyword
import re
from typing import Any, Mapping


_PACKAGE_IMPORT_PROBES = {
    "langgraph": "langgraph",
    "langchain-core": "langchain_core",
    "langchain-openai": "langchain_openai",
    "langchain-community": "langchain_community",
    "pydantic": "pydantic",
    "pypdf": "pypdf",
    "pdfminer.six": "pdfminer",
    "pymupdf": "fitz",
    "requests": "requests",
}

_PACKAGE_FAMILIES = {
    "pypdf": "pdf_parser",
    "pdfminer.six": "pdf_parser",
    "pymupdf": "pdf_parser",
}


def normalize_inline_text(value: Any, fallback: str) -> str:
    """Normalize arbitrary text for safe single-line comments and messages."""

    text = str(value or fallback).replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(part.strip() for part in text.split("\n") if part.strip())
    return text or fallback


def merge_string_lists(*values: Any) -> list[str]:
    """Merge list-or-scalar string inputs into an ordered unique list."""

    merged: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = [value]
        for raw_item in raw_items:
            text = str(raw_item or "").strip()
            if text and text not in merged:
                merged.append(text)
    return merged


def normalize_provider_env_var(value: Any) -> str:
    """Normalize arbitrary env-var suggestions into notebook-safe keys."""

    text = str(value or "").strip()
    if not text:
        return ""

    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", text)
    normalized = re.sub(r"_+", "_", normalized).strip("_").upper()
    if not normalized:
        return ""
    if normalized[0].isdigit():
        normalized = f"ENV_{normalized}"
    if keyword.iskeyword(normalized.lower()) or not normalized.isidentifier():
        normalized = f"ENV_{normalized}"
    return normalized


def package_import_probe(package_name: str) -> str:
    """Return the import probe used to detect whether a package is installed."""

    return _PACKAGE_IMPORT_PROBES.get(
        package_name,
        package_name.replace("-", "_").replace(".", "_"),
    )


@dataclass
class DependencyAccumulator:
    """Mutable normalized dependency accumulator used by planner and composer."""

    packages: list[str] = field(default_factory=list)
    provider_env_vars: list[str] = field(default_factory=list)
    runtime_notes: list[str] = field(default_factory=list)
    conflicts_resolved: list[str] = field(default_factory=list)
    selected_families: dict[str, str] = field(default_factory=dict, repr=False)


def add_dependency_candidate(
    accumulator: DependencyAccumulator,
    package_name: str,
    *,
    family: str | None = None,
    requested_by: str | None = None,
) -> None:
    """Add a dependency candidate while deduplicating and resolving conflicts."""

    normalized_package = str(package_name or "").strip()
    if not normalized_package:
        return

    dependency_family = family or _PACKAGE_FAMILIES.get(normalized_package)
    if dependency_family:
        chosen = accumulator.selected_families.get(dependency_family)
        if chosen and chosen != normalized_package:
            detail = (
                f"Kept '{chosen}' instead of '{normalized_package}' "
                f"for dependency family '{dependency_family}'."
            )
            if requested_by:
                detail += f" Requested by {requested_by}."
            if detail not in accumulator.conflicts_resolved:
                accumulator.conflicts_resolved.append(detail)
            return
        accumulator.selected_families[dependency_family] = normalized_package

    if normalized_package not in accumulator.packages:
        accumulator.packages.append(normalized_package)


def iter_tool_package_candidates(tool: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    """Return package candidates implied by a normalized tool mapping."""

    category = normalize_inline_text(tool.get("category", ""), "").lower()
    tool_configuration = tool.get("configuration")
    if not isinstance(tool_configuration, Mapping):
        tool_configuration = {}

    candidates: list[tuple[str, str | None]] = [
        (package_name, None)
        for package_name in merge_string_lists(
            tool.get("packages"),
            tool_configuration.get("packages"),
        )
    ]

    if "search" in category:
        candidates.append(("langchain-community", None))
    if any(token in category for token in {"file", "document", "pdf"}):
        candidates.append(("pypdf", "pdf_parser"))
    if "api" in category:
        candidates.append(("requests", None))

    return candidates


def accumulate_tool_dependencies(
    accumulator: DependencyAccumulator,
    tool: Mapping[str, Any],
) -> None:
    """Merge one tool's dependencies into the shared accumulator."""

    requested_by = normalize_inline_text(tool.get("name", ""), "tool")

    for package_name, family in iter_tool_package_candidates(tool):
        add_dependency_candidate(
            accumulator,
            package_name,
            family=family,
            requested_by=requested_by,
        )

    tool_configuration = tool.get("configuration")
    if not isinstance(tool_configuration, Mapping):
        tool_configuration = {}

    provider_env_vars = merge_string_lists(
        tool.get("provider_env_vars"),
        tool_configuration.get("provider_env_vars"),
    )
    for env_var in provider_env_vars:
        raw_env_var = str(env_var or "").strip()
        normalized_env_var = normalize_provider_env_var(env_var)
        if not normalized_env_var:
            if raw_env_var:
                note = (
                    f"Ignored provider env var '{raw_env_var}' because it could not "
                    "be normalized into a notebook-safe key."
                )
                if note not in accumulator.runtime_notes:
                    accumulator.runtime_notes.append(note)
            continue

        if raw_env_var and normalized_env_var != raw_env_var:
            note = (
                f"Normalized provider env var '{raw_env_var}' to "
                f"'{normalized_env_var}' for notebook-safe configuration."
            )
            if note not in accumulator.runtime_notes:
                accumulator.runtime_notes.append(note)
        if normalized_env_var not in accumulator.provider_env_vars:
            accumulator.provider_env_vars.append(normalized_env_var)
