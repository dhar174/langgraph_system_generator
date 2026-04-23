"""Regression suite for deterministic QA repair behavior."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from langgraph_system_generator.generator.state import CellSpec, QAReport
from langgraph_system_generator.notebook.composer import (
    NotebookComposer as NotebookFileComposer,
)
from langgraph_system_generator.qa.repair import NotebookRepairAgent
from langgraph_system_generator.qa.validators import NotebookValidator


def _valid_graph_cells(*, execution_content: str | None = None) -> list[CellSpec]:
    """Return a minimal valid notebook cell set for repair regression tests."""

    return [
        CellSpec(
            cell_type="code",
            content="from langgraph.graph import END, START, StateGraph\nfrom typing import TypedDict",
            metadata={"section": "setup"},
            section="setup",
        ),
        CellSpec(
            cell_type="code",
            content='config = {"configurable": {"thread_id": "demo"}}',
            metadata={"section": "config"},
            section="config",
        ),
        CellSpec(
            cell_type="code",
            content=(
                "class WorkflowState(TypedDict, total=False):\n"
                "    messages: list\n\n"
                "workflow = StateGraph(WorkflowState)\n\n"
                "def start_node(state: WorkflowState):\n"
                "    return state\n\n"
                "workflow.add_node('start', start_node)\n"
                "workflow.add_edge(START, 'start')\n"
                "workflow.add_edge('start', END)\n"
                "graph = workflow.compile()"
            ),
            metadata={"section": "graph"},
            section="graph",
        ),
        CellSpec(
            cell_type="code",
            content=execution_content or "result = graph.invoke({})\nprint(result)",
            metadata={"section": "execution"},
            section="execution",
        ),
        CellSpec(
            cell_type="code",
            content='output_data = {"result": "ok"}\noutput_data',
            metadata={"section": "export"},
            section="export",
        ),
        CellSpec(
            cell_type="markdown",
            content="Troubleshooting notes.",
            metadata={"section": "troubleshooting"},
            section="troubleshooting",
        ),
    ]


def _validate_cells(cells: list[CellSpec]) -> list[QAReport]:
    """Validate cells using the same file-backed path as generator nodes."""

    builder = NotebookFileComposer()
    validator = NotebookValidator()
    with TemporaryDirectory() as temp_dir:
        notebook = builder.build_notebook(cells)
        notebook_path = Path(temp_dir) / "generated.ipynb"
        builder.write(notebook, notebook_path)
        return validator.validate_all(notebook_path)


def _joined_code(cells: list[CellSpec]) -> str:
    """Return all code cell content joined for assertions."""

    return "\n".join(cell.content for cell in cells if cell.cell_type == "code")


def _failed_report(reports: list[QAReport], rule_id: str) -> QAReport:
    """Return the first failed report for a rule."""

    return next(
        report
        for report in reports
        if report.rule_id == rule_id and not report.passed
    )


@pytest.fixture
def repair_agent() -> NotebookRepairAgent:
    """Create a repair agent for regression tests."""

    return NotebookRepairAgent()


def test_regression_placeholder_cleanup_removes_visible_scaffold(repair_agent):
    cells = _valid_graph_cells(execution_content="# TODO: fill in\nvalue = 1\nvalue")
    reports = _validate_cells(cells)

    outcome = repair_agent.repair_cells(cells, reports)

    assert outcome.success is True
    assert "TODO" not in _joined_code(outcome.cells)
    assert "value = 1" in _joined_code(outcome.cells)


def test_regression_missing_langgraph_imports_are_consolidated(repair_agent):
    cells = _valid_graph_cells()
    cells[0] = CellSpec(
        cell_type="code",
        content="from typing import TypedDict",
        metadata={"section": "setup"},
        section="setup",
    )
    reports = _validate_cells(cells)

    outcome = repair_agent.repair_cells(cells, reports)

    assert outcome.success is True
    setup = next(cell for cell in outcome.cells if cell.section == "setup")
    assert "from langgraph.graph import" in setup.content
    assert "END" in setup.content
    assert "START" in setup.content
    assert "StateGraph" in setup.content


def test_regression_missing_setup_section_is_inserted_before_graph(repair_agent):
    cells = _valid_graph_cells()[1:]
    cells[1] = CellSpec(
        cell_type="code",
        content=(
            "from langgraph.graph import END, START, StateGraph\n"
            "from typing import TypedDict\n\n"
            f"{cells[1].content}"
        ),
        metadata={"section": "graph"},
        section="graph",
    )
    notebook = NotebookFileComposer().build_notebook(
        cells,
        ensure_minimum_sections=False,
    )
    report = QAReport(
        check_name="Required Sections",
        passed=False,
        message="Missing required sections: setup",
        rule_id="required_sections",
        severity="error",
        category="structure",
        repairable=True,
        evidence={"missing_sections": ["setup"]},
    )

    fixes = repair_agent._repair_sections(notebook, report)
    setup_indexes = [
        index
        for index, cell in enumerate(notebook.cells)
        if cell.metadata.get("section") == "setup"
    ]
    graph_indexes = [
        index
        for index, cell in enumerate(notebook.cells)
        if cell.metadata.get("section") == "graph"
    ]
    assert fixes == ["Added missing 'setup' section with deterministic fallback content."]
    assert setup_indexes
    assert graph_indexes
    assert max(setup_indexes[:2]) < min(graph_indexes)


def test_regression_incomplete_graph_scaffold_is_recovered(repair_agent):
    cells = _valid_graph_cells()
    cells[2] = CellSpec(
        cell_type="code",
        content="workflow = None",
        metadata={"section": "graph"},
        section="graph",
    )
    reports = _validate_cells(cells)

    outcome = repair_agent.repair_cells(cells, reports)

    assert outcome.success is True
    assert "Recovered deterministic graph scaffold" in _joined_code(outcome.cells)
    assert "graph = recovered_workflow.compile()" in _joined_code(outcome.cells)


def test_regression_undefined_name_typo_uses_validator_suggestion(repair_agent):
    cells = _valid_graph_cells(execution_content="result = grpah.invoke({})\nprint(result)")
    reports = _validate_cells(cells)

    outcome = repair_agent.repair_cells(cells, [_failed_report(reports, "undefined_names")])

    assert outcome.success is True
    assert "grpah" not in _joined_code(outcome.cells)
    assert "graph.invoke({})" in _joined_code(outcome.cells)


def test_regression_interleaved_markdown_does_not_break_typo_repair(repair_agent):
    cells = _valid_graph_cells(execution_content="result = grpah.invoke({})\nprint(result)")
    cells.insert(
        3,
        CellSpec(
            cell_type="markdown",
            content="Execution notes live between code cells.",
            metadata={"section": "notes"},
            section="notes",
        ),
    )
    reports = _validate_cells(cells)

    outcome = repair_agent.repair_cells(cells, [_failed_report(reports, "undefined_names")])

    assert outcome.success is True
    execution = next(cell for cell in outcome.cells if cell.section == "execution")
    assert "grpah" not in execution.content
    assert "graph.invoke({})" in execution.content


def test_regression_missing_colon_syntax_repair_is_bounded(repair_agent):
    cells = _valid_graph_cells(execution_content="if True\n    print(graph)")
    reports = _validate_cells(cells)

    outcome = repair_agent.repair_cells(cells, [_failed_report(reports, "python_syntax")])

    assert outcome.success is True
    assert "if True:" in _joined_code(outcome.cells)


def test_regression_unclosed_delimiter_syntax_repair_is_bounded(repair_agent):
    cells = _valid_graph_cells(execution_content="print(1 + 2")
    reports = _validate_cells(cells)

    outcome = repair_agent.repair_cells(cells, [_failed_report(reports, "python_syntax")])

    assert outcome.success is True
    assert "print(1 + 2)" in _joined_code(outcome.cells)


def test_regression_regressive_candidate_rolls_back(monkeypatch, repair_agent):
    cells = _valid_graph_cells(execution_content="result = grpah.invoke({})\nprint(result)")
    baseline_reports = _validate_cells(cells)
    regressive_reports = [
        QAReport(
            check_name="Python Syntax",
            passed=False,
            message="Syntax error in notebook code: invalid syntax at line 4",
            rule_id="python_syntax",
            severity="error",
            category="syntax",
            repairable=True,
        )
    ]
    validate_calls = {"count": 0}

    def fake_validate(_cells):
        validate_calls["count"] += 1
        return baseline_reports if validate_calls["count"] == 1 else regressive_reports

    monkeypatch.setattr(repair_agent, "_validate_cells", fake_validate)
    monkeypatch.setattr(
        repair_agent,
        "_apply_repairs",
        lambda _notebook, _failed_reports: ["Applied synthetic repair."],
    )

    outcome = repair_agent.repair_cells(cells, baseline_reports)

    assert outcome.status == "rolled_back"
    assert outcome.rollback_used is True
    assert outcome.cells == cells


def test_regression_unhandled_runtime_failure_remains_visible(repair_agent):
    cells = _valid_graph_cells()
    runtime_report = QAReport(
        check_name="Runtime Check",
        passed=False,
        message="Runtime validation failed: external dependency unavailable.",
        rule_id="runtime_smoke_test",
        severity="error",
        category="runtime",
        repairable=False,
        stage="runtime",
    )

    outcome = repair_agent.repair_cells(cells, [runtime_report])

    assert outcome.status == "skipped"
    assert outcome.success is False
    assert any(report.rule_id == "runtime_smoke_test" for report in outcome.qa_reports)
    assert "No safe deterministic repair matched" in outcome.message
