"""Shared constants and helpers for the LangGraph Notebook Foundry package."""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT_BASE_ENV = "LNF_OUTPUT_BASE"
DEFAULT_OUTPUT_BASE = Path.home() / ".lnf_output"


def _resolve_output_base() -> Path:
    """Return the configured output base without creating directories.

    The path is resolved eagerly for consistent comparisons, but directory
    creation is intentionally deferred to avoid import-time permission errors
    when the package is installed in read-only locations.
    """
    env_value = os.environ.get(OUTPUT_BASE_ENV)
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        home = Path.home().resolve()
        # Ensure the environment override stays within the user's home directory.
        try:
            # Python 3.9+: use Path.is_relative_to if available
            is_within_home = candidate.is_relative_to(home)  # type: ignore[attr-defined]
        except AttributeError:
            try:
                candidate.relative_to(home)
                is_within_home = True
            except ValueError:
                is_within_home = False
        if is_within_home:
            return candidate
    return DEFAULT_OUTPUT_BASE.resolve()


def is_relative_to_base(path: Path, base: Path) -> bool:
    """Compatibility helper for Path.is_relative_to (Python <3.9 fallback)."""
    try:
        return path.is_relative_to(base)  # type: ignore[attr-defined]
    except AttributeError:
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False


# Global, resolved output base. Directory creation is deferred.
OUTPUT_BASE: Path = _resolve_output_base()

__all__ = ["OUTPUT_BASE", "OUTPUT_BASE_ENV", "DEFAULT_OUTPUT_BASE", "is_relative_to_base"]
