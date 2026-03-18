"""Runnable supervisor/subagents example aligned with current LangGraph idioms."""

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

AGENTS = ("researcher", "analyst", "writer")


def merge_dicts(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    """Merge subagent outputs into a shared mapping."""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class TeamState(TypedDict, total=False):
    """Shared supervisor/subagent state."""

    messages: Annotated[List[BaseMessage], add_messages]
    next_agent: str
    instructions: str
    iterations: int
    dispatch_log: Annotated[List[str], operator.add]
    task_results: Annotated[Dict[str, str], merge_dicts]
    final_output: str


class SupervisorDecision(BaseModel):
    """Typed supervisor decision."""

    next_agent: Literal["researcher", "analyst", "writer", "FINISH"] = Field(
        description="Which specialist should act next."
    )
    instructions: str = Field(description="Specific instructions for the specialist.")
    reasoning: str = Field(description="Why this next step is useful.")


def _stub_supervisor(state: TeamState) -> SupervisorDecision:
    results = state.get("task_results", {})
    if "researcher" not in results:
        return SupervisorDecision(
            next_agent="researcher",
            instructions="Gather the most relevant facts and sources for the request.",
            reasoning="The team needs raw facts before analysis.",
        )
    if "analyst" not in results:
        return SupervisorDecision(
            next_agent="analyst",
            instructions="Turn the research findings into concrete insights and trade-offs.",
            reasoning="The team now has enough evidence to analyze.",
        )
    if "writer" not in results:
        return SupervisorDecision(
            next_agent="writer",
            instructions="Synthesize the research and analysis into a polished final brief.",
            reasoning="All prerequisite inputs are ready for final synthesis.",
        )
    return SupervisorDecision(
        next_agent="FINISH",
        instructions="Combine the specialist outputs into the final answer.",
        reasoning="The team has completed all planned stages.",
    )


def _stub_agent_output(agent: str, task: str, state: TeamState) -> str:
    if agent == "researcher":
        return (
            "Research notes:\n"
            "- LangGraph v1 docs keep graph primitives stable while improving ergonomics.\n"
            "- Command centralizes state updates and control flow.\n"
            f"- Source task: {task}"
        )
    if agent == "analyst":
        return (
            "Analysis:\n"
            "- Router is ideal for one-shot delegation.\n"
            "- Supervisor/subagents work better when task decomposition depends on prior outputs.\n"
            f"- Available context keys: {', '.join(sorted(state.get('task_results', {})))}"
        )
    return (
        "Final brief:\n"
        "- Start with a supervisor when you need sequential collaboration.\n"
        "- Keep specialist responsibilities non-overlapping and pass forward only needed state.\n"
        f"- Original task: {task}"
    )


def build_graph(mode: str, model: str, *, max_iterations: int = 4):
    """Build the runnable supervisor/subagents graph."""
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def supervisor_node(
        state: TeamState,
    ) -> Command[Literal["researcher", "analyst", "writer", "finish"]]:
        iterations = state.get("iterations", 0)
        if iterations >= max_iterations:
            return Command(
                update={
                    "next_agent": "FINISH",
                    "instructions": "Maximum iterations reached; synthesize current work.",
                    "dispatch_log": ["Supervisor stopped at max_iterations."],
                },
                goto="finish",
            )

        if llm:
            summary = "\n".join(
                f"- {agent}: {output[:160]}"
                for agent, output in state.get("task_results", {}).items()
            ) or "No results yet."
            decision = llm.with_structured_output(SupervisorDecision).invoke(
                [
                    SystemMessage(
                        content=(
                            "You supervise a specialist team.\n"
                            "- researcher: gather evidence\n"
                            "- analyst: interpret findings\n"
                            "- writer: produce the final brief\n"
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Task: {state['messages'][0].content if state.get('messages') else ''}\n\n"
                            f"Current results:\n{summary}"
                        )
                    ),
                ]
            )
        else:
            decision = _stub_supervisor(state)

        target = "finish" if decision.next_agent == "FINISH" else decision.next_agent
        return Command(
            update={
                "next_agent": decision.next_agent,
                "instructions": decision.instructions,
                "iterations": iterations + (
                    0 if decision.next_agent == "FINISH" else 1
                ),
                "dispatch_log": [
                    f"Supervisor -> {decision.next_agent}: {decision.reasoning}"
                ],
                "messages": [
                    AIMessage(
                        content=(
                            f"Supervisor selected {decision.next_agent}: "
                            f"{decision.instructions}"
                        )
                    )
                ],
            },
            goto=target,
        )

    def specialist_node(agent: str, role: str):
        def _node(state: TeamState) -> Dict[str, object]:
            task = state["messages"][0].content if state.get("messages") else ""
            if llm:
                response = llm.invoke(
                    [
                        SystemMessage(content=f"You are the {agent}. Role: {role}"),
                        HumanMessage(
                            content=f"Instructions: {state.get('instructions', '')}"
                        ),
                        *state.get("messages", []),
                    ]
                )
                content = response.content
            else:
                content = _stub_agent_output(agent, task, state)
            return {
                "task_results": {agent: content},
                "messages": [AIMessage(content=f"{agent} completed the task.")],
            }

        return _node

    def finish_node(state: TeamState) -> Dict[str, object]:
        results = state.get("task_results", {})
        final_output = "\n\n".join(
            f"## {agent.title()}\n{output}" for agent, output in results.items()
        )
        return {
            "final_output": final_output,
            "messages": [AIMessage(content="Team finished.")],
        }

    workflow = StateGraph(TeamState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node(
        "researcher",
        specialist_node("researcher", "Gather facts and context."),
    )
    workflow.add_node(
        "analyst",
        specialist_node("analyst", "Interpret the findings."),
    )
    workflow.add_node(
        "writer",
        specialist_node("writer", "Produce the final answer."),
    )
    workflow.add_node("finish", finish_node)
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("researcher", "supervisor")
    workflow.add_edge("analyst", "supervisor")
    workflow.add_edge("writer", "supervisor")
    workflow.add_edge("finish", END)
    return workflow.compile(checkpointer=InMemorySaver())


def run_demo(
    task: str,
    *,
    mode: str = "stub",
    model: str = "gpt-4.1-mini",
) -> Dict[str, object]:
    """Execute the supervisor example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(mode, model)
    config = make_thread_config()
    initial_state: TeamState = {
        "messages": [HumanMessage(content=task)],
        "task_results": {},
        "dispatch_log": [],
        "iterations": 0,
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    final_state: Dict[str, object] = {}
    for step in graph.stream(initial_state, config=config, stream_mode="values"):
        trace_step(
            "subagents-step",
            {
                "next_agent": step.get("next_agent"),
                "dispatch_log": step.get("dispatch_log", []),
                "task_results": step.get("task_results", {}),
                "final_output": step.get("final_output", ""),
            },
        )
        final_state = dict(step)
    trace_step("subagents-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run a supervisor/subagents example.",
        "Prepare a short best-practices brief on when to use multi-agent supervision.",
    )
    args = parser.parse_args()
    result = run_demo(args.task, mode=args.mode, model=args.model)
    print("Subagents Pattern Example")
    print(f"Mode: {args.mode}")
    print("Agent history:")
    for entry in result.get("dispatch_log", []):
        print("-", entry)
    print("\nDispatch log:")
    for entry in result.get("dispatch_log", []):
        print("-", entry)
    print("\nFinal output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
