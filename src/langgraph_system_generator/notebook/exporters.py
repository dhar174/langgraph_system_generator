"""Utilities to export notebooks into distributable formats."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Sequence

import nbformat


class NotebookExporter:
    """Exports nbformat notebooks to files or bundles."""

    def export_ipynb(self, notebook: nbformat.NotebookNode, path: str | Path) -> str:
        """Write a validated notebook to disk."""
        nbformat.validate(notebook)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            nbformat.write(notebook, handle)
        return str(target)

    def export_zip(
        self,
        notebook: nbformat.NotebookNode,
        zip_path: str | Path,
        extra_files: Sequence[str | os.PathLike[str]] | None = None,
        notebook_name: str = "notebook.ipynb",
    ) -> str:
        """Create a zip bundle containing the notebook and optional artifacts."""
        nbformat.validate(notebook)
        buffer = io.StringIO()
        nbformat.write(notebook, buffer)

        target = Path(zip_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(notebook_name, buffer.getvalue())
            for extra in extra_files or []:
                extra_path = Path(extra)
                if extra_path.is_file():
                    zf.write(extra_path, arcname=extra_path.name)
        return str(target)
