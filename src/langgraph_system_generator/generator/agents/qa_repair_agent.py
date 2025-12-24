"""QA & Repair Agent for validating and repairing generated notebooks."""

from __future__ import annotations

from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.state import CellSpec, QAReport
from langgraph_system_generator.utils.config import settings


class QARepairAgent:
    """Validates and repairs generated notebooks."""

    def __init__(self, model: str | None = None):
        self.llm = ChatOpenAI(model=model or settings.default_model, temperature=0)

    async def validate(self, cells: List[CellSpec]) -> List[QAReport]:
        """Run all quality checks on generated cells.

        Args:
            cells: List of cell specifications to validate

        Returns:
            List of QA reports for each check
        """
        reports = []

        # Check for placeholders
        reports.append(self._check_no_placeholders(cells))

        # Check for basic structure
        reports.append(self._check_basic_structure(cells))

        # Check for imports
        reports.append(self._check_has_imports(cells))

        return reports

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
        """Attempt to fix issues identified in QA.

        Args:
            cells: Original cell specifications
            qa_reports: QA reports with issues to fix

        Returns:
            Repaired cell specifications
        """
        failed_reports = [r for r in qa_reports if not r.passed]

        if not failed_reports:
            return cells

        # Create repair prompt
        issues = "\n".join([f"- {r.check_name}: {r.message}" for r in failed_reports])

        repair_prompt = SystemMessage(
            content="""You are a notebook repair specialist.
Fix the identified issues in the notebook cells while maintaining their structure and purpose.

Focus on:
1. Replacing placeholders with working code
2. Adding missing imports
3. Ensuring proper cell structure
4. Maintaining code quality

Return suggestions as a list of specific changes."""
        )

        cells_summary = "\n".join(
            [
                f"Cell {i} ({cell.cell_type}): {cell.content[:100]}..."
                for i, cell in enumerate(cells[:10])
            ]
        )

        user_message = HumanMessage(
            content=f"""Issues Found:
{issues}

Cells:
{cells_summary}

Suggest specific repairs."""
        )

        # Get repair suggestions from LLM (currently unused as repair is not fully implemented)
        await self.llm.ainvoke([repair_prompt, user_message])

        # For now, return original cells as we need more context for repairs
        # In a full implementation, we'd parse the LLM response and apply fixes
        return cells
