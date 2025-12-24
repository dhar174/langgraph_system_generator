"""Notebook composer to build runnable nbformat notebooks."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence

import nbformat
from nbformat import NotebookNode
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from langgraph_system_generator.generator.state import CellSpec
from langgraph_system_generator.notebook import templates


class NotebookComposer:
    """Create nbformat notebooks from structured cell specifications."""

    def __init__(self, colab_friendly: bool = True):
        self.colab_friendly = colab_friendly

    def build_notebook(
        self,
        cells: Sequence[CellSpec],
        ensure_minimum_sections: bool = True,
    ) -> NotebookNode:
        """Convert CellSpec entries into a validated NotebookNode.

        Args:
            cells: Ordered collection of CellSpec definitions.
            ensure_minimum_sections: When True, prepend required scaffold
                sections (installation, configuration, build/run/export, troubleshooting).

        Returns:
            nbformat.NotebookNode ready to write to disk.
        """
        ordered_cells: List[CellSpec] = list(cells)

        if ensure_minimum_sections:
            ordered_cells = self._with_required_sections(ordered_cells)

        notebook = new_notebook()
        notebook.metadata.setdefault("kernelspec", {"display_name": "Python 3", "name": "python3"})
        notebook.metadata.setdefault("language_info", {"name": "python"})
        if self.colab_friendly:
            notebook.metadata.setdefault("colab", {"provenance": []})

        for cell_spec in ordered_cells:
            cell = (
                new_markdown_cell(cell_spec.content)
                if cell_spec.cell_type == "markdown"
                else new_code_cell(cell_spec.content)
            )
            if cell_spec.section:
                cell.metadata.setdefault("section", cell_spec.section)
            if cell_spec.metadata:
                cell.metadata.update(cell_spec.metadata)
            notebook.cells.append(cell)

        nbformat.validate(notebook)
        return notebook

    def write(self, notebook: NotebookNode, path: str | Path) -> str:
        """Write a notebook to disk after validation."""
        nbformat.validate(notebook)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            nbformat.write(notebook, handle)
        return str(target)

    def _with_required_sections(self, cells: Sequence[CellSpec]) -> List[CellSpec]:
        """Ensure required sections are present and ordered for Colab-friendly execution."""
        provided_sections = {c.section for c in cells if c.section}
        scaffold: List[CellSpec] = []

        required: Iterable[tuple[str, Iterable[CellSpec]]] = [
            ("setup", templates.installation_and_imports()),
            ("config", templates.configuration_cell()),
            ("graph", templates.build_graph_cells()),
            ("execution", templates.run_graph_cells()),
            ("export", templates.export_results_cells()),
            ("troubleshooting", templates.troubleshooting_cell()),
        ]

        for section_name, section_cells in required:
            if section_name not in provided_sections:
                scaffold.extend(section_cells)

        scaffold.extend(cells)
        return scaffold
