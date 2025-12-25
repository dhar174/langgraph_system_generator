"""Tests for QA validators."""

from __future__ import annotations

from pathlib import Path

import nbformat
import pytest
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from langgraph_system_generator.qa.validators import NotebookValidator


@pytest.fixture
def tmp_notebook_path(tmp_path: Path) -> Path:
    """Create a temporary notebook path."""
    return tmp_path / "test_notebook.ipynb"


@pytest.fixture
def valid_notebook() -> nbformat.NotebookNode:
    """Create a valid notebook for testing."""
    nb = new_notebook()
    
    # Add setup section
    nb.cells.append(
        new_markdown_cell(source="## Setup", metadata={"section": "setup"})
    )
    nb.cells.append(
        new_code_cell(
            source="from langgraph.graph import StateGraph, END\nimport langgraph",
            metadata={"section": "setup"},
        )
    )
    
    # Add config section
    nb.cells.append(
        new_markdown_cell(source="## Config", metadata={"section": "config"})
    )
    nb.cells.append(
        new_code_cell(source='MODEL = "gpt-4o-mini"', metadata={"section": "config"})
    )
    
    # Add graph section
    nb.cells.append(
        new_markdown_cell(source="## Graph", metadata={"section": "graph"})
    )
    nb.cells.append(
        new_code_cell(
            source="""from typing import TypedDict
class State(TypedDict):
    messages: list

graph = StateGraph(State)
graph.add_node("start", lambda x: x)
graph.set_entry_point("start")
graph.add_edge("start", END)
compiled_graph = graph.compile()""",
            metadata={"section": "graph"},
        )
    )
    
    # Add execution section
    nb.cells.append(
        new_markdown_cell(source="## Execution", metadata={"section": "execution"})
    )
    nb.cells.append(
        new_code_cell(
            source='result = compiled_graph.invoke({"messages": []})',
            metadata={"section": "execution"},
        )
    )
    
    return nb


def test_validate_json_structure_valid(tmp_notebook_path: Path, valid_notebook):
    """Test JSON validation with a valid notebook."""
    with tmp_notebook_path.open("w") as f:
        nbformat.write(valid_notebook, f)
    
    validator = NotebookValidator()
    report = validator.validate_json_structure(tmp_notebook_path)
    
    assert report.passed
    assert report.check_name == "JSON Validity"
    assert "valid" in report.message.lower()


def test_validate_json_structure_missing_file(tmp_path: Path):
    """Test JSON validation with missing file."""
    validator = NotebookValidator()
    report = validator.validate_json_structure(tmp_path / "nonexistent.ipynb")
    
    assert not report.passed
    assert report.check_name == "JSON Validity"
    assert "not found" in report.message.lower()


def test_validate_json_structure_invalid_json(tmp_notebook_path: Path):
    """Test JSON validation with invalid JSON."""
    with tmp_notebook_path.open("w") as f:
        f.write("{ invalid json }")
    
    validator = NotebookValidator()
    report = validator.validate_json_structure(tmp_notebook_path)
    
    assert not report.passed
    assert report.check_name == "JSON Validity"
    assert "json" in report.message.lower()


def test_check_no_placeholders_clean(tmp_notebook_path: Path, valid_notebook):
    """Test placeholder check with clean notebook."""
    with tmp_notebook_path.open("w") as f:
        nbformat.write(valid_notebook, f)
    
    validator = NotebookValidator()
    report = validator.check_no_placeholders(tmp_notebook_path)
    
    assert report.passed
    assert report.check_name == "No Placeholders"


def test_check_no_placeholders_with_todo(tmp_notebook_path: Path):
    """Test placeholder check with TODO."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="# TODO: implement this\npass"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_no_placeholders(tmp_notebook_path)
    
    assert not report.passed
    assert "TODO" in report.message
    assert len(report.suggestions) > 0


def test_check_no_placeholders_with_multiple(tmp_notebook_path: Path):
    """Test placeholder check with multiple placeholders."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="# TODO: fix this\n# FIXME: broken\npass"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_no_placeholders(tmp_notebook_path)
    
    assert not report.passed
    assert "TODO" in report.message
    assert "FIXME" in report.message


def test_check_required_sections_all_present(tmp_notebook_path: Path, valid_notebook):
    """Test section check with all required sections."""
    with tmp_notebook_path.open("w") as f:
        nbformat.write(valid_notebook, f)
    
    validator = NotebookValidator()
    report = validator.check_required_sections(tmp_notebook_path)
    
    assert report.passed
    assert report.check_name == "Required Sections"


