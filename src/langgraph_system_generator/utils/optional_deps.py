"""Helpers for optional dependency loading with friendly error messages."""

from __future__ import annotations

from importlib import import_module
from typing import Any


class OptionalDependencyError(RuntimeError):
    """Raised when an optional dependency group is required but unavailable."""

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        dependency: str | None = None,
        extra: str | None = None,
        feature: str | None = None,
    ) -> None:
        super().__init__(message)
        self.hint = hint
        self.dependency = dependency
        self.extra = extra
        self.feature = feature


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
            f"Install the '{extra}' extra with: {hint}",
            hint=hint,
            dependency=module_name,
            extra=extra,
            feature=feature,
        ) from exc
    except ImportError:
        raise


def missing_external_tool(
    tool_name: str,
    *,
    feature: str,
    hint: str,
) -> OptionalDependencyError:
    """Create a consistent error for missing external tools."""

    return OptionalDependencyError(
        f"{feature} requires the external tool '{tool_name}', but it is not available.",
        hint=hint,
        dependency=tool_name,
        feature=feature,
    )
