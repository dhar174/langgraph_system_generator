"""Runnable router-pattern example aligned with current LangGraph idioms."""

from __future__ import annotations

import operator
import sys
from pathlib import Path
from typing import Annotated, Dict, List, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

if __package__ in (None, ""):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    for path in (REPO_ROOT, REPO_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command

from langgraph_system_generator.examples_support import (
    build_example_parser,
    build_metrics,
    ensure_live_credentials,
    make_thread_config,
    trace_step,
)

ROUTES = ("search", "analyze", "summarize")


def merge_dicts(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    """Merge route outputs into a single state field."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class RouterState(TypedDict, total=False):
    """State for the router example."""

    messages: Annotated[List[BaseMessage], add_messages]
    route: str
    route_reasoning: str
    route_history: Annotated[List[str], operator.add]
    results: Annotated[Dict[str, str], merge_dicts]
    final_output: str


class RouteDecision(BaseModel):
    """Structured router output."""

    route: Literal["search", "analyze", "summarize"] = Field(
        description="Specialist that should handle the request."
    )
    reasoning: str = Field(description="Why the route matches the request.")


def _stub_route_decision(task: str) -> RouteDecision:
    lowered = task.lower()
    if any(token in lowered for token in ("find", "research", "search", "lookup")):
        return RouteDecision(route="search", reasoning="The task asks for retrieval.")
    if any(token in lowered for token in ("analyze", "compare", "pattern", "trend")):
        return RouteDecision(
            route="analyze",
            reasoning="The task asks for interpretation.",
        )
    return RouteDecision(
        route="summarize",
        reasoning="The task asks for concise synthesis.",
    )


def _stub_specialist_output(route: str, task: str) -> str:
    if route == "search":
        return (
            "Stub search result:\n"
            "- Source A: Current LangGraph docs emphasize Command for dynamic routing.\n"
            "- Source B: Reducers keep shared state merges explicit.\n"
            f"- Query handled: {task}"
        )
    if route == "analyze":
        return (
            "Stub analysis:\n"
            "- Pattern fit: Command-based router keeps control flow inside the node.\n"
            "- Trade-off: deterministic routing is faster, semantic routing is more flexible.\n"
            f"- Task analyzed: {task}"
        )
    return (
        "Stub summary:\n"
        "- Use a small specialist graph when the request has a clear dominant intent.\n"
        "- Promote to supervisor/subagents when multiple specialties must collaborate.\n"
        f"- Task summarized: {task}"
    )


def build_graph(mode: str, model: str):
    """Build the runnable router graph for the selected mode."""
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def router_node(
        state: RouterState,
    ) -> Command[Literal["search", "analyze", "summarize"]]:
        task = state["messages"][-1].content if state.get("messages") else ""
        decision = (
            llm.with_structured_output(RouteDecision).invoke(
                [
                    SystemMessage(
                        content=(
                            "You route requests to one specialist.\n"
                            "- search: retrieval, sourcing, lookup\n"
                            "- analyze: comparisons, trend detection, interpretation\n"
                            "- summarize: concise synthesis\n"
                        )
                    ),
                    HumanMessage(content=f"Task: {task}"),
                ]
            )
            if llm
            else _stub_route_decision(task)
        )
        return Command(
            update={
                "route": decision.route,
                "route_reasoning": decision.reasoning,
                "route_history": [decision.route],
                "messages": [
                    AIMessage(
                        content=f"Router selected {decision.route}: {decision.reasoning}"
                    )
                ],
            },
            goto=decision.route,
        )

    def specialist_node(route: str, purpose: str):
        def _node(state: RouterState) -> Dict[str, object]:
            task = state["messages"][0].content if state.get("messages") else ""
            if llm:
                response = llm.invoke(
                    [
                        SystemMessage(
                            content=(
                                f"You are the {route} specialist.\n"
                                f"Purpose: {purpose}\n"
                                "Respond with a useful answer for the task."
                            )
                        ),
                        *state.get("messages", []),
                    ]
                )
                content = response.content
            else:
                content = _stub_specialist_output(route, task)
            return {
                "results": {route: content},
                "final_output": content,
                "messages": [
                    AIMessage(content=f"{route} specialist completed the task.")
                ],
            }

        return _node

    workflow = StateGraph(RouterState)
    workflow.add_node("router", router_node)
    workflow.add_node(
        "search",
        specialist_node("search", "Gather a grounded answer with cited-style notes."),
    )
    workflow.add_node(
        "analyze",
        specialist_node(
            "analyze",
            "Interpret the request and explain patterns or trade-offs.",
        ),
    )
    workflow.add_node(
        "summarize",
        specialist_node(
            "summarize",
            "Create a concise answer highlighting only key takeaways.",
        ),
    )
    workflow.add_edge(START, "router")
    for route in ROUTES:
        workflow.add_edge(route, END)
    return workflow.compile(checkpointer=InMemorySaver())


def run_demo(
    task: str,
    *,
    mode: str = "stub",
    model: str = "gpt-4.1-mini",
) -> Dict[str, object]:
    """Execute the router example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(mode, model)
    config = make_thread_config()
    state: RouterState = {
        "messages": [HumanMessage(content=task)],
        "results": {},
        "route_history": [],
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    final_state: Dict[str, object] = {}
    for step in graph.stream(state, config=config, stream_mode="values"):
        snapshot = {
            "route": step.get("route"),
            "route_reasoning": step.get("route_reasoning"),
            "results": step.get("results", {}),
            "final_output": step.get("final_output", ""),
        }
        trace_step("router-step", snapshot)
        final_state = dict(step)
    trace_step("router-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run a router-pattern example.",
        "Search the docs and summarize when Command is preferable to conditional edges.",
    )
    args = parser.parse_args()
    result = run_demo(args.task, mode=args.mode, model=args.model)
    print("Router Pattern Example")
    print(f"Mode: {args.mode}")
    print("Route selected:", result.get("route"))
    print("Final route:", result.get("route"))
    print("Final output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
