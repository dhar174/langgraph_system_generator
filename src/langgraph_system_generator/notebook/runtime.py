"""Runtime helpers for notebook execution checks."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from shutil import which
from typing import Any

import nbformat
from nbformat import NotebookNode

def inspect_kernel_spec(kernel_name: str = "python3") -> tuple[bool, str]:
    """Return whether the requested kernel spec looks executable."""

    try:
        from jupyter_client.kernelspec import KernelSpecManager, NoSuchKernel
    except ImportError as exc:
        return False, f"Runtime validation unavailable: missing jupyter_client ({exc})"

    manager = KernelSpecManager()
    try:
        spec = manager.get_kernel_spec(kernel_name)
    except NoSuchKernel:
        return False, f"Runtime validation unavailable: kernel '{kernel_name}' is not registered."

    if not spec.argv:
        return False, f"Runtime validation unavailable: kernel '{kernel_name}' has no launch command."

    executable = spec.argv[0]
    executable_path = Path(executable)
    if not executable_path.exists() and which(executable) is None:
        return (
            False,
            f"Runtime validation unavailable: kernel '{kernel_name}' points to missing executable '{executable}'.",
        )

    return True, f"Kernel '{kernel_name}' is available for notebook execution."


def inspect_notebook_runtime_support(
    kernel_name: str = "python3",
) -> tuple[bool, str, dict[str, Any]]:
    """Return whether notebook execution support is available."""

    kernel_ok, kernel_message = inspect_kernel_spec(kernel_name)
    evidence: dict[str, Any] = {
        "kernel_name": kernel_name,
        "kernel_message": kernel_message,
    }
    if not kernel_ok:
        evidence["failure_kind"] = "runtime_unavailable"
        return False, kernel_message, evidence

    try:
        from nbclient.client import NotebookClient  # noqa: F401
    except ImportError as exc:
        message = (
            "Runtime validation unavailable: missing notebook execution dependency "
            f"({exc})."
        )
        evidence["failure_kind"] = "runtime_unavailable"
        evidence["dependency_error"] = str(exc)
        return False, message, evidence

    evidence["kernel_available"] = True
    evidence["execution_dependency_available"] = True
    return True, kernel_message, evidence


def _load_notebook(notebook: str | Path | NotebookNode) -> NotebookNode:
    """Normalize a notebook path or object into a NotebookNode."""

    if isinstance(notebook, NotebookNode):
        return notebook

    path = Path(notebook)
    with path.open("r", encoding="utf-8") as handle:
        return nbformat.read(handle, as_version=4)


def execute_notebook(
    notebook: str | Path | NotebookNode,
    kernel_name: str = "python3",
    timeout: int = 60,
) -> tuple[bool, str, dict[str, Any]]:
    """Execute the provided notebook and return structured execution evidence."""

    try:
        from nbclient.client import NotebookClient
    except ImportError as exc:
        message = (
            "Runtime validation unavailable: missing notebook execution dependency "
            f"({exc})."
        )
        return False, message, {
            "kernel_name": kernel_name,
            "failure_kind": "runtime_unavailable",
            "dependency_error": str(exc),
        }

    try:
        loaded = _load_notebook(notebook)
    except Exception as exc:
        return False, f"Runtime execution failed: {type(exc).__name__}: {exc}", {
            "kernel_name": kernel_name,
            "failure_kind": "execution_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    client = NotebookClient(loaded, timeout=timeout, kernel_name=kernel_name)

    try:
        executed = client.execute()
    except Exception as exc:  # pragma: no cover - exercised through callers
        return False, f"Runtime execution failed: {type(exc).__name__}: {exc}", {
            "kernel_name": kernel_name,
            "failure_kind": "execution_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    code_cells = 0
    output_count = 0
    for cell in executed.cells:
        if cell.cell_type != "code":
            continue
        code_cells += 1
        output_count += len(cell.get("outputs", []))

    return True, f"Generated notebook executed successfully using the '{kernel_name}' kernel.", {
        "kernel_name": kernel_name,
        "executed_cells": code_cells,
        "output_count": output_count,
    }


@lru_cache(maxsize=8)
def run_notebook_smoke_test(
    kernel_name: str = "python3", timeout: int = 60
) -> tuple[bool, str]:
    """Execute a tiny notebook to verify notebook runtime support."""

    from nbformat.v4 import new_code_cell, new_notebook

    runtime_ok, runtime_message, _ = inspect_notebook_runtime_support(kernel_name)
    if not runtime_ok:
        return False, runtime_message

    notebook = new_notebook(cells=[new_code_cell("value = 2 + 2\nprint(value)")])
    passed, _message, evidence = execute_notebook(
        notebook,
        kernel_name=kernel_name,
        timeout=timeout,
    )

    if passed and evidence.get("output_count", 0) >= 1:
        return True, f"Runtime execution environment validated using the '{kernel_name}' kernel."

    return False, "Runtime validation failed: smoke notebook executed without the expected output."
