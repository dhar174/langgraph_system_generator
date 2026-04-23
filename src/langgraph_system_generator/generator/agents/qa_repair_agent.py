"""QA & Repair Agent for validating and repairing generated notebooks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List

from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.agents._llm import build_chat_llm
from langgraph_system_generator.generator.state import CellSpec, QAReport
from langgraph_system_generator.notebook.composer import (
    NotebookComposer as NotebookFileComposer,
)
from langgraph_system_generator.qa.repair import NotebookRepairAgent
from langgraph_system_generator.qa.validators import NotebookValidator
from langgraph_system_generator.utils.config import ModelConfig


class QARepairAgent:
    """Validates and repairs generated notebooks."""

    def __init__(
        self,
        model: str | None = None,
        model_config: ModelConfig | None = None,
    ):
        self.llm = build_chat_llm(
            model=model,
            model_config=model_config,
            chat_openai_class=ChatOpenAI,
        )
        self.repair_engine = NotebookRepairAgent()

    async def validate(self, cells: List[CellSpec]) -> List[QAReport]:
        """Run all quality checks on generated cells.

        Args:
            cells: List of cell specifications to validate

        Returns:
            List of QA reports for each check
        """
        notebook_builder = NotebookFileComposer()
        validator = NotebookValidator()

        with TemporaryDirectory() as temp_dir:
            notebook = notebook_builder.build_notebook(cells)
            notebook_path = Path(temp_dir) / "generated.ipynb"
            notebook_builder.write(notebook, notebook_path)
            return validator.validate_all(notebook_path)

    def _check_no_placeholders(self, cells: List[CellSpec]) -> QAReport:
        """Ensure no TODO or placeholder text in critical cells."""
        placeholders = ["TODO", "FIXME", "PLACEHOLDER"]
        found_placeholders = []

        for i, cell in enumerate(cells):
            if cell.cell_type == "code":
                for placeholder in placeholders:
                    if placeholder in cell.content:
                        found_placeholders.append(f"Cell {i}: {placeholder}")

        if found_placeholders:
            return QAReport(
                check_name="No Placeholders",
                passed=False,
                message=f"Found placeholders: {', '.join(found_placeholders[:3])}",
                suggestions=[
                    "Replace TODO comments with actual implementations",
                    "Remove FIXME markers",
                ],
            )

        return QAReport(
            check_name="No Placeholders",
            passed=True,
            message="No critical placeholders found",
        )

    def _check_basic_structure(self, cells: List[CellSpec]) -> QAReport:
        """Check for basic notebook structure."""
        has_markdown = any(cell.cell_type == "markdown" for cell in cells)
        has_code = any(cell.cell_type == "code" for cell in cells)

        if not has_markdown or not has_code:
            return QAReport(
                check_name="Basic Structure",
                passed=False,
                message="Notebook missing markdown or code cells",
                suggestions=["Add both markdown and code cells for proper structure"],
            )

        return QAReport(
            check_name="Basic Structure",
            passed=True,
            message="Notebook has proper cell structure",
        )

    def _check_has_imports(self, cells: List[CellSpec]) -> QAReport:
        """Check that necessary imports are present."""
        all_code = "\n".join(
            [cell.content for cell in cells if cell.cell_type == "code"]
        )

        required_imports = ["langgraph", "StateGraph"]
        missing_imports = []

        for imp in required_imports:
            if imp not in all_code:
                missing_imports.append(imp)

        if missing_imports:
            return QAReport(
                check_name="Required Imports",
                passed=False,
                message=f"Missing imports: {', '.join(missing_imports)}",
                suggestions=[f"Add import for {imp}" for imp in missing_imports[:2]],
            )

        return QAReport(
            check_name="Required Imports",
            passed=True,
            message="All required imports present",
        )

    async def repair(
        self, cells: List[CellSpec], qa_reports: List[QAReport]
    ) -> List[CellSpec]:
        """Attempt to fix issues identified in QA through the shared repair engine.

        Args:
            cells: Original cell specifications
            qa_reports: QA reports with issues to fix

        Returns:
            Repaired cell specifications
        """
        if not any(not report.passed for report in qa_reports):
            return cells

        outcome = await asyncio.to_thread(
            self.repair_engine.repair_cells,
            cells,
            qa_reports,
            0,
        )
        return outcome.cells if outcome.success else cells
