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

    CANONICAL_SECTION_ORDER = [
        "intro",
        "setup",
        "config",
        "state",
        "tools",
        "nodes",
        "graph",
        "execution",
        "export",
        "troubleshooting",
    ]
    SECTION_ALIASES = {
        "state_definition": "state",
    }

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
            ensure_minimum_sections: When True, merge required scaffold
                sections into the canonical notebook order.

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
        """Ensure required sections are present in the public notebook contract.

        Recognized notebook sections are grouped into the canonical execution
        order when minimum scaffolding is enabled. Unsectioned or unknown user
        cells stay in their original relative order and are preserved ahead of
        the canonical sections. Legacy ``state_definition`` cells are treated as
        ``state`` for ordering so older stub generators still produce runnable
        notebooks.
        """
        provided_sections = {c.section for c in cells if c.section}
        scaffold: List[CellSpec] = []
        architecture_type = self._infer_architecture_type(cells)

        required: Iterable[tuple[str, Iterable[CellSpec]]] = [
            ("setup", templates.installation_and_imports()),
            ("config", templates.configuration_cell()),
            ("graph", templates.build_graph_cells()),
            ("execution", templates.run_graph_cells(architecture_type)),
            ("export", templates.export_results_cells()),
            ("troubleshooting", templates.troubleshooting_cell()),
        ]

        for section_name, section_cells in required:
            if section_name not in provided_sections:
                scaffold.extend(section_cells)

        return self._order_sections([*cells, *scaffold])

    def _order_sections(self, cells: Sequence[CellSpec]) -> List[CellSpec]:
        """Return cells grouped by the public notebook section order."""

        section_positions = {
            section: index
            for index, section in enumerate(self.CANONICAL_SECTION_ORDER)
        }
        known_sections: dict[str, List[CellSpec]] = {
            section: [] for section in self.CANONICAL_SECTION_ORDER
        }
        unknown_sections: List[CellSpec] = []

        for cell in cells:
            section = self._canonical_section(cell.section) or ""
            if section in section_positions:
                known_sections[section].append(cell)
            else:
                unknown_sections.append(cell)

        ordered: List[CellSpec] = list(unknown_sections)
        for section in self.CANONICAL_SECTION_ORDER:
            ordered.extend(known_sections[section])
        return ordered

    @classmethod
    def _canonical_section(cls, section: str | None) -> str | None:
        """Normalize legacy section aliases used by older notebook generators."""
        if section is None:
            return None
        return cls.SECTION_ALIASES.get(section, section)

    @staticmethod
    def _infer_architecture_type(cells: Sequence[CellSpec]) -> str | None:
        """Infer the generated architecture from state/node cells."""
        combined_content = "\n".join(
            cell.content for cell in cells if cell.section in {"state", "state_definition", "nodes", "graph"}
        )
        lowered = combined_content.lower()

        if "revision_count:" in lowered and "critique_feedback:" in lowered:
            return "critique_loop"
        if "task_results:" in lowered and "instructions:" in lowered:
            return "subagents"
        if "route:" in lowered and "final_output:" in lowered:
            return "router"
        return None
