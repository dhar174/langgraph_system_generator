"""Runtime helpers for notebook execution checks."""

from __future__ import annotations

from pathlib import Path
from shutil import which


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


def run_notebook_smoke_test(kernel_name: str = "python3", timeout: int = 60) -> tuple[bool, str]:
    """Execute a tiny notebook to verify notebook runtime support."""

    kernel_ok, kernel_message = inspect_kernel_spec(kernel_name)
    if not kernel_ok:
        return False, kernel_message

    try:
        from nbclient.client import NotebookClient
        from nbformat.v4 import new_code_cell, new_notebook
    except ImportError as exc:
        return False, f"Runtime validation unavailable: missing notebook execution dependency ({exc})."

    notebook = new_notebook(cells=[new_code_cell("value = 2 + 2\nprint(value)")])
    client = NotebookClient(notebook, timeout=timeout, kernel_name=kernel_name)

    try:
        executed = client.execute()
    except Exception as exc:  # pragma: no cover - exercised through callers
        return False, f"Runtime validation failed: {type(exc).__name__}: {exc}"

    outputs = []
    for cell in executed.cells:
        if cell.cell_type != "code":
            continue
        for output in cell.get("outputs", []):
            text = output.get("text")
            if text:
                outputs.append(str(text))

    if any("4" in output for output in outputs):
        return True, f"Runtime execution environment validated using the '{kernel_name}' kernel."

    return False, "Runtime validation failed: smoke notebook executed without the expected output."
