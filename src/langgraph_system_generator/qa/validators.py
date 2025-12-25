"""Notebook validation system for QA checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

import nbformat
from nbformat import NotebookNode

from langgraph_system_generator.generator.state import QAReport


class NotebookValidator:
    """Validates generated notebooks for quality and correctness."""

    PLACEHOLDER_PATTERNS = [
        "TODO",
        "FIXME",
        "PLACEHOLDER",
        "...",  # ellipsis as placeholder
        "# Your code here",
        "pass  # implement",
    ]

    REQUIRED_SECTIONS = [
        "setup",
        "config",
        "graph",
        "execution",
    ]

    REQUIRED_IMPORTS = [
        "langgraph",
        "StateGraph",
        "END",
    ]

    def validate_json_structure(self, notebook_path: str | Path) -> QAReport:
        """Check that notebook JSON is valid and can be loaded.

        Args:
            notebook_path: Path to the notebook file

        Returns:
            QAReport with validation results
        """
        try:
            path = Path(notebook_path)
            if not path.exists():
                return QAReport(
                    check_name="JSON Validity",
                    passed=False,
                    message=f"Notebook file not found: {notebook_path}",
                    suggestions=["Ensure the notebook was generated and saved correctly"],
                )

            with path.open("r", encoding="utf-8") as f:
                nb = nbformat.read(f, as_version=4)

            # Validate the notebook structure
            nbformat.validate(nb)

            return QAReport(
                check_name="JSON Validity",
                passed=True,
                message="Notebook JSON is valid and properly structured",
            )
        except json.JSONDecodeError as e:
            return QAReport(
                check_name="JSON Validity",
                passed=False,
                message=f"Invalid JSON: {str(e)}",
                suggestions=[
                    "Check for syntax errors in the notebook JSON",
                    "Ensure the file is properly encoded as UTF-8",
                ],
            )
        except nbformat.ValidationError as e:
            return QAReport(
                check_name="JSON Validity",
                passed=False,
                message=f"Invalid notebook structure: {str(e)}",
                suggestions=[
                    "Verify all required notebook fields are present",
                    "Check cell structure and metadata",
                ],
            )
        except Exception as e:
            return QAReport(
                check_name="JSON Validity",
                passed=False,
                message=f"Error reading notebook: {str(e)}",
                suggestions=["Check file permissions and path"],
            )

    def check_no_placeholders(self, notebook_path: str | Path) -> QAReport:
        """Ensure no placeholder text remains in the notebook.

        Args:
            notebook_path: Path to the notebook file

        Returns:
            QAReport with validation results
        """
        try:
            path = Path(notebook_path)
            with path.open("r", encoding="utf-8") as f:
                content = f.read()

            found_placeholders = []
            for pattern in self.PLACEHOLDER_PATTERNS:
                if pattern in content:
                    # Count occurrences
                    count = content.count(pattern)
                    found_placeholders.append(f"{pattern} ({count}x)")

            if found_placeholders:
                return QAReport(
                    check_name="No Placeholders",
                    passed=False,
                    message=f"Found placeholders: {', '.join(found_placeholders)}",
                    suggestions=[
                        "Replace all TODO/FIXME markers with actual implementation",
                        "Remove ellipsis (...) placeholders",
                        "Complete all code sections marked for implementation",
                    ],
                )

            return QAReport(
                check_name="No Placeholders",
                passed=True,
                message="No placeholders found in notebook",
            )
        except Exception as e:
            return QAReport(
                check_name="No Placeholders",
                passed=False,
                message=f"Error checking placeholders: {str(e)}",
                suggestions=["Verify notebook file is readable"],
            )

    def check_required_sections(
        self, notebook_path: str | Path, required_sections: Optional[List[str]] = None
    ) -> QAReport:
        """Verify that notebook has all required sections.

        Args:
            notebook_path: Path to the notebook file
            required_sections: Optional list of required section names.
                              Uses default if not provided.

        Returns:
            QAReport with validation results
        """
        try:
            path = Path(notebook_path)
            with path.open("r", encoding="utf-8") as f:
                nb = nbformat.read(f, as_version=4)

            sections_to_check = required_sections or self.REQUIRED_SECTIONS
            present_sections = set()

            for cell in nb.cells:
                section = cell.metadata.get("section")
                if section:
                    present_sections.add(section)

            missing_sections = set(sections_to_check) - present_sections

            if missing_sections:
                return QAReport(
                    check_name="Required Sections",
                    passed=False,
                    message=f"Missing required sections: {', '.join(sorted(missing_sections))}",
                    suggestions=[
                        f"Add cells with section metadata for: {', '.join(sorted(missing_sections))}",
                        "Ensure minimum required sections are present",
                    ],
                )

            return QAReport(
                check_name="Required Sections",
                passed=True,
                message=f"All required sections present: {', '.join(sorted(present_sections))}",
            )
        except Exception as e:
            return QAReport(
                check_name="Required Sections",
                passed=False,
                message=f"Error checking sections: {str(e)}",
                suggestions=["Verify notebook structure and metadata"],
            )

    def check_imports_present(
        self, notebook_path: str | Path, required_imports: Optional[List[str]] = None
    ) -> QAReport:
        """Ensure necessary imports are present in the notebook.

        Args:
            notebook_path: Path to the notebook file
            required_imports: Optional list of required import names.
                            Uses default if not provided.

        Returns:
            QAReport with validation results
        """
        try:
            path = Path(notebook_path)
            with path.open("r", encoding="utf-8") as f:
                nb = nbformat.read(f, as_version=4)

            imports_to_check = required_imports or self.REQUIRED_IMPORTS
            
            # Collect all code content
            code_content = ""
            for cell in nb.cells:
                if cell.cell_type == "code":
                    code_content += cell.source + "\n"

            missing_imports = []
            for imp in imports_to_check:
                if imp not in code_content:
                    missing_imports.append(imp)

            if missing_imports:
                return QAReport(
                    check_name="Required Imports",
                    passed=False,
                    message=f"Missing required imports: {', '.join(missing_imports)}",
                    suggestions=[
                        f"Add import statements for: {', '.join(missing_imports)}",
                        "Ensure all LangGraph dependencies are imported",
                        "Check setup/installation cells for missing imports",
                    ],
                )

            return QAReport(
                check_name="Required Imports",
                passed=True,
                message="All required imports are present",
            )
        except Exception as e:
            return QAReport(
                check_name="Required Imports",
                passed=False,
                message=f"Error checking imports: {str(e)}",
                suggestions=["Verify notebook can be read and parsed"],
            )

    def check_graph_compiles(self, notebook_path: str | Path) -> QAReport:
        """Check if the graph construction code compiles (syntax check).

        Note: This performs static syntax validation, not full execution.
        For full execution testing, use runtime validation tools.

        Args:
            notebook_path: Path to the notebook file

        Returns:
            QAReport with validation results
        """
        try:
            path = Path(notebook_path)
            with path.open("r", encoding="utf-8") as f:
                nb = nbformat.read(f, as_version=4)

            # Extract code cells
            code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]
            
            if not code_cells:
                return QAReport(
                    check_name="Graph Compilation",
                    passed=False,
                    message="No code cells found in notebook",
                    suggestions=["Add code cells to implement the graph"],
                )

            # Collect all code and try to compile it
            all_code = "\n\n".join(cell.source for cell in code_cells)
            
            try:
                compile(all_code, "<notebook>", "exec")
            except SyntaxError as e:
                return QAReport(
                    check_name="Graph Compilation",
                    passed=False,
                    message=f"Syntax error in notebook code: {e.msg} at line {e.lineno}",
                    suggestions=[
                        "Fix syntax errors in the code cells",
                        "Check for missing colons, parentheses, or indentation issues",
                        "Validate Python syntax before generating notebook",
                    ],
                )

            # Check for basic graph construction patterns
            if "StateGraph" not in all_code:
                return QAReport(
                    check_name="Graph Compilation",
                    passed=False,
                    message="No StateGraph construction found in notebook",
                    suggestions=[
                        "Add StateGraph construction code",
                        "Ensure LangGraph is properly used",
                    ],
                )

            if ".compile()" not in all_code:
                return QAReport(
                    check_name="Graph Compilation",
                    passed=False,
                    message="Graph compilation step (.compile()) not found",
                    suggestions=[
                        "Add graph.compile() call to compile the workflow",
                        "Ensure the graph is compiled before execution",
                    ],
                )

            return QAReport(
                check_name="Graph Compilation",
                passed=True,
                message="Notebook code compiles and contains proper graph construction",
            )
        except Exception as e:
            return QAReport(
                check_name="Graph Compilation",
                passed=False,
                message=f"Error checking graph compilation: {str(e)}",
                suggestions=["Verify notebook structure and code cells"],
            )

    def validate_all(self, notebook_path: str | Path) -> List[QAReport]:
        """Run all validation checks on a notebook.

        Args:
            notebook_path: Path to the notebook file

        Returns:
            List of QAReport objects, one for each validation check
        """
        reports = []
        
        # JSON structure is prerequisite for other checks
        json_report = self.validate_json_structure(notebook_path)
        reports.append(json_report)
        
        if not json_report.passed:
            # If JSON is invalid, skip other checks
            return reports

        # Run remaining checks
        reports.append(self.check_no_placeholders(notebook_path))
        reports.append(self.check_required_sections(notebook_path))
        reports.append(self.check_imports_present(notebook_path))
        reports.append(self.check_graph_compiles(notebook_path))
        
        return reports

