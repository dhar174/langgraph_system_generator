"""Reusable cell templates for generated notebooks."""

from __future__ import annotations

from textwrap import dedent
from typing import Iterable, List, Sequence

from langgraph_system_generator.generator.state import CellSpec

_DEFAULT_PACKAGES = ("langgraph", "langchain", "langchain-openai")


def installation_and_imports(
    packages: Sequence[str] | None = None,
) -> List[CellSpec]:
    """Return Installation & Imports cells."""
    pkgs = list(packages) if packages else list(_DEFAULT_PACKAGES)
    install_code = dedent(
        f"""
        # Install runtime requirements only if missing to avoid unnecessary network calls.
        import importlib
        import subprocess
        import sys

        def _ensure(package: str) -> None:
            module_name = package.replace("-", "_")
            try:
                importlib.import_module(module_name)
            except ImportError:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])

        for _pkg in {pkgs!r}:
            _ensure(_pkg)

        from langgraph.graph import END, StateGraph
        """
    ).strip()

    return [
        CellSpec(
            cell_type="markdown",
            content="## Installation & Imports\nPrepare dependencies for the notebook runtime.",
            section="setup",
        ),
        CellSpec(cell_type="code", content=install_code, section="setup"),
    ]


def configuration_cell(model: str = "gpt-4o-mini") -> List[CellSpec]:
    """Return configuration cells with API key handling."""
    config_code = dedent(
        f"""
        import os
        from getpass import getpass
        from pathlib import Path

        WORKDIR = Path(os.getenv("WORKDIR", ".")).resolve()
        WORKDIR.mkdir(parents=True, exist_ok=True)
        MODEL = os.getenv("MODEL", "{model}")

        if not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = getpass("Enter OPENAI_API_KEY (kept local): ")

        print(f"Using model: {{MODEL}}")
        print(f"Working directory: {{WORKDIR}}")
        """
    ).strip()

    return [
        CellSpec(
            cell_type="markdown",
            content="## Configuration\nSet runtime parameters and secrets.",
            section="config",
        ),
        CellSpec(cell_type="code", content=config_code, section="config"),
    ]


def build_graph_cells() -> List[CellSpec]:
    """Return Build Graph cells."""
    graph_code = dedent(
        """
        from typing import Annotated, Sequence, TypedDict
        import operator
        from langchain_core.messages import BaseMessage, HumanMessage
        from langgraph.graph import END, StateGraph

        class WorkflowState(TypedDict):
            messages: Annotated[Sequence[BaseMessage], operator.add]
            route: str | None

        graph = StateGraph(WorkflowState)

        def start(state: WorkflowState):
            return {"messages": [HumanMessage(content="Hello from the workflow!")]}

        graph.add_node("start", start)
        graph.set_entry_point("start")
        graph.add_edge("start", END)
        compiled_graph = graph.compile()
        """
    ).strip()

    return [
        CellSpec(
            cell_type="markdown",
            content="## Build Graph\nDefine the LangGraph workflow structure.",
            section="graph",
        ),
        CellSpec(cell_type="code", content=graph_code, section="graph"),
    ]


def run_graph_cells() -> List[CellSpec]:
    """Return Run Graph cells."""
    run_code = dedent(
        """
        sample_state = {"messages": [], "route": None}

        try:
            graph  # type: ignore[name-defined]  # noqa: F821
        except NameError as exc:
            raise NameError(
                "`graph` is not defined. Please run the 'Build Graph' cell before this one."
            ) from exc

        compiled_graph = graph.compile()
        result = compiled_graph.invoke(sample_state)
        print("Graph output:")
        print(result)
        """
    ).strip()

    return [
        CellSpec(
            cell_type="markdown",
            content="## Run Graph\nExecute the compiled graph with a sample state.",
            section="execution",
        ),
        CellSpec(cell_type="code", content=run_code, section="execution"),
    ]


def export_results_cells() -> List[CellSpec]:
    """Return Export Results cells."""
    export_code = dedent(
        """
        import json
        from pathlib import Path

        if "result" not in globals():
            raise NameError("`result` is not defined. Run the 'Run Graph' cell before exporting results.")

        output_data = result
        output_path = Path("graph_results.json")
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(output_data, handle, indent=2, default=str)

        print(f"Saved results to {output_path.resolve()}")
        """
    ).strip()

    return [
        CellSpec(
            cell_type="markdown",
            content="## Export Results\nPersist outputs for downstream use.",
            section="export",
        ),
        CellSpec(cell_type="code", content=export_code, section="export"),
    ]


def troubleshooting_cell() -> Iterable[CellSpec]:
    """Return Troubleshooting guidance."""
    return [
        CellSpec(
            cell_type="markdown",
            content=(
                "## Troubleshooting\n"
                "- Restart runtime if imports fail in Colab.\n"
                "- Confirm `OPENAI_API_KEY` is set before running graph cells.\n"
                "- Ensure pip installs complete before executing later cells.\n"
                "- Review output JSON for unexpected schema mismatches."
            ),
            section="troubleshooting",
        )
    ]
