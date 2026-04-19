"""Helpers for optional dependency loading with friendly error messages."""

from __future__ import annotations

from importlib import import_module
from typing import Any


class OptionalDependencyError(RuntimeError):
    """Raised when an optional dependency group is required but unavailable."""


_EXTRA_HINTS = {
    "api": 'pip install -e ".[api]"',
    "full": 'pip install -e ".[full]"',
}


def require_optional_module(module_name: str, *, feature: str, extra: str) -> Any:
    """Import an optional module or raise a friendly runtime error."""
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        hint = _EXTRA_HINTS.get(extra, f'pip install -e ".[{extra}]"')
        raise OptionalDependencyError(
            f"{feature} requires optional dependencies that are not installed. "
            f"Install the '{extra}' extra with: {hint}"
        ) from exc
    except ImportError:
        raise
