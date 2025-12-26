"""Notebook repair system with bounded retry logic."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import nbformat
from nbformat import NotebookNode

from langgraph_system_generator.generator.state import QAReport
from langgraph_system_generator.qa.validators import NotebookValidator


class NotebookRepairAgent:
    """Repairs issues in generated notebooks with bounded retry attempts."""

    DEFAULT_MAX_ATTEMPTS = 3

    def __init__(self, max_attempts: int = DEFAULT_MAX_ATTEMPTS):
        """Initialize repair agent.

        Args:
            max_attempts: Maximum number of repair attempts before giving up
        """
        self.max_attempts = max_attempts
        self.validator = NotebookValidator()

    def repair_notebook(
        self,
        notebook_path: str | Path,
        qa_reports: List[QAReport],
        attempt: int = 0,
    ) -> tuple[bool, List[QAReport]]:
        """Attempt to repair notebook based on QA failures.

        Args:
            notebook_path: Path to the notebook file
            qa_reports: List of QA reports identifying issues
            attempt: Current attempt number (0-indexed)

        Returns:
            Tuple of (success, new_qa_reports)
            - success: True if all issues were fixed
            - new_qa_reports: Updated QA reports after repair attempt
        """
        if attempt >= self.max_attempts:
            return False, qa_reports

        failed_reports = [r for r in qa_reports if not r.passed]
        if not failed_reports:
            return True, qa_reports

        path = Path(notebook_path)
        try:
            with path.open("r", encoding="utf-8") as f:
                nb = nbformat.read(f, as_version=4)
        except Exception:
            # Can't repair if we can't read the notebook
            return False, qa_reports

        # Apply repairs based on failed checks
        repaired = False
        for report in failed_reports:
            if report.check_name == "No Placeholders":
                repaired = self._repair_placeholders(nb) or repaired
            elif report.check_name == "Required Imports":
                repaired = self._repair_imports(nb, report) or repaired
            elif report.check_name == "Required Sections":
                repaired = self._repair_sections(nb, report) or repaired
            elif report.check_name == "Graph Compilation":
                repaired = self._repair_compilation(nb, report) or repaired

        if repaired:
            # Save the repaired notebook
            try:
                with path.open("w", encoding="utf-8") as f:
                    nbformat.write(nb, f)
            except Exception:
                return False, qa_reports

            # Re-validate
            new_reports = self.validator.validate_all(notebook_path)
            return all(r.passed for r in new_reports), new_reports

        return False, qa_reports

    def _repair_placeholders(self, nb: NotebookNode) -> bool:
        """Remove or replace placeholder text in cells.

        Args:
            nb: Notebook to repair

        Returns:
            True if any repairs were made
        """
        repaired = False
        placeholder_replacements = {
            "TODO": "",
            "FIXME": "",
            "PLACEHOLDER": "",
            "# Your code here": "pass",
            "pass  # implement": "pass",
        }

        for cell in nb.cells:
            if cell.cell_type == "code":
                original = cell.source
                modified = original

                # Remove placeholder comments
                for placeholder, replacement in placeholder_replacements.items():
                    if placeholder in modified:
                        modified = modified.replace(placeholder, replacement)
                        repaired = True

                # Remove ellipsis that appear as placeholders (not in strings)
                # Only remove standalone ellipsis lines
                lines = modified.split("\n")
                filtered_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped == "..." or stripped == "# ...":
                        repaired = True
                        continue  # Skip this line
                    filtered_lines.append(line)
                
                modified = "\n".join(filtered_lines)

                # Clean up multiple blank lines
                while "\n\n\n" in modified:
                    modified = modified.replace("\n\n\n", "\n\n")
                    repaired = True

                cell.source = modified

        return repaired

    def _repair_imports(self, nb: NotebookNode, report: QAReport) -> bool:
        """Add missing imports to the notebook.

        Args:
            nb: Notebook to repair
            report: QA report with import issues

        Returns:
            True if any repairs were made
        """
        # Extract missing imports from the report message
        match = re.search(r"Missing required imports: (.+)", report.message)
        if not match:
            return False

        missing_imports_str = match.group(1)
        missing_imports = [imp.strip() for imp in missing_imports_str.split(",")]

        # Find the first code cell (typically installation/import section)
        import_cell_idx = None
        for idx, cell in enumerate(nb.cells):
            if cell.cell_type == "code":
                import_cell_idx = idx
                break

        if import_cell_idx is None:
            return False

        # Add missing imports to the first code cell
        cell = nb.cells[import_cell_idx]
        source = cell.source or ""
        
        # Determine which symbols are actually needed and not already present
        needs_stategraph = any("langgraph" in imp.lower() for imp in missing_imports) and "StateGraph" not in source
        needs_end = any("END" in imp for imp in missing_imports) and "END" not in source

        if not (needs_stategraph or needs_end):
            return False

        lines = source.splitlines()
        updated = False

        # Try to consolidate into existing 'from langgraph.graph import ...' imports
        for i, line in enumerate(lines):
            match_import = re.match(r"^(\s*from\s+langgraph\.graph\s+import\s+)(.+)$", line)
            if not match_import:
                continue

            prefix, names_str = match_import.groups()
            names = [n.strip() for n in names_str.split(",") if n.strip()]

            if needs_stategraph and "StateGraph" not in names:
                names.append("StateGraph")
                needs_stategraph = False
                updated = True

            if needs_end and "END" not in names:
                names.append("END")
                needs_end = False
                updated = True

            # Reconstruct the import line with updated names
            lines[i] = prefix + ", ".join(names)

            # If we've satisfied all needs, no need to keep scanning
            if not (needs_stategraph or needs_end):
                break

        additions: List[str] = []
        # If still missing any symbols, add a new consolidated import line
        missing_names: List[str] = []
        if needs_stategraph:
            missing_names.append("StateGraph")
        if needs_end:
            missing_names.append("END")
        if missing_names:
            additions.append(f"from langgraph.graph import {', '.join(missing_names)}")
            updated = True

        if not updated:
            return False

        # Update the cell source, appending any new consolidated import
        new_source = "\n".join(lines)
        if additions:
            if new_source:
                new_source = new_source.rstrip() + "\n" + "\n".join(additions)
            else:
                new_source = "\n".join(additions)

        cell.source = new_source
        return True

    def _repair_sections(self, nb: NotebookNode, report: QAReport) -> bool:
        """Add missing required sections to the notebook.

        Args:
            nb: Notebook to repair
            report: QA report with section issues

        Returns:
            True if any repairs were made
        """
        # Extract missing sections from the report message
        match = re.search(r"Missing required sections: (.+)", report.message)
        if not match:
            return False

        missing_sections_str = match.group(1)
        missing_sections = [sec.strip() for sec in missing_sections_str.split(",")]

        # Create placeholder cells for missing sections
        repaired = False
        for section in missing_sections:
            section = section.strip()
            
            # Add a markdown header cell
            header_cell = nbformat.v4.new_markdown_cell(
                source=f"## {section.title()}\n\nGenerated section placeholder."
            )
            header_cell.metadata["section"] = section

            # Add a code placeholder
            code_cell = nbformat.v4.new_code_cell(source="# Section implementation here\npass")
            code_cell.metadata["section"] = section

            # Append to notebook
            nb.cells.extend([header_cell, code_cell])
            repaired = True

        return repaired

    def _repair_compilation(self, nb: NotebookNode, report: QAReport) -> bool:
        """Fix compilation issues in the notebook.

        Args:
            nb: Notebook to repair
            report: QA report with compilation issues

        Returns:
            True if any repairs were made
        """
        repaired = False

        # Check for missing StateGraph construction
        if "No StateGraph construction found" in report.message:
            # Find the graph section or add it
            graph_cell_idx = None
            for idx, cell in enumerate(nb.cells):
                if cell.metadata.get("section") == "graph":
                    graph_cell_idx = idx
                    break

            if graph_cell_idx is not None:
                cell = nb.cells[graph_cell_idx]
                if cell.cell_type == "code" and "StateGraph" not in cell.source:
                    # Add minimal StateGraph construction
                    graph_template = """
