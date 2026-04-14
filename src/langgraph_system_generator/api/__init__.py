"""API package for LangGraph Notebook Foundry."""

from __future__ import annotations

from langgraph_system_generator.utils.optional_deps import require_optional_module

__all__ = ["app"]


def __getattr__(name: str):
    """Lazily expose the FastAPI app so core installs do not import API extras."""

    if name != "app":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    server_module = require_optional_module(
        "langgraph_system_generator.api.server",
        feature="The FastAPI server",
        extra="api",
    )
    return server_module.app
