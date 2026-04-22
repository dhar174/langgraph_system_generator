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

    notebook = new_notebook()
    notebook.cells.extend(
        [
            new_markdown_cell("## Setup", metadata={"section": "setup"}),
            new_code_cell(
                "import langgraph\nfrom langgraph.graph import END, StateGraph",
                metadata={"section": "setup"},
            ),
            new_markdown_cell("## Config", metadata={"section": "config"}),
            new_code_cell('MODEL = "gpt-5-mini"', metadata={"section": "config"}),
            new_markdown_cell("## Graph", metadata={"section": "graph"}),
            new_code_cell(
                """from typing import TypedDict

class State(TypedDict):
    messages: list

workflow = StateGraph(State)
workflow.add_node("start", lambda state: state)
workflow.set_entry_point("start")
workflow.add_edge("start", END)
graph = workflow.compile()""",
                metadata={"section": "graph"},
            ),
            new_markdown_cell("## Execution", metadata={"section": "execution"}),
            new_code_cell(
                'result = graph.invoke({"messages": []})',
                metadata={"section": "execution"},
            ),
        ]
    )
    return notebook


def _write_notebook(path: Path, notebook: nbformat.NotebookNode) -> None:
    with path.open("w", encoding="utf-8") as handle:
        nbformat.write(notebook, handle)


def _report_by_name(reports, name: str):
    return next(report for report in reports if report.check_name == name)


def test_validate_json_structure_valid(tmp_notebook_path: Path, valid_notebook):
    _write_notebook(tmp_notebook_path, valid_notebook)

    report = NotebookValidator().validate_json_structure(tmp_notebook_path)

    assert report.passed is True
    assert report.rule_id == "json_structure"
    assert report.category == "serialization"


def test_validate_json_structure_missing_file(tmp_path: Path):
    report = NotebookValidator().validate_json_structure(tmp_path / "missing.ipynb")

    assert report.passed is False
    assert "not found" in report.message.lower()
    assert report.rule_id == "json_structure"


def test_check_no_placeholders_detects_placeholder_content(tmp_notebook_path: Path):
    notebook = new_notebook()
    notebook.cells.append(new_code_cell("# TODO: implement\npass"))
    _write_notebook(tmp_notebook_path, notebook)

    report = NotebookValidator().check_no_placeholders(tmp_notebook_path)

    assert report.passed is False
    assert report.rule_id == "placeholder_content"
    assert report.repairable is True


def test_check_required_sections_missing(tmp_notebook_path: Path):
    notebook = new_notebook()
    notebook.cells.append(new_code_cell("x = 1", metadata={"section": "setup"}))
    _write_notebook(tmp_notebook_path, notebook)

    report = NotebookValidator().check_required_sections(tmp_notebook_path)

    assert report.passed is False
    assert "missing required sections" in report.message.lower()
    assert report.category == "structure"


def test_check_imports_present_uses_parsed_imports_not_substring_matching(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            '# StateGraph appears in a comment only\nprint("END appears in a string")'
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    report = NotebookValidator().check_imports_present(tmp_notebook_path)

    assert report.passed is False
    assert report.rule_id == "required_import_symbols"
    assert "StateGraph" in report.message
    assert "END" in report.message


def test_python_syntax_report_includes_precise_line_evidence(tmp_notebook_path: Path):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell("def broken_graph(\n    pass", metadata={"section": "graph"})
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    syntax_report = _report_by_name(reports, "Python Syntax")

    assert syntax_report.passed is False
    assert syntax_report.rule_id == "python_syntax"
    assert syntax_report.evidence["syntax_error"]["line"] == 1
    assert syntax_report.evidence["syntax_error"]["cell_index"] == 0
    assert "broken_graph" in syntax_report.evidence["syntax_error"]["source_line"]


def test_undefined_name_rule_detects_likely_typo_in_execution_path(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langgraph.graph import END, StateGraph

workflow = StateGraph(dict)
workflow.add_node("start", lambda state: state)
workflow.set_entry_point("start")
workflow.add_edge("start", END)
compiled_graph = workflow.compile()
result = compiled_grap.invoke({})""",
            metadata={"section": "graph"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    undefined_report = _report_by_name(reports, "Undefined Names")

    assert undefined_report.passed is False
    assert undefined_report.rule_id == "undefined_names"
    assert "compiled_grap" in undefined_report.message
    assert "compiled_graph" in undefined_report.message


def test_graph_structure_rule_uses_ast_not_string_presence(tmp_notebook_path: Path):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            'graph_hint = "StateGraph"\ncompile_hint = ".compile()"\nprint(graph_hint, compile_hint)',
            metadata={"section": "graph"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    report = NotebookValidator().check_graph_compiles(tmp_notebook_path)

    assert report.passed is False
    assert report.rule_id == "graph_structure"
    assert "StateGraph construction" in report.message


def test_graph_structure_rule_requires_terminal_path(tmp_notebook_path: Path):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langgraph.graph import StateGraph

workflow = StateGraph(dict)
workflow.set_entry_point("start")
graph = workflow.compile()""",
            metadata={"section": "graph"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    report = NotebookValidator().check_graph_compiles(tmp_notebook_path)

    assert report.passed is False
    assert "terminal path to END" in report.message


def test_validate_all_emits_structured_reports(tmp_notebook_path: Path, valid_notebook):
    _write_notebook(tmp_notebook_path, valid_notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)

    assert _report_by_name(reports, "JSON Validity").passed is True
    assert _report_by_name(reports, "Required Imports").passed is True
    assert _report_by_name(reports, "Python Syntax").passed is True
    assert _report_by_name(reports, "Graph Compilation").passed is True
    for report in reports:
        assert report.rule_id
        assert report.severity in {"info", "warning", "error"}
        assert report.category
        assert isinstance(report.repairable, bool)


def test_validate_all_skips_deep_ast_rules_when_syntax_is_broken(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(new_code_cell("def broken(\npass"))
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report_names = {report.check_name for report in reports}

    assert "Python Syntax" in report_names
    assert "Undefined Names" not in report_names
    assert "Graph Compilation" not in report_names
