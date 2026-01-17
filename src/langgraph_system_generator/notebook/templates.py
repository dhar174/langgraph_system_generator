"""Reusable cell templates for generated notebooks."""

from __future__ import annotations

from textwrap import dedent
from typing import Iterable, List, Sequence

from langgraph_system_generator.generator.state import CellSpec

_DEFAULT_PACKAGES = (
    "langgraph",
    "langchain-core",
    "langchain-community",
    "langchain-openai",
)


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

        from langgraph.graph import END, START, MessagesState, StateGraph
        from langgraph.types import Command
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.prebuilt import create_react_agent
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
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
        from google.colab import userdata
        
        
        
        
        WORKDIR = Path(os.getenv("WORKDIR", ".")).resolve()
        WORKDIR.mkdir(parents=True, exist_ok=True)
        MODEL = os.getenv("MODEL", "gpt-4o-mini")
        
        if not os.environ.get("OPENAI_API_KEY"):
          if userdata.get('OPENAI_API_KEY'):
            os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY')
          else:
            os.environ["OPENAI_API_KEY"] = getpass("Enter OPENAI_API_KEY (kept local): ")
        
        if os.environ.get("OPENAI_API_KEY"):
          print("OPENAI_API_KEY found in environment variables.")
        
        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            if userdata.get('ANTHROPIC_API_KEY'):
                os.environ["ANTHROPIC_API_KEY"] = userdata.get('ANTHROPIC_API_KEY')
            elif not os.environ.get("OPENAI_API_KEY"):
                os.environ["ANTHROPIC_API_KEY"] = getpass("Enter ANTHROPIC_API_KEY (optional): ")
        
        print(f"Using model: {MODEL}")
        print(f"Working directory: {WORKDIR}")
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
        from langgraph.types import Command
        from langgraph.graph import END, START, MessagesState, StateGraph
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.prebuilt import create_react_agent
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI

        # Define state using the built-in message reducer
        class WorkflowState(MessagesState):
            pass

        # Configure a simple ReAct-style agent
        llm = ChatOpenAI(model=MODEL, temperature=0)
        router = create_react_agent(
            llm,
            tools=[],
            prompt="You are a router that decides whether to hand off or answer directly.",
        )

        def router_node(state: WorkflowState) -> Command:
            result = router.invoke({"messages": state["messages"]})
            return Command(
                update={"messages": result["messages"]},
                goto=END,
            )

        graph = StateGraph(WorkflowState)
        graph.add_node("router_node", router_node)
        graph.add_edge(START, "router_node")

        memory = MemorySaver()
        app = graph.compile(checkpointer=memory)
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
        try:
            app  # type: ignore[name-defined]  # noqa: F821
        except NameError as exc:
            raise NameError(
                "`app` is not defined. Please run the 'Build Graph' cell before this one."
            ) from exc

        config = {"configurable": {"thread_id": "lnf-demo-thread"}}
        initial_messages = [HumanMessage(content="Hi! Show me the LangGraph demo.")]

        print("Streaming updates (per step):")
        for update in app.stream(
            {"messages": initial_messages}, config, stream_mode="updates"
        ):
            print(update)

        final_state = app.get_state(config).values
        print("Final message:", final_state["messages"][-1])
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

        if "app" not in globals():
            raise NameError("`app` is not defined. Run the 'Run Graph' cell before exporting results.")

        config = {"configurable": {"thread_id": "lnf-demo-thread"}}
        output_data = app.get_state(config).values
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
