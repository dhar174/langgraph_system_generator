"""Tests for QA repair agent."""

from __future__ import annotations

from pathlib import Path

import nbformat
import pytest
from nbformat.v4 import new_code_cell, new_notebook

from langgraph_system_generator.generator.state import QAReport
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


def test_repair_agent_initialization():
    """Test repair agent initialization."""
    agent = NotebookRepairAgent(max_attempts=5)
    assert agent.max_attempts == 5
    assert isinstance(agent.validator, NotebookValidator)


def test_repair_agent_default_max_attempts():
    """Test repair agent uses default max attempts."""
    agent = NotebookRepairAgent()
    assert agent.max_attempts == NotebookRepairAgent.DEFAULT_MAX_ATTEMPTS


def test_repair_placeholders(tmp_notebook_path: Path, repair_agent):
    """Test repairing placeholders in notebook."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="# TODO: implement\nx = 1\n# FIXME: broken"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    # Create a QA report indicating placeholder issue
    qa_reports = [
        QAReport(
            check_name="No Placeholders",
            passed=False,
            message="Found placeholders: TODO, FIXME",
            suggestions=["Remove placeholders"],
        )
    ]
    
    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, qa_reports)
    
    # Verify repair was attempted
    assert success or len(new_reports) > 0
    
    # Read the repaired notebook
    with tmp_notebook_path.open("r") as f:
        repaired_nb = nbformat.read(f, as_version=4)
    
    # Check that placeholders were removed
    content = repaired_nb.cells[0].source
    assert "TODO" not in content
    assert "FIXME" not in content
    assert "x = 1" in content  # Code should remain


def test_repair_placeholders_ellipsis(tmp_notebook_path: Path, repair_agent):
    """Test repairing ellipsis placeholders."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="def func():\n    ...\n    pass"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    qa_reports = [
        QAReport(
            check_name="No Placeholders",
            passed=False,
            message="Found placeholders: ... (1x)",
            suggestions=["Remove ellipsis"],
        )
    ]
    
    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, qa_reports)
    
    # Verify repair was attempted
    assert success or len(new_reports) > 0
    
    with tmp_notebook_path.open("r") as f:
        repaired_nb = nbformat.read(f, as_version=4)
    
    # Ellipsis line should be removed
    content = repaired_nb.cells[0].source
    assert content.count("...") == 0


