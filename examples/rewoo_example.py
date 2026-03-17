"""Runnable REWOO-style speculative reasoning example."""

from __future__ import annotations

import operator
import sys
from pathlib import Path
from typing import Annotated, Dict, List

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
from langgraph.types import Send

from langgraph_system_generator.examples_support import (
    build_example_parser,
    build_metrics,
    ensure_live_credentials,
    make_thread_config,
    trace_step,
)


def merge_dicts(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class SpeculativeCall(BaseModel):
    """A predicted tool invocation."""

    call_id: str = Field(description="Stable identifier for the speculative call.")
    tool_name: str = Field(description="Name of the tool to run.")
    query: str = Field(description="Tool input.")
    predicted_output: str = Field(description="Predicted result before observation.")


class SpeculativePlan(BaseModel):
    """Structured speculative plan."""

    calls: List[SpeculativeCall]


class RewooState(TypedDict, total=False):
    """Shared state for the REWOO example."""

    messages: Annotated[List[BaseMessage], add_messages]
    speculative_plan: List[Dict[str, str]]
    predicted_results: Annotated[Dict[str, str], merge_dicts]
    observed_results: Annotated[Dict[str, str], merge_dicts]
    divergences: Annotated[List[str], operator.add]
    final_output: str


def _stub_plan(task: str) -> SpeculativePlan:
    return SpeculativePlan(
        calls=[
            SpeculativeCall(
                call_id="docs_lookup",
                tool_name="search_docs",
                query=f"LangGraph Command usage for: {task}",
                predicted_output="Predicted docs result: Command is preferred for dynamic control flow.",
            ),
            SpeculativeCall(
                call_id="pattern_lookup",
                tool_name="search_patterns",
                query=f"Pattern comparison for: {task}",
                predicted_output="Predicted pattern result: router and supervisor are the most relevant patterns.",
            ),
        ]
    )


def _stub_tool(call_id: str, query: str) -> str:
    if call_id == "docs_lookup":
        return (
            "Observed docs result: Command combines state updates and routing in one node.\n"
            f"Query: {query}"
        )
    return (
        "Observed pattern result: choose router for one-shot delegation, supervisor for sequential collaboration.\n"
        f"Query: {query}"
    )


def build_graph(mode: str, model: str):
    """Build the speculative reasoning graph."""
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def planner_node(state: RewooState):
        task = state["messages"][0].content if state.get("messages") else ""
        if llm:
            plan = llm.with_structured_output(SpeculativePlan).invoke(
                [
                    SystemMessage(
                        content=(
                            "Create exactly two speculative tool calls. Predict likely outputs so the workflow can reason ahead."
                        )
                    ),
                    HumanMessage(content=f"Task: {task}"),
                ]
            )
        else:
            plan = _stub_plan(task)
        return {
            "speculative_plan": [call.model_dump() for call in plan.calls],
            "predicted_results": {call.call_id: call.predicted_output for call in plan.calls},
            "messages": [AIMessage(content="Planner predicted tool outputs and queued speculative calls.")],
        }

    def dispatch_speculative_calls(state: RewooState):
        sends = []
        for call in state.get("speculative_plan", []):
            sends.append(
                Send(
                    "execute_tool",
                    {
                        "speculative_plan": state.get("speculative_plan", []),
                        "messages": state.get("messages", []),
                        "predicted_results": state.get("predicted_results", {}),
                        "call_id": call["call_id"],
                        "tool_name": call["tool_name"],
                        "query": call["query"],
                    },
                )
            )
        return sends

    def execute_tool_node(state: RewooState):
        call_id = state["call_id"]
        query = state["query"]
        if llm:
            response = llm.invoke(
                [
                    SystemMessage(content=f"Simulate the tool {state['tool_name']} and provide an observed result."),
                    HumanMessage(content=query),
                ]
            )
            observed = response.content
        else:
            observed = _stub_tool(call_id, query)
        return {
            "observed_results": {call_id: observed},
            "messages": [AIMessage(content=f"Observed result captured for {call_id}.")],
        }

    def reconcile_node(state: RewooState):
        plan = state.get("speculative_plan", [])
        observed = state.get("observed_results", {})
        if len(observed) < len(plan):
            return {
                "messages": [AIMessage(content="Waiting for remaining speculative calls to finish.")],
            }

        divergences = []
        lines = ["# REWOO Reconciliation"]
        for call in plan:
            predicted = state.get("predicted_results", {}).get(call["call_id"], "")
            actual = observed.get(call["call_id"], "")
            if predicted.strip() != actual.strip():
                divergences.append(f"{call['call_id']}: prediction differed from observation.")
            lines.append(f"## {call['call_id']}")
            lines.append(f"Predicted: {predicted}")
            lines.append(f"Observed: {actual}")
        if divergences:
            lines.append("## Divergences")
            lines.extend(f"- {item}" for item in divergences)
        return {
            "divergences": divergences,
            "final_output": "\n".join(lines),
            "messages": [AIMessage(content="Reconciliation complete.")],
        }

    workflow = StateGraph(RewooState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("execute_tool", execute_tool_node)
    workflow.add_node("reconcile", reconcile_node)
    workflow.add_edge(START, "planner")
    workflow.add_conditional_edges("planner", dispatch_speculative_calls, ["execute_tool"])
    workflow.add_edge("execute_tool", "reconcile")
    workflow.add_edge("reconcile", END)
    return workflow.compile(checkpointer=InMemorySaver())


def run_demo(task: str, *, mode: str = "stub", model: str = "gpt-4.1-mini"):
    """Execute the REWOO example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(mode, model)
    config = make_thread_config()
    initial_state: RewooState = {
        "messages": [HumanMessage(content=task)],
        "speculative_plan": [],
        "predicted_results": {},
        "observed_results": {},
        "divergences": [],
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    final_state = {}
    for step in graph.stream(initial_state, config=config, stream_mode="values"):
        trace_step(
            "rewoo-step",
            {
                "speculative_plan": step.get("speculative_plan", []),
                "predicted_results": step.get("predicted_results", {}),
                "observed_results": step.get("observed_results", {}),
                "divergences": step.get("divergences", []),
            },
        )
        final_state = dict(step)
    trace_step("rewoo-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run a REWOO-style speculative reasoning example.",
        "Speculate on the best pattern for a multi-agent workflow and then reconcile with observed tool outputs.",
    )
    args = parser.parse_args()
    result = run_demo(args.task, mode=args.mode, model=args.model)
    print("\nFinal output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
