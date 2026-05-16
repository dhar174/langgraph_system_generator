"""Tests for QA validators."""

from __future__ import annotations

from pathlib import Path

import nbformat
import pytest
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from langgraph_system_generator.qa.validators import (
    CanonicalSectionOrderRule,
    DomainArchitectureAlignmentRule,
    GraphStructureRule,
    InvocationConfigRule,
    LangGraphTopologyRule,
    NotebookValidator,
    PlaceholderRule,
    PythonSyntaxRule,
    RequiredImportsRule,
    RequiredSectionsRule,
    StateReducerSemanticsRule,
    ToolReachabilityRule,
    UndefinedNameRule,
    ValidatorRegistry,
)


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
                """from langgraph.graph import MessagesState

class State(MessagesState):
    pass

workflow = StateGraph(State)
workflow.add_node("start", lambda state: state)
workflow.set_entry_point("start")
workflow.add_edge("start", END)
graph = workflow.compile()""",
                metadata={"section": "graph"},
            ),
            new_markdown_cell("## Execution", metadata={"section": "execution"}),
            new_code_cell(
                'config = {"configurable": {"thread_id": "validator-test"}, "recursion_limit": 25}\n'
                'result = graph.invoke({"messages": []}, config)',
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


def test_validate_json_structure_malformed_json(tmp_notebook_path: Path):
    tmp_notebook_path.write_text('{"cells": [', encoding="utf-8")

    report = NotebookValidator().validate_json_structure(tmp_notebook_path)

    assert report.passed is False
    assert report.rule_id == "json_structure"
    assert report.category == "serialization"
    assert report.evidence["error_type"] == "json"
    assert report.evidence["message"]


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


def test_undefined_name_rule_flags_assignment_self_reference(tmp_notebook_path: Path):
    notebook = new_notebook()
    notebook.cells.append(new_code_cell("x = x + 1"))
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    undefined_report = _report_by_name(reports, "Undefined Names")

    assert undefined_report.passed is False
    assert "Likely undefined name 'x'" in undefined_report.message


def test_undefined_name_rule_allows_loop_and_with_targets_in_body(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """workers = [1]

for worker in workers:
    print(worker)

with open("README.md") as handle:
    print(handle)"""
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    undefined_report = _report_by_name(reports, "Undefined Names")

    assert undefined_report.passed is True


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


def test_canonical_section_order_rule_rejects_export_before_execution(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.extend(
        [
            new_code_cell("print('export')", metadata={"section": "export"}),
            new_code_cell("print('run')", metadata={"section": "execution"}),
        ]
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Canonical Section Order")

    assert report.passed is False
    assert report.rule_id == "canonical_section_order"
    assert report.severity == "error"


def test_langgraph_topology_rule_rejects_duplicates_and_self_loop(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langgraph.graph import END, START, StateGraph
from langgraph.graph import MessagesState

class WorkflowState(MessagesState):
    pass

def finish_node(state: WorkflowState) -> dict:
    return {"messages": []}

def finish_node(state: WorkflowState) -> dict:
    return {"messages": []}

workflow = StateGraph(WorkflowState)
workflow.add_node("finish", finish_node)
workflow.add_node("finish", finish_node)
workflow.add_edge(START, "finish")
workflow.add_edge("finish", "finish")
workflow.add_edge("finish", END)
graph = workflow.compile()""",
            metadata={"section": "graph"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "LangGraph Topology")
    issue_codes = {issue["code"] for issue in report.evidence["issues"]}

    assert report.passed is False
    assert "duplicate_node_registration" in issue_codes
    assert "duplicate_node_function" in issue_codes
    assert "unguarded_self_loop" in issue_codes


def test_langgraph_topology_rule_accepts_keyword_path_map_and_dotted_boundaries(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langgraph import graph as lg_graph
from langgraph.graph import StateGraph

class WorkflowState(dict):
    pass

def refine_node(state: WorkflowState) -> dict:
    return state

def should_continue(state: WorkflowState) -> str:
    return "retry"

workflow = StateGraph(WorkflowState)
workflow.add_node("refine", refine_node)
workflow.add_edge(lg_graph.START, "refine")
workflow.add_conditional_edges(
    source="refine",
    path=should_continue,
    path_map={"retry": "refine", "done": lg_graph.END},
)
graph = workflow.compile()""",
            metadata={"section": "graph"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "LangGraph Topology")

    assert report.passed is True
    assert any(
        edge.get("source") == "refine"
        and edge.get("target") == "refine"
        and edge.get("conditional")
        for edge in report.evidence["edge_registrations"]
    )


def test_state_reducer_semantics_rule_rejects_duplicate_fields(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from typing import Annotated, List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class WorkflowState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    messages: list
""",
            metadata={"section": "state"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "State Reducer Semantics")

    assert report.passed is False
    assert report.rule_id == "state_reducer_semantics"
    assert report.evidence["issues"][0]["code"] == "duplicate_state_field"


def test_state_reducer_semantics_rule_detects_prefixed_typeddict(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """import typing

class WorkflowState(typing.TypedDict):
    messages: list

def worker(state: WorkflowState) -> dict:
    return {"messages": ["hello"]}
""",
            metadata={"section": "state"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "State Reducer Semantics")

    assert report.passed is False
    assert report.evidence["issues"][0]["code"] == "messages_missing_reducer"


def test_state_reducer_semantics_rule_catches_messagesstate_reducer_override(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langgraph.graph import MessagesState

class WorkflowState(MessagesState):
    messages: list

def worker(state: WorkflowState) -> dict:
    return {"messages": ["hello"]}
""",
            metadata={"section": "state"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "State Reducer Semantics")

    assert report.passed is False
    assert report.evidence["issues"][0]["code"] == "messages_missing_reducer"


def test_state_reducer_semantics_rule_warns_for_multi_writer_without_reducer(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from typing_extensions import TypedDict
from langgraph.graph import MessagesState

class WorkflowState(MessagesState):
    final_output: str

def first_node(state: WorkflowState) -> dict:
    return {"final_output": "first"}

def second_node(state: WorkflowState) -> dict:
    return {"final_output": "second"}
""",
            metadata={"section": "state"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "State Reducer Semantics")

    assert report.passed is False
    assert report.severity == "warning"
    assert (
        report.evidence["warnings"][0]["code"] == "multi_writer_field_without_reducer"
    )


def test_state_reducer_semantics_rule_rejects_full_state_overwrite(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langgraph.graph import MessagesState, StateGraph

class WorkflowState(MessagesState):
    route: str

def router_node(state: WorkflowState) -> dict:
    return {**state, "route": "artifact_cataloger"}

workflow = StateGraph(WorkflowState)
workflow.add_node("router", router_node)
""",
            metadata={"section": "state"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "State Reducer Semantics")
    issue_codes = {issue["code"] for issue in report.evidence["issues"]}

    assert report.passed is False
    assert "full_state_overwrite" in issue_codes


def test_state_reducer_semantics_rule_ignores_unregistered_state_helpers(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langgraph.graph import MessagesState, StateGraph

class WorkflowState(MessagesState):
    route: str

def copy_state(state: WorkflowState) -> WorkflowState:
    return state

def router_node(state: WorkflowState) -> dict:
    return {"route": "artifact_cataloger"}

workflow = StateGraph(WorkflowState)
workflow.add_node("router", router_node)
""",
            metadata={"section": "state"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "State Reducer Semantics")

    assert report.passed is True
    assert "route" in report.evidence["writer_map"]
    assert "copy_state" not in report.evidence["writer_map"].get("route", [])


def test_tool_reachability_rule_flags_unbound_placeholder_tools(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langchain_core.tools import tool

@tool
def lookup_context(query: str) -> str:
    \"\"\"Placeholder tool for auxiliary context lookup.\"\"\"
    return f"Context for: {query}"
""",
            metadata={"section": "tools"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Tool Reachability")
    issue_codes = {issue["code"] for issue in report.evidence["advisories"]}

    assert report.passed is False
    assert report.severity == "warning"
    assert "placeholder_tool_description" in issue_codes
    assert "unreachable_tool" in issue_codes


def test_tool_reachability_rule_flags_unsafe_broad_http_tool(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langchain_core.tools import tool
import requests

@tool
def fetch_url(url: str) -> str:
    '''Fetch a remote URL for context.'''
    return requests.get(url, timeout=5).text

tools = [fetch_url]
result = fetch_url.invoke("https://example.com")
""",
            metadata={"section": "tools"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Tool Reachability")
    issue_codes = {issue["code"] for issue in report.evidence["advisories"]}

    assert report.passed is False
    assert "unsafe_http_tool" in issue_codes


def test_tool_reachability_rule_rejects_docstring_only_http_safety(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langchain_core.tools import tool
import requests

@tool
def fetch_url(url: str) -> str:
    '''Fetch only trusted allowlist endpoints for context.'''
    return requests.get(url, timeout=5).text

result = fetch_url.invoke("https://example.com")
""",
            metadata={"section": "tools"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Tool Reachability")
    issue_codes = {issue["code"] for issue in report.evidence["advisories"]}

    assert report.passed is False
    assert "unsafe_http_tool" in issue_codes


def test_tool_reachability_rule_accepts_enforced_http_allowlist(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langchain_core.tools import tool
from urllib.parse import urlparse
import requests

ALLOWED_HOSTS = {"example.com"}

@tool
def fetch_url(url: str) -> str:
    '''Fetch approved context from a bounded endpoint list.'''
    host = urlparse(url).hostname
    if host not in ALLOWED_HOSTS:
        raise ValueError("Blocked unapproved host")
    return requests.get(url, timeout=5).text

result = fetch_url.invoke("https://example.com")
""",
            metadata={"section": "tools"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Tool Reachability")

    assert report.passed is True


def test_tool_reachability_rule_rejects_allowlisted_request_with_unsafe_fallback(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langchain_core.tools import tool
from urllib.parse import urlparse
import requests

ALLOWED_HOSTS = {"example.com"}

@tool
def fetch_url(url: str) -> str:
    '''Fetch approved context from a bounded endpoint list.'''
    host = urlparse(url).hostname
    if host in ALLOWED_HOSTS:
        return requests.get(url, timeout=5).text
    return requests.get(url, timeout=5).text

result = fetch_url.invoke("https://example.com")
""",
            metadata={"section": "tools"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Tool Reachability")
    issue_codes = {issue["code"] for issue in report.evidence["advisories"]}

    assert report.passed is False
    assert "unsafe_http_tool" in issue_codes


def test_domain_architecture_alignment_rule_rejects_generic_domain_nodes(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.extend(
        [
            new_markdown_cell("Museum artifact cataloging workflow"),
            new_code_cell(
                """from langgraph.graph import StateGraph

def specialist_1_node(state):
    return {"final_output": "cataloged"}

workflow = StateGraph(dict)
workflow.add_node("specialist_1", specialist_1_node)
""",
                metadata={"section": "graph"},
            ),
        ]
    )
    _write_notebook(tmp_notebook_path, notebook)

    report = DomainArchitectureAlignmentRule().validate(
        NotebookValidator()._context_from_path(tmp_notebook_path)
    )

    assert report is not None
    assert report.passed is False
    assert "museum" in report.evidence["matched_domains"]
    assert report.evidence["generic_nodes"]


def test_tool_reachability_rule_requires_executor_for_bound_tools(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langchain_core.tools import tool

@tool
def lookup_context(query: str) -> str:
    \"\"\"Lookup context.\"\"\"
    return query

tools = [lookup_context]
model_with_tools = model.bind_tools(tools)
""",
            metadata={"section": "tools"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Tool Reachability")

    assert report.passed is False
    assert report.evidence["advisories"][0]["code"] == "bound_tool_without_executor"


def test_tool_reachability_rule_accepts_tool_node_executor(tmp_notebook_path: Path):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

@tool
def lookup_context(query: str) -> str:
    \"\"\"Lookup context.\"\"\"
    return query

tools = [lookup_context]
tool_node = ToolNode(tools)
""",
            metadata={"section": "tools"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Tool Reachability")

    assert report.passed is True


def test_invocation_config_rule_requires_thread_id_and_recursion_limit(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """config = {"configurable": {"thread_id": "demo"}}
final_state = graph.invoke({"messages": []}, config)
for update in graph.stream({"messages": []}, config, stream_mode="updates"):
    print(update)
""",
            metadata={"section": "execution"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Invocation Config")
    issue_codes = {issue["code"] for issue in report.evidence["issues"]}

    assert report.passed is False
    assert issue_codes == {"missing_recursion_limit"}


def test_invocation_config_rule_checks_async_and_custom_graph_targets(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """workflow = builder()
self.graph = workflow.compile()
config = {"configurable": {"thread_id": "demo"}, "recursion_limit": 25}
async def run_graph() -> None:
    final_state = await self.graph.ainvoke({"messages": []}, config)
    async for update in self.graph.astream({"messages": []}, config):
        print(update)
""",
            metadata={"section": "execution"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Invocation Config")

    assert report.passed is True
    assert "self.graph" in report.evidence["graph_references"]


def test_invocation_config_rule_fails_when_execution_is_missing(
    tmp_notebook_path: Path,
):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """workflow = builder()
graph = workflow.compile()
print("compiled")
""",
            metadata={"section": "execution"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Invocation Config")

    assert report.passed is False
    assert report.evidence["issues"][0]["code"] == "missing_graph_invocation"


def test_invocation_config_rule_accepts_documented_config(tmp_notebook_path: Path):
    notebook = new_notebook()
    notebook.cells.append(
        new_code_cell(
            """config = {
    "configurable": {"thread_id": "demo"},
    "recursion_limit": 25,
}
for update in graph.stream({"messages": []}, config, stream_mode="updates"):
    print(update)
final_state = graph.invoke({"messages": []}, config)
snapshot = graph.get_state(config)
""",
            metadata={"section": "execution"},
        )
    )
    _write_notebook(tmp_notebook_path, notebook)

    reports = NotebookValidator().validate_all(tmp_notebook_path)
    report = _report_by_name(reports, "Invocation Config")

    assert report.passed is True


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


def test_single_check_helpers_use_registry_backed_rules(
    tmp_notebook_path: Path, valid_notebook
):
    class CustomRequiredSectionsRule(RequiredSectionsRule):
        def validate(self, context):
            return self.passed_report("custom required sections")

    class CustomRequiredImportsRule(RequiredImportsRule):
        def validate(self, context):
            return self.passed_report("custom required imports")

    class CustomPythonSyntaxRule(PythonSyntaxRule):
        def validate(self, context):
            return self.passed_report("custom syntax")

    class CustomGraphStructureRule(GraphStructureRule):
        def validate(self, context):
            return self.passed_report("custom graph structure")

    registry = ValidatorRegistry(
        [
            PlaceholderRule(NotebookValidator.PLACEHOLDER_PATTERNS),
            CustomRequiredSectionsRule(NotebookValidator.REQUIRED_SECTIONS),
            CustomRequiredImportsRule(NotebookValidator.REQUIRED_IMPORTS),
            CustomPythonSyntaxRule(),
            UndefinedNameRule(),
            CustomGraphStructureRule(),
            CanonicalSectionOrderRule(),
            LangGraphTopologyRule(),
            StateReducerSemanticsRule(),
            ToolReachabilityRule(),
            InvocationConfigRule(),
        ]
    )
    _write_notebook(tmp_notebook_path, valid_notebook)

    validator = NotebookValidator(registry=registry)

    assert (
        validator.check_required_sections(tmp_notebook_path).message
        == "custom required sections"
    )
    assert (
        validator.check_imports_present(tmp_notebook_path).message
        == "custom required imports"
    )
    assert (
        validator.check_graph_compiles(tmp_notebook_path).message
        == "custom graph structure"
    )
