"""Runnable router pattern demo built with current LangGraph state patterns.

The example defaults to ``stub`` mode so it can run without network access.
Use ``--mode live`` to switch to ``ChatOpenAI``-backed routing and handlers.

Examples:
    python examples/router_pattern_example.py --mode stub
    python examples/router_pattern_example.py --mode live --input "Analyze this incident report"
"""

from __future__ import annotations

import argparse
import operator
import os
from typing import Annotated, Literal, Optional

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

ExampleMode = Literal["stub", "live"]
RouteName = Literal["search", "analyze", "summarize"]

DEFAULT_INPUT = "Analyze the attached customer feedback themes and summarize the biggest risks."
DEFAULT_MODEL = os.environ.get("LNF_EXAMPLE_MODEL", "gpt-5-mini")


class RouteDecision(BaseModel):
    """Structured routing output used by the router node."""

    route: RouteName = Field(description="The specialist route that should handle the request.")
    reason: str = Field(description="Short explanation for the chosen route.")


class RouterState(TypedDict):
    """Shared graph state for the router example."""

    messages: Annotated[list[AnyMessage], add_messages]
    route_trace: Annotated[list[str], operator.add]
    route: str
    route_reason: str
    final_output: str


def _require_live_api_key(mode: ExampleMode) -> None:
    if mode == "live" and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for --mode live.")


def _build_live_model(*, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(model=DEFAULT_MODEL, temperature=temperature)


def _route_stub(user_input: str) -> RouteDecision:
    lowered = user_input.lower()
    if any(token in lowered for token in ("find", "lookup", "search", "research")):
        return RouteDecision(
            route="search",
            reason="Stub router detected a retrieval-style request.",
        )
    if any(token in lowered for token in ("analyze", "pattern", "trend", "compare", "risk")):
        return RouteDecision(
            route="analyze",
            reason="Stub router detected an analysis-focused request.",
        )
    return RouteDecision(
        route="summarize",
        reason="Stub router fell back to summarization for a broad request.",
    )


def _route_live(user_input: str) -> RouteDecision:
    model = _build_live_model(temperature=0)
    structured_model = model.with_structured_output(RouteDecision)
    return structured_model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a deterministic router for a LangGraph demo. "
                    "Choose exactly one route: search, analyze, or summarize."
                )
            ),
            HumanMessage(content=user_input),
        ]
    )


def _run_search(mode: ExampleMode, user_input: str) -> str:
    if mode == "stub":
        return (
            "Stub search report:\n"
            "- Gathered three representative customer comments.\n"
            "- Retrieved two competitor notes.\n"
            "- Highlighted a recent churn trend tied to onboarding friction."
        )

    model = _build_live_model(temperature=0.2)
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a retrieval specialist. Return concise research notes that a downstream "
                    "analyst can use immediately."
                )
            ),
            HumanMessage(content=user_input),
        ]
    )
    return response.content


def _run_analysis(mode: ExampleMode, user_input: str) -> str:
    if mode == "stub":
        return (
            "Stub analysis:\n"
            "- The dominant risk is onboarding confusion during the first session.\n"
            "- A secondary risk is missing follow-up nudges for inactive users.\n"
            "- The highest-leverage fix is a guided checklist plus a day-two reminder."
        )

    model = _build_live_model(temperature=0.2)
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "You are an analyst. Explain patterns, risks, and recommended next steps in a tight "
                    "operator-facing format."
                )
            ),
            HumanMessage(content=user_input),
        ]
    )
    return response.content


def _run_summary(mode: ExampleMode, user_input: str) -> str:
    if mode == "stub":
        return (
            "Stub summary:\n"
            "The request should be condensed into a short executive update with one key risk, one key "
            "opportunity, and one immediate action."
        )

    model = _build_live_model(temperature=0.2)
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a summarization specialist. Produce a short, polished summary with a clear "
                    "takeaway."
                )
            ),
            HumanMessage(content=user_input),
        ]
    )
    return response.content


def build_router_graph(mode: ExampleMode = "stub"):
    """Build a runnable router graph using current LangGraph patterns."""

    _require_live_api_key(mode)

    def router_node(
        state: RouterState,
    ) -> Command[Literal["search", "analyze", "summarize"]]:
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        decision = _route_stub(user_input) if mode == "stub" else _route_live(user_input)

        # Returning Command keeps the state update and the dynamic route selection in one node.
        return Command(
            update={
                "route": decision.route,
                "route_reason": decision.reason,
                "route_trace": [f"router->{decision.route}"],
                "messages": [
                    AIMessage(
                        content=f"Router selected {decision.route}: {decision.reason}"
                    )
                ],
            },
            goto=decision.route,
        )

    def search_node(state: RouterState):
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        result = _run_search(mode, user_input)
        return {
            "final_output": result,
            "route_trace": ["search"],
            "messages": [AIMessage(content=result)],
        }

    def analyze_node(state: RouterState):
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        result = _run_analysis(mode, user_input)
        return {
            "final_output": result,
            "route_trace": ["analyze"],
            "messages": [AIMessage(content=result)],
        }

    def summarize_node(state: RouterState):
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        result = _run_summary(mode, user_input)
        return {
            "final_output": result,
            "route_trace": ["summarize"],
            "messages": [AIMessage(content=result)],
        }

    workflow = StateGraph(RouterState)
    workflow.add_node("router", router_node)
    workflow.add_node("search", search_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_edge(START, "router")
    workflow.add_edge("search", END)
    workflow.add_edge("analyze", END)
    workflow.add_edge("summarize", END)
    return workflow.compile()


def run_router_example(
    user_input: str = DEFAULT_INPUT,
    mode: ExampleMode = "stub",
) -> RouterState:
    """Execute the router demo and return the final graph state."""

    graph = build_router_graph(mode)
    return graph.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "route_trace": [],
            "route": "",
            "route_reason": "",
            "final_output": "",
        }
    )


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["stub", "live"], default="stub")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    args = parser.parse_args(argv)

    result = run_router_example(args.input, args.mode)

    print("Router Pattern Example")
    print(f"Mode: {args.mode}")
    print(f"Route selected: {result['route']}")
    print(f"Reason: {result['route_reason']}")
    print("Trace:")
    for entry in result["route_trace"]:
        print(f"- {entry}")
    print("Final output:")
    print(result["final_output"])

    if args.mode == "stub":
        print("Live mode note: rerun with --mode live and OPENAI_API_KEY to use ChatOpenAI.")


if __name__ == "__main__":
    main()
