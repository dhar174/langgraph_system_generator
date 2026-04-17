"""Tests for optional dependency guard behavior."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from langgraph_system_generator.cli import generate_artifacts
from langgraph_system_generator.utils import optional_deps


def test_require_optional_module_mentions_requested_extra(monkeypatch):
    """Missing optional imports should point to the correct extra."""

    def raise_import_error(_name):
        raise ModuleNotFoundError("missing dependency")

    monkeypatch.setattr(optional_deps, "import_module", raise_import_error)

    with pytest.raises(optional_deps.OptionalDependencyError) as exc_info:
        optional_deps.require_optional_module(
            "fake.module",
            feature="Artifact generation",
            extra="full",
        )

    assert 'pip install -e ".[full]"' in str(exc_info.value)


@pytest.mark.asyncio
async def test_generate_artifacts_raises_friendly_error_when_full_extra_missing(monkeypatch, tmp_path):
    """Artifact generation should fail with an actionable optional-deps message."""

    def guarded_import(name):
        if name == "langgraph_system_generator.notebook.composer":
            raise ModuleNotFoundError("missing notebook deps")
        return importlib.import_module(name)

    monkeypatch.setattr(optional_deps, "import_module", guarded_import)

    with pytest.raises(optional_deps.OptionalDependencyError) as exc_info:
        await generate_artifacts("test prompt", output_dir=tmp_path, mode="stub")

    assert 'pip install -e ".[full]"' in str(exc_info.value)


def test_require_optional_module_surfaces_non_module_import_errors(monkeypatch):
    """Import-time errors inside installed modules should not be rewrapped."""

    def raise_import_error(_name):
        raise ImportError("cannot import name 'broken_symbol' from 'installed_package'")

    monkeypatch.setattr(optional_deps, "import_module", raise_import_error)

    with pytest.raises(ImportError, match="broken_symbol"):
        optional_deps.require_optional_module(
            "installed_package.feature",
            feature="Artifact generation",
            extra="full",
        )


def test_api_package_exposes_app_lazily(monkeypatch):
    """The API package should lazy-load the FastAPI app."""
    api_module = importlib.import_module("langgraph_system_generator.api")

    monkeypatch.setattr(
        api_module,
        "require_optional_module",
        lambda *args, **kwargs: SimpleNamespace(app="sentinel-app"),
    )

    assert api_module.app == "sentinel-app"


def test_api_package_surfaces_missing_api_extra(monkeypatch):
    """Missing API extras should produce an actionable error when app is accessed."""
    api_module = importlib.import_module("langgraph_system_generator.api")

    def raise_optional_error(*_args, **_kwargs):
        raise optional_deps.OptionalDependencyError("Install with pip install -e \".[api]\"")

    monkeypatch.setattr(api_module, "require_optional_module", raise_optional_error)

    with pytest.raises(optional_deps.OptionalDependencyError) as exc_info:
        _ = api_module.app

    assert '".[api]"' in str(exc_info.value)
