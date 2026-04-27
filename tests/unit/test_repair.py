"""Tests for the shared QA repair engine."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import nbformat
import pytest

from langgraph_system_generator.generator.state import CellSpec, QAReport
from langgraph_system_generator.notebook.composer import (
    NotebookComposer as NotebookFileComposer,
)
from langgraph_system_generator.qa.repair import NotebookRepairAgent
from langgraph_system_generator.qa.validators import NotebookValidator


@pytest.fixture
def tmp_notebook_path(tmp_path: Path) -> Path:
    """Create a temporary notebook path."""

    return tmp_path / "test_notebook.ipynb"


@pytest.fixture
def repair_agent() -> NotebookRepairAgent:
    """Create a repair agent for testing."""

    return NotebookRepairAgent(max_attempts=3)


def _validate_cells(cells: list[CellSpec]) -> list[QAReport]:
    """Validate cells using the shared notebook validator path."""

    builder = NotebookFileComposer()
    validator = NotebookValidator()
    with TemporaryDirectory() as temp_dir:
        notebook = builder.build_notebook(cells)
        notebook_path = Path(temp_dir) / "generated.ipynb"
        builder.write(notebook, notebook_path)
        return validator.validate_all(notebook_path)


def _valid_graph_cells(*, execution_content: str | None = None) -> list[CellSpec]:
    """Return a minimal valid notebook cell set for repair-focused tests."""

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


def _joined_code(cells: list[CellSpec]) -> str:
    """Return concatenated code cell content for easy assertions."""

    return "\n".join(cell.content for cell in cells if cell.cell_type == "code")


def _failed_report(reports: list[QAReport], rule_id: str) -> QAReport:
    """Return the first failing report for the requested rule."""

    return next(
        report
        for report in reports
        if report.rule_id == rule_id and not report.passed
    )


def test_repair_agent_initialization():
    """Test repair agent initialization."""

    agent = NotebookRepairAgent(max_attempts=5)
    assert agent.max_attempts == 5
    assert isinstance(agent.validator, NotebookValidator)


def test_repair_agent_default_max_attempts():
    """Test repair agent uses default max attempts."""

    agent = NotebookRepairAgent()
    assert agent.max_attempts == NotebookRepairAgent.DEFAULT_MAX_ATTEMPTS


def test_repair_cells_removes_placeholders_and_accepts_candidate(repair_agent):
    """Placeholder cleanup should remove marker content without dropping real code."""

    cells = _valid_graph_cells(
        execution_content="# TODO: implement\nvalue = 1\n# FIXME: remove placeholder"
    )
    reports = _validate_cells(cells)
    placeholder_report = _failed_report(reports, "placeholder_content")

    outcome = repair_agent.repair_cells(cells, [placeholder_report])

    assert outcome.success is True
    code = _joined_code(outcome.cells)
    assert "TODO" not in code
    assert "FIXME" not in code
    assert "value = 1" in code
    assert all(report.passed for report in outcome.qa_reports)


def test_repair_placeholders_preserves_identifiers_and_literals(repair_agent):
    """Placeholder cleanup should not mutate identifiers or literals that only contain marker text."""

    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(
                source=(
                    'method_TODO = 1\n'
                    'payload = {"TODO": "keep"}\n'
                    "value = method_TODO  # TODO: refine after smoke test\n"
                    "# FIXME: remove placeholder"
                )
            )
        ]
    )
    notebook.cells[0].metadata["section"] = "execution"

    fixes = repair_agent._repair_placeholders(notebook)

    repaired_source = str(notebook.cells[0].source)
    assert fixes
    assert "method_TODO = 1" in repaired_source
    assert 'payload = {"TODO": "keep"}' in repaired_source
    assert "# TODO" not in repaired_source
    assert "# FIXME" not in repaired_source


def test_repair_cells_adds_missing_langgraph_imports(repair_agent):
    """Import repair should restore missing LangGraph imports in the setup section."""

    cells = [
        CellSpec(
            cell_type="code",
            content="from typing import TypedDict",
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
            content="result = graph.invoke({})\nprint(result)",
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
    reports = _validate_cells(cells)
    import_report = _failed_report(reports, "required_import_symbols")

    outcome = repair_agent.repair_cells(cells, reports)

    assert outcome.success is True
    setup_cell = next(cell for cell in outcome.cells if cell.section == "setup")
    assert "from langgraph.graph import" in setup_cell.content
    assert "StateGraph" in setup_cell.content
    assert "START" in setup_cell.content
    assert all(report.passed for report in outcome.qa_reports)


def test_repair_cells_rebuilds_incomplete_graph_scaffold(repair_agent):
    """Graph repair should append a deterministic scaffold for incomplete graphs."""

    cells = [
        CellSpec(
            cell_type="code",
            content="from typing import TypedDict",
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
            content="# TODO: graph scaffold\nworkflow = None",
            metadata={"section": "graph"},
            section="graph",
        ),
        CellSpec(
            cell_type="code",
            content="print('ready')",
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
    reports = _validate_cells(cells)

    outcome = repair_agent.repair_cells(cells, reports)

    assert outcome.success is True
    code = _joined_code(outcome.cells)
    assert "Recovered deterministic graph scaffold" in code
    assert "graph = recovered_workflow.compile()" in code
    assert all(report.passed for report in outcome.qa_reports)


def test_repair_sections_inserts_setup_at_start(repair_agent):
    """Recovered setup sections should be inserted before dependent notebook cells."""

    notebook = NotebookFileComposer().build_notebook(
        [
            CellSpec(
                cell_type="markdown",
                content="## Graph",
                metadata={"section": "graph"},
                section="graph",
            ),
            CellSpec(
                cell_type="code",
                content="graph = None",
                metadata={"section": "graph"},
                section="graph",
            ),
        ]
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

    assert fixes == ["Added missing 'setup' section with deterministic fallback content."]
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
    assert len(setup_indexes) >= 2
    assert graph_indexes
    assert max(setup_indexes[:2]) < min(graph_indexes)


def test_repair_cells_fixes_undefined_name_typos(repair_agent):
    """Undefined-name repair should use validator suggestions for bounded typo fixes."""

    cells = _valid_graph_cells(execution_content="result = grpah.invoke({})\nprint(result)")
    reports = _validate_cells(cells)
    undefined_report = _failed_report(reports, "undefined_names")

    outcome = repair_agent.repair_cells(cells, [undefined_report])

    assert outcome.success is True
    code = _joined_code(outcome.cells)
    assert "grpah" not in code
    assert "graph.invoke({})" in code
    assert all(report.passed for report in outcome.qa_reports)


def test_repair_cells_fixes_undefined_name_typos_with_interleaved_markdown(repair_agent):
    """Undefined-name repair should map validator code-cell indexes back to notebook cells."""

    cells = _valid_graph_cells(execution_content="result = grpah.invoke({})\nprint(result)")
    cells.insert(
        3,
        CellSpec(
            cell_type="markdown",
            content="Execution follows below.",
            metadata={"section": "notes"},
            section="notes",
        ),
    )
    reports = _validate_cells(cells)
    undefined_report = _failed_report(reports, "undefined_names")

    outcome = repair_agent.repair_cells(cells, [undefined_report])

    assert outcome.success is True
    execution_cell = next(cell for cell in outcome.cells if cell.section == "execution")
    assert "grpah" not in execution_cell.content
    assert "graph.invoke({})" in execution_cell.content


@pytest.mark.parametrize(
    ("execution_content", "expected_fragment"),
    [
        ("if True\n    print(graph)", "if True:"),
        ("print(1 + 2", "print(1 + 2)"),
    ],
)
def test_repair_cells_applies_bounded_syntax_fixes(
    repair_agent,
    execution_content,
    expected_fragment,
):
    """Syntax repair should handle unambiguous missing-colon and delimiter cases."""

    cells = _valid_graph_cells(execution_content=execution_content)
    reports = _validate_cells(cells)
    syntax_report = _failed_report(reports, "python_syntax")

    outcome = repair_agent.repair_cells(cells, [syntax_report])

    assert outcome.success is True
    code = _joined_code(outcome.cells)
    assert expected_fragment in code
    assert all(report.passed for report in outcome.qa_reports)


def test_repair_cells_rolls_back_regressive_candidates(monkeypatch, repair_agent):
    """A regressive repair candidate should be rejected and rolled back."""

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
            suggestions=["Fix Python syntax errors before attempting execution."],
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
        lambda _notebook, _failed_reports: ["Applied synthetic deterministic fix."],
    )

    outcome = repair_agent.repair_cells(cells, baseline_reports)

    assert outcome.status == "rolled_back"
    assert outcome.rollback_used is True
    assert outcome.persisted is False
    assert outcome.cells == cells
    assert outcome.qa_reports == baseline_reports
    assert outcome.validation_summary["accepted"] is False


def test_repair_cells_skips_unhandled_failures_without_claiming_success(repair_agent):
    """Unhandled failures should be surfaced as skipped, not as successful repairs."""

    cells = _valid_graph_cells()
    runtime_report = QAReport(
        check_name="Runtime Check",
        passed=False,
        message="Runtime validation unavailable in this environment.",
        rule_id="runtime_check",
        severity="error",
        category="runtime",
        repairable=False,
        suggestions=["Install a healthy notebook execution environment before retrying."],
        stage="runtime",
    )

    outcome = repair_agent.repair_cells(cells, [runtime_report])

    assert outcome.status == "skipped"
    assert outcome.success is False
    assert outcome.rollback_used is False
    assert outcome.attempted_fixes == []
    assert "No safe deterministic repair matched" in outcome.message
    assert outcome.next_steps
    assert any(report.check_name == "Runtime Check" for report in outcome.qa_reports)
    assert any(report.stage == "runtime" for report in outcome.qa_reports if not report.passed)


def test_cells_from_notebook_preserves_list_source_line_boundaries(repair_agent):
    """List-backed notebook sources should round-trip with intact line boundaries."""

    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(source=["value = 1", "print(value)"]),
            nbformat.v4.new_markdown_cell(source=["## Summary", "Line two"]),
        ]
    )
    notebook.cells[0].metadata["section"] = "execution"
    notebook.cells[1].metadata["section"] = "summary"

    regenerated = repair_agent._cells_from_notebook(notebook)

    assert regenerated[0].content == "value = 1\nprint(value)"
    assert regenerated[1].content == "## Summary\nLine two"


def test_repair_notebook_persists_accepted_repairs(tmp_notebook_path: Path, repair_agent):
    """The legacy path adapter should write accepted in-memory repairs back to disk."""

    builder = NotebookFileComposer()
    cells = _valid_graph_cells(execution_content="result = grpah.invoke({})\nprint(result)")
    notebook = builder.build_notebook(cells)
    builder.write(notebook, tmp_notebook_path)
    reports = repair_agent.validator.validate_all(tmp_notebook_path)

    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, reports)

    assert success is True
    assert all(report.passed for report in new_reports)
    with tmp_notebook_path.open("r", encoding="utf-8") as handle:
        repaired_notebook = nbformat.read(handle, as_version=4)
    code = "\n".join(cell.source for cell in repaired_notebook.cells if cell.cell_type == "code")
    assert "grpah" not in code
    assert "graph.invoke({})" in code


def test_repair_notebook_all_passing(tmp_notebook_path: Path, repair_agent):
    """Repair should return success immediately when the caller reports no failures."""

    builder = NotebookFileComposer()
    notebook = builder.build_notebook(_valid_graph_cells())
    builder.write(notebook, tmp_notebook_path)
    qa_reports = [
        QAReport(
            check_name="Test Check",
            passed=True,
            message="All good",
            suggestions=[],
        )
    ]

    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, qa_reports)

    assert success is True
    assert new_reports == qa_reports


def test_repair_notebook_max_attempts(tmp_notebook_path: Path):
    """Test repair respects max attempts."""

    agent = NotebookRepairAgent(max_attempts=2)
    builder = NotebookFileComposer()
    notebook = builder.build_notebook(_valid_graph_cells(execution_content="result = grpah.invoke({})"))
    builder.write(notebook, tmp_notebook_path)
    reports = agent.validator.validate_all(tmp_notebook_path)

    success, _ = agent.repair_notebook(tmp_notebook_path, reports, attempt=2)
    assert not success


def test_repair_notebook_invalid_path(repair_agent):
    """Test repair with invalid notebook path."""

    qa_reports = [
        QAReport(
            check_name="Test",
            passed=False,
            message="Error",
            suggestions=[],
        )
    ]

    success, new_reports = repair_agent.repair_notebook(
        "/nonexistent/notebook.ipynb",
        qa_reports,
    )

    assert not success
    assert new_reports == qa_reports


def test_should_retry_within_limits(repair_agent):
    """Test should_retry returns True when within limits."""

    qa_reports = [
        QAReport(
            check_name="Test",
            passed=False,
            message="Error",
            suggestions=[],
        )
    ]

    assert repair_agent.should_retry(qa_reports, 0)
    assert repair_agent.should_retry(qa_reports, 1)
    assert repair_agent.should_retry(qa_reports, 2)


def test_should_retry_at_max(repair_agent):
    """Test should_retry returns False at max attempts."""

    qa_reports = [
        QAReport(
            check_name="Test",
            passed=False,
            message="Error",
            suggestions=[],
        )
    ]

    assert not repair_agent.should_retry(qa_reports, 3)
    assert not repair_agent.should_retry(qa_reports, 4)


def test_should_retry_all_passing(repair_agent):
    """Test should_retry returns False when all checks pass."""

    qa_reports = [
        QAReport(
            check_name="Test",
            passed=True,
            message="All good",
            suggestions=[],
        )
    ]

    assert not repair_agent.should_retry(qa_reports, 0)


def test_get_repair_summary_all_passed(repair_agent):
    """Test repair summary with all checks passing."""

    qa_reports = [
        QAReport(check_name="Check1", passed=True, message="OK", suggestions=[]),
        QAReport(check_name="Check2", passed=True, message="OK", suggestions=[]),
    ]

    summary = repair_agent.get_repair_summary(qa_reports)

    assert summary["total_checks"] == 2
    assert summary["passed"] == 2
    assert summary["failed"] == 0
    assert summary["success_rate"] == 1.0
    assert summary["failed_checks"] == []
    assert summary["all_passed"] is True


def test_get_repair_summary_mixed_results(repair_agent):
    """Test repair summary with mixed results."""

    qa_reports = [
        QAReport(check_name="Check1", passed=True, message="OK", suggestions=[]),
        QAReport(check_name="Check2", passed=False, message="Error", suggestions=[]),
        QAReport(check_name="Check3", passed=False, message="Error", suggestions=[]),
    ]

    summary = repair_agent.get_repair_summary(qa_reports)

    assert summary["total_checks"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 2
    assert summary["success_rate"] == pytest.approx(0.333, rel=0.01)
    assert summary["failed_checks"] == ["Check2", "Check3"]
    assert summary["all_passed"] is False