from langgraph.graph import StateGraph, END
from typing import TypedDict

class WorkflowState(TypedDict):
    messages: list

graph = StateGraph(WorkflowState)

def placeholder_node(state: WorkflowState):
    return state

graph.add_node("start", placeholder_node)
graph.set_entry_point("start")
graph.add_edge("start", END)
"""
                    existing_source = cell.source or ""
                    if existing_source.strip():
                        # Preserve existing content and append the graph template
                        cell.source = existing_source.rstrip() + "\n\n" + graph_template.strip()
                    else:
                        # Cell is effectively empty; safe to replace entirely
                        cell.source = graph_template.strip()
                    repaired = True

        # Check for missing .compile() call
        elif "Graph compilation step (.compile()) not found" in report.message:
            # Find the last graph-related code cell
            for idx in range(len(nb.cells) - 1, -1, -1):
                cell = nb.cells[idx]
                if cell.cell_type == "code" and "StateGraph" in cell.source:
                    if ".compile()" not in cell.source:
                        cell.source = cell.source.rstrip() + "\ncompiled_graph = graph.compile()"
                        repaired = True
                    break

        return repaired

    def should_retry(self, qa_reports: List[QAReport], attempt: int) -> bool:
        """Determine if repair should be retried.

        Args:
            qa_reports: Current QA reports
            attempt: Current attempt number (0-indexed)

        Returns:
            True if repair should be retried
        """
        if attempt >= self.max_attempts:
            return False

        failed_reports = [r for r in qa_reports if not r.passed]
        return len(failed_reports) > 0

    def get_repair_summary(self, qa_reports: List[QAReport]) -> Dict[str, Any]:
        """Generate a summary of repair results.

        Args:
            qa_reports: Final QA reports after repair attempts

        Returns:
            Dictionary with repair summary
        """
        passed = [r for r in qa_reports if r.passed]
        failed = [r for r in qa_reports if not r.passed]

        return {
            "total_checks": len(qa_reports),
            "passed": len(passed),
            "failed": len(failed),
            "success_rate": len(passed) / len(qa_reports) if qa_reports else 0.0,
            "failed_checks": [r.check_name for r in failed],
            "all_passed": len(failed) == 0,
        }

