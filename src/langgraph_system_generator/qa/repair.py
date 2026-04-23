"""Notebook repair system with bounded retry logic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Sequence

import nbformat
from nbformat import NotebookNode

from langgraph_system_generator.generator.state import CellSpec, QAReport
from langgraph_system_generator.notebook.composer import (
    NotebookComposer as NotebookFileComposer,
)
from langgraph_system_generator.qa.validators import NotebookValidator

_GRAPH_SCAFFOLD_MARKER = "# Recovered deterministic graph scaffold"
_GRAPH_SCAFFOLD_TEMPLATE = f"""{_GRAPH_SCAFFOLD_MARKER}
from langgraph.graph import END, START, StateGraph
from typing import TypedDict


class RecoveredWorkflowState(TypedDict, total=False):
    messages: list


recovered_workflow = StateGraph(RecoveredWorkflowState)


def recovered_start(state: RecoveredWorkflowState):
    return state


recovered_workflow.add_node("recovered_start", recovered_start)
recovered_workflow.add_edge(START, "recovered_start")
recovered_workflow.add_edge("recovered_start", END)
graph = recovered_workflow.compile()
"""
_PLACEHOLDER_REPLACEMENTS = {
    "TODO": "",
    "FIXME": "",
    "PLACEHOLDER": "",
    "# Your code here": "pass",
    "pass  # implement": "pass",
}
_LANGGRAPH_IMPORT_ORDER = {
    "END": 0,
    "START": 1,
    "StateGraph": 2,
}


@dataclass
class RepairOutcome:
    """Structured result from a deterministic repair attempt."""

    status: str
    cells: List[CellSpec] = field(default_factory=list)
    qa_reports: List[QAReport] = field(default_factory=list)
    attempted_fixes: List[str] = field(default_factory=list)
    rollback_used: bool = False
    persisted: bool = False
    message: str = ""
    next_steps: List[str] = field(default_factory=list)
    validation_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Whether repaired cells were accepted and persisted in memory."""

        return self.status == "applied" and self.persisted


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
        self.notebook_builder = NotebookFileComposer()

    def repair_cells(
        self,
        cells: Sequence[CellSpec],
        qa_reports: List[QAReport],
        attempt: int = 0,
    ) -> RepairOutcome:
        """Repair generated cells in memory and validate before accepting them."""

        original_cells = self._clone_cells(cells)
        failed_reports = [report for report in qa_reports if not report.passed]
        baseline_summary = self._validation_summary(qa_reports, qa_reports, accepted=True)

        if attempt >= self.max_attempts:
            return RepairOutcome(
                status="skipped",
                cells=original_cells,
                qa_reports=list(qa_reports),
                message="Repair attempt limit reached before another repair could run.",
                next_steps=[
                    "Inspect the latest QA reports and resolve the remaining issues manually."
                ],
                validation_summary=baseline_summary,
            )

        if not failed_reports:
            return RepairOutcome(
                status="not_needed",
                cells=original_cells,
                qa_reports=list(qa_reports),
                persisted=True,
                message="No repair was needed because all QA checks already passed.",
                validation_summary=baseline_summary,
            )

        try:
            baseline_reports = self._validate_cells(original_cells)
        except Exception:  # pragma: no cover - defensive fallback
            baseline_reports = list(qa_reports)
        baseline_summary = self._validation_summary(
            baseline_reports,
            baseline_reports,
            accepted=True,
        )

        notebook = self.notebook_builder.build_notebook(original_cells)
        candidate_notebook = nbformat.from_dict(notebook)
        attempted_fixes = self._apply_repairs(candidate_notebook, failed_reports)

        if not attempted_fixes:
            return RepairOutcome(
                status="skipped",
                cells=original_cells,
                qa_reports=baseline_reports,
                attempted_fixes=[],
                message="No safe deterministic repair matched the current QA failures.",
                next_steps=[
                    "Inspect the latest QA reports and resolve the remaining issues manually."
                ],
                validation_summary=baseline_summary,
            )

        try:
            candidate_cells = self._cells_from_notebook(candidate_notebook)
            candidate_reports = self._validate_cells(candidate_cells)
        except Exception as exc:  # pragma: no cover - defensive fallback
            validation_summary = self._validation_summary(
                baseline_reports,
                baseline_reports,
                accepted=False,
                error=str(exc),
            )
            return RepairOutcome(
                status="rolled_back",
                cells=original_cells,
                qa_reports=baseline_reports,
                attempted_fixes=attempted_fixes,
                rollback_used=True,
                message="Repair candidate could not be validated safely and was rolled back.",
                next_steps=[
                    "Inspect the generated notebook around the reported QA failures before retrying."
                ],
                validation_summary=validation_summary,
            )

        accepted = self._is_non_regressive(baseline_reports, candidate_reports)
        validation_summary = self._validation_summary(
            baseline_reports,
            candidate_reports,
            accepted=accepted,
        )
        if accepted:
            return RepairOutcome(
                status="applied",
                cells=candidate_cells,
                qa_reports=candidate_reports,
                attempted_fixes=attempted_fixes,
                persisted=True,
                message="Repair candidate passed validation and was accepted.",
                validation_summary=validation_summary,
            )

        return RepairOutcome(
            status="rolled_back",
            cells=original_cells,
            qa_reports=baseline_reports,
            attempted_fixes=attempted_fixes,
            rollback_used=True,
            message="Repair candidate was rolled back because it regressed or did not improve validation.",
            next_steps=[
                "Inspect the QA and Repair Summary cell for the attempted deterministic fixes.",
                "Resolve the remaining blocking QA failures manually before retrying."
            ],
            validation_summary=validation_summary,
        )

    def repair_notebook(
        self,
        notebook_path: str | Path,
        qa_reports: List[QAReport],
        attempt: int = 0,
    ) -> tuple[bool, List[QAReport]]:
        """Attempt to repair a notebook file while preserving legacy behavior."""

        path = Path(notebook_path)
        try:
            with path.open("r", encoding="utf-8") as handle:
                notebook = nbformat.read(handle, as_version=4)
        except Exception:
            return False, qa_reports

        cells = self._cells_from_notebook(notebook)
        outcome = self.repair_cells(cells, qa_reports, attempt=attempt)
        if outcome.status == "not_needed":
            return True, outcome.qa_reports
        if not outcome.success:
            return False, outcome.qa_reports

        try:
            repaired_notebook = self.notebook_builder.build_notebook(outcome.cells)
            self.notebook_builder.write(repaired_notebook, path)
        except Exception:
            return False, qa_reports

        return True, outcome.qa_reports

    def _apply_repairs(
        self,
        notebook: NotebookNode,
        failed_reports: Sequence[QAReport],
    ) -> List[str]:
        """Apply deterministic repairs for the currently failing QA reports."""

        attempted_fixes: List[str] = []
        for report in failed_reports:
            if report.rule_id == "placeholder_content" or report.check_name == "No Placeholders":
                attempted_fixes.extend(self._repair_placeholders(notebook))
            elif report.rule_id == "required_sections" or report.check_name == "Required Sections":
                attempted_fixes.extend(self._repair_sections(notebook, report))
            elif report.rule_id == "required_import_symbols" or report.check_name == "Required Imports":
                attempted_fixes.extend(self._repair_imports(notebook, report))
            elif report.rule_id == "undefined_names":
                attempted_fixes.extend(self._repair_undefined_names(notebook, report))
            elif report.rule_id == "python_syntax":
                attempted_fixes.extend(self._repair_syntax(notebook, report))
            elif report.rule_id == "graph_structure" or report.check_name == "Graph Compilation":
                attempted_fixes.extend(self._repair_graph_scaffold(notebook, report))

        return list(dict.fromkeys(fix for fix in attempted_fixes if fix.strip()))

    def _repair_placeholders(self, notebook: NotebookNode) -> List[str]:
        """Remove deterministic placeholder content from notebook code cells."""

        fixes: List[str] = []
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type != "code":
                continue

            original = str(cell.source or "")
            modified = original
            for placeholder, replacement in _PLACEHOLDER_REPLACEMENTS.items():
                modified = modified.replace(placeholder, replacement)

            filtered_lines: List[str] = []
            for line in modified.splitlines():
                stripped = line.strip()
                if stripped in {"...", "# ..."}:
                    continue
                filtered_lines.append(line)
            modified = "\n".join(filtered_lines)

            while "\n\n\n" in modified:
                modified = modified.replace("\n\n\n", "\n\n")

            if modified != original:
                cell.source = modified or "pass"
                fixes.append(
                    f"Removed placeholder content from code cell {index}."
                )

        return fixes

    def _repair_imports(self, notebook: NotebookNode, report: QAReport) -> List[str]:
        """Add missing LangGraph imports to the setup/import area."""

        missing_symbols = [
            str(symbol).strip()
            for symbol in (report.evidence.get("missing_symbols") or [])
            if str(symbol).strip()
        ]
        if not missing_symbols:
            match = re.search(r"Missing required imports: (.+)", report.message)
            if match:
                missing_symbols = [
                    item.strip() for item in match.group(1).split(",") if item.strip()
                ]

        if not missing_symbols:
            return []

        names_to_add: set[str] = set()
        if "langgraph" in missing_symbols:
            names_to_add.update({"StateGraph", "END", "START"})
        if "StateGraph" in missing_symbols:
            names_to_add.add("StateGraph")
        if "END" in missing_symbols:
            names_to_add.add("END")
        if "START" in missing_symbols:
            names_to_add.add("START")

        if not names_to_add:
            return []

        cell = self._ensure_setup_code_cell(notebook)
        source = str(cell.source or "")
        updated_source = self._merge_langgraph_imports(source, names_to_add)
        if updated_source == source:
            return []

        cell.source = updated_source
        sorted_names = sorted(
            names_to_add,
            key=lambda item: (_LANGGRAPH_IMPORT_ORDER.get(item, 99), item),
        )
        return [
            "Added LangGraph imports to the setup section: "
            + ", ".join(sorted_names)
            + "."
        ]

    def _repair_sections(self, notebook: NotebookNode, report: QAReport) -> List[str]:
        """Add missing required notebook sections with deterministic defaults."""

        missing_sections = [
            str(section).strip()
            for section in (report.evidence.get("missing_sections") or [])
            if str(section).strip()
        ]
        if not missing_sections:
            match = re.search(r"Missing required sections: (.+)", report.message)
            if match:
                missing_sections = [
                    item.strip() for item in match.group(1).split(",") if item.strip()
                ]

        fixes: List[str] = []
        for section in missing_sections:
            if section == "graph":
                code_source = _GRAPH_SCAFFOLD_TEMPLATE
            elif section == "setup":
                code_source = (
                    "from pathlib import Path\n\nworkspace_dir = Path.cwd()\nworkspace_dir"
                )
            elif section == "config":
                code_source = 'MODEL = "gpt-5-mini"\nMAX_ITERATIONS = 10'
            elif section == "execution":
                code_source = 'result = graph.invoke({})\nprint(result)'
            else:
                code_source = (
                    f'section_status = "Recovered {section}"\nprint(section_status)'
                )

            header_cell = nbformat.v4.new_markdown_cell(
                source=f"## {section.title()}\n\nRecovered automatically during notebook repair."
            )
            header_cell.metadata["section"] = section
            code_cell = nbformat.v4.new_code_cell(source=code_source)
            code_cell.metadata["section"] = section
            notebook.cells.extend([header_cell, code_cell])
            fixes.append(f"Added missing '{section}' section with deterministic fallback content.")

        return fixes

    def _repair_undefined_names(
        self, notebook: NotebookNode, report: QAReport
    ) -> List[str]:
        """Apply close-match typo replacements for undefined notebook symbols."""

        fixes: List[str] = []
        issues = report.evidence.get("undefined_names") or []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            suggestion = issue.get("suggestion")
            name = issue.get("name")
            cell_index = issue.get("cell_index")
            if not isinstance(suggestion, str) or not isinstance(name, str):
                continue
            if not isinstance(cell_index, int) or not (0 <= cell_index < len(notebook.cells)):
                continue

            cell = notebook.cells[cell_index]
            if cell.cell_type != "code":
                continue

            pattern = re.compile(rf"\b{re.escape(name)}\b")
            updated_source, count = pattern.subn(suggestion, str(cell.source or ""))
            if count > 0:
                cell.source = updated_source
                fixes.append(
                    f"Replaced likely typo '{name}' with '{suggestion}' in code cell {cell_index}."
                )

        return fixes

    def _repair_syntax(self, notebook: NotebookNode, report: QAReport) -> List[str]:
        """Apply bounded deterministic syntax repairs based on validator evidence."""

        syntax_error = report.evidence.get("syntax_error") or {}
        if not isinstance(syntax_error, dict):
            return []

        cell_index = syntax_error.get("cell_index")
        line_in_cell = syntax_error.get("line_in_cell")
        message = str(syntax_error.get("message") or "")
        if not isinstance(cell_index, int) or not isinstance(line_in_cell, int):
            return []
        if not (0 <= cell_index < len(notebook.cells)):
            return []

        cell = notebook.cells[cell_index]
        if cell.cell_type != "code":
            return []

        lines = str(cell.source or "").splitlines()
        target_index = line_in_cell - 1
        if not (0 <= target_index < len(lines)):
            return []

        original_line = lines[target_index]
        updated_line = self._repair_missing_colon(original_line, message)
        if updated_line == original_line:
            updated_line = self._repair_unclosed_delimiter(original_line, message)

        if updated_line == original_line:
            return []

        lines[target_index] = updated_line
        cell.source = "\n".join(lines)
        return [
            f"Applied bounded syntax repair in code cell {cell_index} at line {line_in_cell}."
        ]

    def _repair_graph_scaffold(
        self, notebook: NotebookNode, report: QAReport
    ) -> List[str]:
        """Append a deterministic runnable graph scaffold when graph structure is incomplete."""

        graph_cell = self._ensure_graph_code_cell(notebook)
        source = str(graph_cell.source or "")
        if _GRAPH_SCAFFOLD_MARKER in source:
            return []

        graph_cell.source = (
            f"{source.rstrip()}\n\n{_GRAPH_SCAFFOLD_TEMPLATE}".strip()
            if source.strip()
            else _GRAPH_SCAFFOLD_TEMPLATE
        )
        return [
            "Appended a deterministic LangGraph scaffold to recover missing graph wiring."
        ]

    def _repair_missing_colon(self, line: str, message: str) -> str:
        """Append a trailing colon for obvious block starters when syntax evidence is clear."""

        stripped = line.rstrip()
        if stripped.endswith(":"):
            return line

        block_starter = re.match(
            r"^\s*(if|elif|else|for|while|try|except|finally|with|def|class)\b",
            stripped,
        )
        if not block_starter:
            return line

        if "expected ':'" in message or "invalid syntax" in message:
            return f"{stripped}:"

        return line

    def _repair_unclosed_delimiter(self, line: str, message: str) -> str:
        """Close a single obviously unclosed delimiter on the current source line."""

        match = re.search(r"'([\(\[\{])' was never closed", message)
        if not match:
            return line

        opener = match.group(1)
        closer = {"(": ")", "[": "]", "{": "}"}[opener]
        if line.count(opener) - line.count(closer) != 1:
            return line
        if line.rstrip().endswith(closer):
            return line
        return f"{line.rstrip()}{closer}"

    def _ensure_setup_code_cell(self, notebook: NotebookNode) -> NotebookNode:
        """Return the best setup/import code cell, creating one if necessary."""

        for cell in notebook.cells:
            if cell.cell_type == "code" and cell.metadata.get("section") == "setup":
                return cell
        for cell in notebook.cells:
            if cell.cell_type == "code":
                return cell

        cell = nbformat.v4.new_code_cell(source="")
        cell.metadata["section"] = "setup"
        notebook.cells.insert(0, cell)
        return cell

    def _ensure_graph_code_cell(self, notebook: NotebookNode) -> NotebookNode:
        """Return a graph-section code cell, creating one if necessary."""

        for cell in notebook.cells:
            if cell.cell_type == "code" and cell.metadata.get("section") == "graph":
                return cell

        graph_header = nbformat.v4.new_markdown_cell(
            source="## Graph\n\nRecovered automatically during notebook repair."
        )
        graph_header.metadata["section"] = "graph"
        graph_cell = nbformat.v4.new_code_cell(source="")
        graph_cell.metadata["section"] = "graph"
        notebook.cells.extend([graph_header, graph_cell])
        return graph_cell

    def _merge_langgraph_imports(self, source: str, names_to_add: set[str]) -> str:
        """Merge LangGraph imports into the setup code without duplicating lines."""

        lines = source.splitlines()
        import_line_index = None
        import_names: set[str] = set()
        for index, line in enumerate(lines):
            match = re.match(
                r"^(\s*from\s+langgraph\.graph\s+import\s+)(.+)$",
                line.strip(),
            )
            if not match:
                continue
            import_line_index = index
            names = [
                item.strip()
                for item in match.group(2).split(",")
                if item.strip()
            ]
            import_names.update(names)
            break

        import_names.update(names_to_add)
        ordered_names = sorted(
            import_names,
            key=lambda item: (_LANGGRAPH_IMPORT_ORDER.get(item, 99), item),
        )
        import_line = f"from langgraph.graph import {', '.join(ordered_names)}"

        if import_line_index is not None:
            lines[import_line_index] = import_line
            return "\n".join(lines).strip()

        insert_at = 0
        while insert_at < len(lines):
            stripped = lines[insert_at].strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("import ") or stripped.startswith("from "):
                insert_at += 1
                continue
            break

        updated_lines = [*lines[:insert_at], import_line, *lines[insert_at:]]
        return "\n".join(updated_lines).strip()

    def _validate_cells(self, cells: Sequence[CellSpec]) -> List[QAReport]:
        """Validate cells using the shared notebook validator."""

        with TemporaryDirectory() as temp_dir:
            notebook = self.notebook_builder.build_notebook(cells)
            notebook_path = Path(temp_dir) / "repaired.ipynb"
            self.notebook_builder.write(notebook, notebook_path)
            return self.validator.validate_all(notebook_path)

    def _clone_cells(self, cells: Sequence[CellSpec]) -> List[CellSpec]:
        """Clone cell specs so repair attempts do not mutate caller-owned state."""

        return [cell.model_copy(deep=True) for cell in cells]

    def _cells_from_notebook(self, notebook: NotebookNode) -> List[CellSpec]:
        """Convert an in-memory notebook into CellSpec entries."""

        regenerated_cells: List[CellSpec] = []
        for cell in notebook.cells:
            metadata = dict(cell.metadata or {})
            section = metadata.pop("section", None)
            source = cell.source if isinstance(cell.source, str) else "".join(cell.source or [])
            regenerated_cells.append(
                CellSpec(
                    cell_type=cell.cell_type,
                    content=source,
                    metadata=metadata,
                    section=section if isinstance(section, str) else None,
                )
            )
        return regenerated_cells

    def _report_key(self, report: QAReport) -> tuple[str, str, str, str]:
        """Return a stable key for comparing report severity across attempts."""

        return (
            report.rule_id,
            report.check_name,
            report.severity,
            report.message,
        )

    def _is_non_regressive(
        self,
        baseline_reports: Sequence[QAReport],
        candidate_reports: Sequence[QAReport],
    ) -> bool:
        """Accept candidates that improve or safely preserve validation severity."""

        baseline_failed = [report for report in baseline_reports if not report.passed]
        candidate_failed = [report for report in candidate_reports if not report.passed]
        if len(candidate_failed) < len(baseline_failed):
            return True

        if len(candidate_failed) != len(baseline_failed):
            return False

        baseline_errors = {
            self._report_key(report)
            for report in baseline_failed
            if report.severity == "error"
        }
        candidate_errors = {
            self._report_key(report)
            for report in candidate_failed
            if report.severity == "error"
        }
        return candidate_errors < baseline_errors

    def _validation_summary(
        self,
        baseline_reports: Sequence[QAReport],
        candidate_reports: Sequence[QAReport],
        *,
        accepted: bool,
        error: str | None = None,
    ) -> Dict[str, Any]:
        """Return a compact validation comparison for repair attempt evidence."""

        baseline_failed = [report for report in baseline_reports if not report.passed]
        candidate_failed = [report for report in candidate_reports if not report.passed]
        baseline_errors = [
            report.check_name for report in baseline_failed if report.severity == "error"
        ]
        candidate_errors = [
            report.check_name for report in candidate_failed if report.severity == "error"
        ]

        summary: Dict[str, Any] = {
            "baseline_failed_checks": len(baseline_failed),
            "candidate_failed_checks": len(candidate_failed),
            "baseline_error_checks": baseline_errors,
            "candidate_error_checks": candidate_errors,
            "accepted": accepted,
        }
        if error:
            summary["validation_error"] = error
        return summary

    def should_retry(self, qa_reports: List[QAReport], attempt: int) -> bool:
        """Determine if repair should be retried."""

        if attempt >= self.max_attempts:
            return False

        failed_reports = [report for report in qa_reports if not report.passed]
        return len(failed_reports) > 0

    def get_repair_summary(self, qa_reports: List[QAReport]) -> Dict[str, Any]:
        """Generate a summary of repair results."""

        passed = [report for report in qa_reports if report.passed]
        failed = [report for report in qa_reports if not report.passed]

        return {
            "total_checks": len(qa_reports),
            "passed": len(passed),
            "failed": len(failed),
            "success_rate": len(passed) / len(qa_reports) if qa_reports else 0.0,
            "failed_checks": [report.check_name for report in failed],
            "all_passed": len(failed) == 0,
        }