def test_check_required_sections_missing(tmp_notebook_path: Path):
    """Test section check with missing sections."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="x = 1", metadata={"section": "setup"}))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_required_sections(tmp_notebook_path)
    
    assert not report.passed
    assert "missing" in report.message.lower()
    assert len(report.suggestions) > 0


def test_check_required_sections_custom(tmp_notebook_path: Path):
    """Test section check with custom required sections."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="x = 1", metadata={"section": "custom"}))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_required_sections(tmp_notebook_path, ["custom"])
    
    assert report.passed


def test_check_imports_present_all_present(tmp_notebook_path: Path, valid_notebook):
    """Test import check with all required imports."""
    with tmp_notebook_path.open("w") as f:
        nbformat.write(valid_notebook, f)
    
    validator = NotebookValidator()
    report = validator.check_imports_present(tmp_notebook_path)
    
    assert report.passed
    assert report.check_name == "Required Imports"


def test_check_imports_present_missing(tmp_notebook_path: Path):
    """Test import check with missing imports."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="x = 1"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_imports_present(tmp_notebook_path)
    
    assert not report.passed
    assert "missing" in report.message.lower()
    assert len(report.suggestions) > 0


def test_check_imports_present_custom(tmp_notebook_path: Path):
    """Test import check with custom required imports."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="import custom_module"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_imports_present(tmp_notebook_path, ["custom_module"])
    
    assert report.passed


def test_check_graph_compiles_valid(tmp_notebook_path: Path, valid_notebook):
    """Test graph compilation check with valid code."""
    with tmp_notebook_path.open("w") as f:
        nbformat.write(valid_notebook, f)
    
    validator = NotebookValidator()
    report = validator.check_graph_compiles(tmp_notebook_path)
    
    assert report.passed
    assert report.check_name == "Graph Compilation"


def test_check_graph_compiles_syntax_error(tmp_notebook_path: Path):
    """Test graph compilation check with syntax error."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="def broken(\npass"))  # Invalid syntax
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_graph_compiles(tmp_notebook_path)
    
    assert not report.passed
    assert "syntax" in report.message.lower()


def test_check_graph_compiles_no_stategraph(tmp_notebook_path: Path):
    """Test graph compilation check without StateGraph."""
    nb = new_notebook()
    nb.cells.append(new_code_cell(source="x = 1\nprint(x)"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_graph_compiles(tmp_notebook_path)
    
    assert not report.passed
    assert "StateGraph" in report.message


def test_check_graph_compiles_no_compile_call(tmp_notebook_path: Path):
    """Test graph compilation check without .compile() call."""
    nb = new_notebook()
    nb.cells.append(
        new_code_cell(
            source="from langgraph.graph import StateGraph\ngraph = StateGraph(dict)"
        )
    )
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_graph_compiles(tmp_notebook_path)
    
    assert not report.passed
    assert "compile" in report.message.lower()


def test_check_graph_compiles_no_code_cells(tmp_notebook_path: Path):
    """Test graph compilation check with no code cells."""
    nb = new_notebook()
    nb.cells.append(new_markdown_cell(source="# Just markdown"))
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    report = validator.check_graph_compiles(tmp_notebook_path)
    
    assert not report.passed
    assert "no code cells" in report.message.lower()


def test_validate_all_valid_notebook(tmp_notebook_path: Path, valid_notebook):
    """Test validate_all with a valid notebook."""
    with tmp_notebook_path.open("w") as f:
        nbformat.write(valid_notebook, f)
    
    validator = NotebookValidator()
    reports = validator.validate_all(tmp_notebook_path)
    
    assert len(reports) == 5  # All validation checks
    assert all(r.passed for r in reports)


def test_validate_all_invalid_json(tmp_notebook_path: Path):
    """Test validate_all with invalid JSON (should stop after first check)."""
    with tmp_notebook_path.open("w") as f:
        f.write("invalid json")
    
    validator = NotebookValidator()
    reports = validator.validate_all(tmp_notebook_path)
    
    # Only JSON validation should run if it fails
    assert len(reports) == 1
    assert reports[0].check_name == "JSON Validity"
    assert not reports[0].passed


def test_validate_all_mixed_results(tmp_notebook_path: Path):
    """Test validate_all with some passing and some failing checks."""
    nb = new_notebook()
    nb.cells.append(
        new_code_cell(
            source="from langgraph.graph import StateGraph, END\nimport langgraph\n# TODO: fix this",
            metadata={"section": "setup"},
        )
    )
    
    with tmp_notebook_path.open("w") as f:
        nbformat.write(nb, f)
    
    validator = NotebookValidator()
    reports = validator.validate_all(tmp_notebook_path)
    
    # Some checks should pass, some should fail
    assert len(reports) == 5
    passed = [r for r in reports if r.passed]
    failed = [r for r in reports if not r.passed]
    
    assert len(passed) > 0  # JSON and imports should pass
    assert len(failed) > 0  # Placeholders and missing sections should fail