def test_repair_imports(tmp_notebook_path: Path, repair_agent):
    """Test adding missing imports."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="x = 1"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    qa_reports = [
        QAReport(
            check_name="Required Imports",
            passed=False,
            message="Missing required imports: langgraph, StateGraph",
            suggestions=["Add imports"],
        )
    ]
    
    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, qa_reports)
    
    # Verify repair was attempted
    assert success or len(new_reports) > 0
    
    with tmp_notebook_path.open("r") as f:
        repaired_nb = nbformat.read(f, as_version=4)
    
    content = repaired_nb.cells[0].source
    assert "StateGraph" in content or "langgraph" in content


def test_repair_sections(tmp_notebook_path: Path, repair_agent):
    """Test adding missing sections."""
    nb = new_notebook()
    nb.cells.append(
        new_code_cell(source="x = 1", metadata={"section": "setup"})
    )
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    qa_reports = [
        QAReport(
            check_name="Required Sections",
            passed=False,
            message="Missing required sections: config, graph",
            suggestions=["Add missing sections"],
        )
    ]
    
    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, qa_reports)
    
    with tmp_notebook_path.open("r") as f:
        repaired_nb = nbformat.read(f, as_version=4)
    
    sections = {cell.metadata.get("section") for cell in repaired_nb.cells}
    assert "config" in sections
    assert "graph" in sections


def test_repair_compilation_missing_stategraph(tmp_notebook_path: Path, repair_agent):
    """Test repairing missing StateGraph construction."""
    nb = new_notebook()
    nb.cells.append(
        new_code_cell(source="x = 1", metadata={"section": "graph"})
    )
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    qa_reports = [
        QAReport(
            check_name="Graph Compilation",
            passed=False,
            message="No StateGraph construction found in notebook",
            suggestions=["Add StateGraph"],
        )
    ]
    
    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, qa_reports)
    
    with tmp_notebook_path.open("r") as f:
        repaired_nb = nbformat.read(f, as_version=4)
    
    # Find graph section
    graph_cell = None
    for cell in repaired_nb.cells:
        if cell.metadata.get("section") == "graph" and cell.cell_type == "code":
            graph_cell = cell
            break
    
    assert graph_cell is not None
    # Verify StateGraph was added and existing code was preserved
    assert "StateGraph" in graph_cell.source
    assert "x = 1" in graph_cell.source  # Original code should be preserved


def test_repair_compilation_missing_compile(tmp_notebook_path: Path, repair_agent):
    """Test repairing missing .compile() call."""
    nb = new_notebook()
    nb.cells.append(
        new_code_cell(
            source="from langgraph.graph import StateGraph\ngraph = StateGraph(dict)",
            metadata={"section": "graph"},
        )
    )
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    qa_reports = [
        QAReport(
            check_name="Graph Compilation",
            passed=False,
            message="Graph compilation step (.compile()) not found",
            suggestions=["Add .compile()"],
        )
    ]
    
    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, qa_reports)
    
    with tmp_notebook_path.open("r") as f:
        repaired_nb = nbformat.read(f, as_version=4)
    
    content = repaired_nb.cells[0].source
    assert ".compile()" in content


def test_repair_notebook_all_passing(tmp_notebook_path: Path, repair_agent):
    """Test repair when all checks pass (no repair needed)."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="x = 1"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    qa_reports = [
        QAReport(
            check_name="Test Check",
            passed=True,
            message="All good",
            suggestions=[],
        )
    ]
    
    success, new_reports = repair_agent.repair_notebook(tmp_notebook_path, qa_reports)
    
    # Should succeed immediately since no repairs needed
    assert success
    assert new_reports == qa_reports


def test_repair_notebook_max_attempts(tmp_notebook_path: Path):
    """Test repair respects max attempts."""
    agent = NotebookRepairAgent(max_attempts=2)
    
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="# TODO: implement"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    qa_reports = [
        QAReport(
            check_name="No Placeholders",
            passed=False,
            message="Found placeholders: TODO",
            suggestions=["Remove TODO"],
        )
    ]
    
    # Test with attempt at max
    success, _ = agent.repair_notebook(tmp_notebook_path, qa_reports, attempt=2)
    assert not success  # Should fail since at max attempts


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
        "/nonexistent/notebook.ipynb", qa_reports
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


def test_get_repair_summary_empty(repair_agent):
    """Test repair summary with no reports."""
    summary = repair_agent.get_repair_summary([])
    
    assert summary["total_checks"] == 0
    assert summary["passed"] == 0
    assert summary["failed"] == 0
    assert summary["success_rate"] == 0.0
    assert summary["all_passed"] is True  # Vacuously true


def test_integration_repair_cycle(tmp_notebook_path: Path, repair_agent):
    """Test complete repair cycle with validation."""
    # Create a notebook with multiple issues
    nb = new_notebook()
    nb.cells.append(
        new_code_cell(
            source="# TODO: implement\nx = 1",
            metadata={"section": "setup"},
        )
    )
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    # Run initial validation
    validator = NotebookValidator()
    initial_reports = validator.validate_all(tmp_notebook_path)
    
    # Some checks should fail
    failed = [r for r in initial_reports if not r.passed]
    assert len(failed) > 0
    
    # Attempt repair
    success, repaired_reports = repair_agent.repair_notebook(
        tmp_notebook_path, initial_reports
    )
    
    # Check that some issues were fixed
    repaired_failed = [r for r in repaired_reports if not r.passed]
    assert len(repaired_failed) < len(failed)
    
    # Get summary
    summary = repair_agent.get_repair_summary(repaired_reports)
    assert summary["total_checks"] > 0
    assert summary["passed"] > 0
