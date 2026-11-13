"""Small callable notebook fixtures for the hand-authored semantic cases."""

from __future__ import annotations

import ast
from copy import deepcopy
from textwrap import dedent
from typing import Any


def _cell(section: str, cell_type: str, content: str) -> dict[str, Any]:
    return {
        "cell_type": cell_type,
        "section": section,
        "metadata": {},
        "content": dedent(content).strip(),
    }


def coherent_cells(
    prompt: str,
    function_source: str,
    function_name: str,
    *,
    claim: str | None = None,
) -> list[dict[str, Any]]:
    """Expose the supplied fixture operation through a reachable LangGraph node."""
    tree = ast.parse(function_source)
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == function_name
        for node in tree.body
    ):
        raise ValueError("The named fixture operation must be defined at module scope.")

    intro = "# Workflow\n\n" + prompt
    if claim:
        intro += "\n\n" + claim
    return [
        _cell("intro", "markdown", intro),
        _cell(
            "setup",
            "code",
            """
            from typing import Any, TypedDict

            from langgraph.graph import END, START, StateGraph
            """,
        ),
        _cell(
            "config",
            "code",
            'CONFIG = {"configurable": {"thread_id": "fixture-session"}, "recursion_limit": 10}',
        ),
        _cell(
            "state",
            "code",
            """
            class WorkflowState(TypedDict, total=False):
                request: dict[str, Any]
                result: Any
            """,
        ),
        _cell(
            "nodes",
            "code",
            function_source.strip()
            + "\n\ndef perform_request(state: WorkflowState) -> WorkflowState:\n"
            + f'    return {{"result": {function_name}(**state["request"])}}',
        ),
        _cell(
            "graph",
            "code",
            """
            builder = StateGraph(WorkflowState)
            builder.add_node("perform_request", perform_request)
            builder.add_edge(START, "perform_request")
            builder.add_edge("perform_request", END)
            graph = builder.compile()
            """,
        ),
        _cell(
            "execution",
            "code",
            """
            def run_workflow(request: dict[str, Any]) -> Any:
                result = graph.invoke({"request": request}, config=CONFIG)
                return result["result"]
            """,
        ),
        _cell(
            "export",
            "markdown",
            "The workflow returns the result from the requested operation.",
        ),
        _cell(
            "troubleshooting",
            "markdown",
            "Supply the operation's named arguments in the request dictionary.",
        ),
    ]


def research_supervisor_cells(prompt: str) -> list[dict[str, Any]]:
    """Build a parallel research workflow with reducer-backed worker results."""
    return [
        _cell("intro", "markdown", "# Research brief\n\n" + prompt),
        _cell(
            "setup",
            "code",
            """
            from typing import Annotated, TypedDict

            from langgraph.graph import END, START, StateGraph
            """,
        ),
        _cell(
            "config",
            "code",
            'CONFIG = {"configurable": {"thread_id": "research-fixture"}, "recursion_limit": 10}',
        ),
        _cell(
            "state",
            "code",
            """
            def combine_results(
                current: dict[str, str], update: dict[str, str]
            ) -> dict[str, str]:
                return {**current, **update}


            class ResearchState(TypedDict, total=False):
                field_notes: str
                archive_notes: str
                results: Annotated[dict[str, str], combine_results]
                brief: dict[str, str]
            """,
        ),
        _cell(
            "nodes",
            "code",
            """
            def summarize(notes: str) -> str:
                sentences = notes.strip().split(". ", 2)
                return ". ".join(sentences[:2]).strip()


            def researcher(state: ResearchState) -> ResearchState:
                return {"results": {"researcher": summarize(state["field_notes"])}}


            def reviewer(state: ResearchState) -> ResearchState:
                return {"results": {"reviewer": summarize(state["archive_notes"])}}


            def finish(state: ResearchState) -> ResearchState:
                source_names = {"researcher": "Field notes", "reviewer": "Archive review"}
                results = state["results"]
                return {
                    "brief": {
                        source_names[agent]: output for agent, output in results.items()
                    }
                }
            """,
        ),
        _cell(
            "graph",
            "code",
            """
            builder = StateGraph(ResearchState)
            builder.add_node("researcher", researcher)
            builder.add_node("reviewer", reviewer)
            builder.add_node("finish", finish)
            builder.add_edge(START, "researcher")
            builder.add_edge(START, "reviewer")
            builder.add_edge(["researcher", "reviewer"], "finish")
            builder.add_edge("finish", END)
            graph = builder.compile()
            """,
        ),
        _cell(
            "execution",
            "code",
            """
            def prepare_brief(field_notes: str, archive_notes: str) -> dict[str, str]:
                request = {"field_notes": field_notes, "archive_notes": archive_notes}
                return graph.invoke(request, config=CONFIG)["brief"]
            """,
        ),
        _cell(
            "export",
            "markdown",
            "The brief maps each source name to its specialist's summary.",
        ),
        _cell(
            "troubleshooting",
            "markdown",
            "Provide field notes and archive notes as separate text arguments.",
        ),
    ]


def replace_code(
    cells: list[dict[str, Any]], old: str, new: str
) -> list[dict[str, Any]]:
    """Copy cells and replace one exact code fragment with another."""
    copied = deepcopy(cells)
    matches = [
        item
        for item in copied
        if item["cell_type"] == "code" and old in item["content"]
    ]
    if len(matches) != 1 or matches[0]["content"].count(old) != 1:
        raise ValueError("A mutation must identify exactly one code fragment.")
    matches[0]["content"] = matches[0]["content"].replace(old, new, 1)
    ast.parse(matches[0]["content"])
    return copied
