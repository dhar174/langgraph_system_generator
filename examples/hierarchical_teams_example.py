"""Runnable hierarchical agent teams example using nested team graphs."""

from __future__ import annotations

import operator
import sys
from pathlib import Path
from typing import Annotated, Dict, List, Literal

from typing_extensions import TypedDict

if __package__ in (None, ""):
    REPO_ROOT = Path(__file__).resolve().parents[1]
    for path in (REPO_ROOT, REPO_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
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


def merge_dicts(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class TeamOfTeamsState(TypedDict, total=False):
    """Top-level shared state for the hierarchical teams example."""

    messages: Annotated[List[BaseMessage], add_messages]
    completed_teams: Annotated[List[str], operator.add]
    team_outputs: Annotated[Dict[str, str], merge_dicts]
    final_output: str


class TeamState(TypedDict, total=False):
    """Internal state for a nested team graph."""

    messages: Annotated[List[BaseMessage], add_messages]
    step: str
    notes: Annotated[List[str], operator.add]
    summary: str


def _build_research_team(mode: str, model: str):
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def lead_node(state: TeamState) -> Command[Literal["researcher"]]:
        return Command(
            update={"notes": ["Research lead framed the information-gathering plan."]},
            goto="researcher",
        )

    def researcher_node(state: TeamState):
        task = state["messages"][0].content if state.get("messages") else ""
        if llm:
            response = llm.invoke([HumanMessage(content=f"Collect concise research notes for: {task}")])
            summary = response.content
        else:
            summary = (
                "Research team summary:\n"
                "- Durable execution and human-in-the-loop remain core LangGraph strengths.\n"
                "- Use nested teams when one supervisor would otherwise accumulate too many responsibilities.\n"
                f"- Research task: {task}"
            )
        return {
            "notes": [summary],
            "summary": summary,
            "messages": [AIMessage(content="Research team finished its brief.")],
        }

    workflow = StateGraph(TeamState)
    workflow.add_node("lead", lead_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_edge(START, "lead")
    workflow.add_edge("researcher", END)
    return workflow.compile(checkpointer=InMemorySaver())


def _build_writing_team(mode: str, model: str):
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def lead_node(state: TeamState) -> Command[Literal["writer"]]:
        return Command(
            update={"notes": ["Writing lead aligned the team on the final deliverable."]},
            goto="writer",
        )

    def writer_node(state: TeamState):
        research_context = state["messages"][0].content if state.get("messages") else ""
        if llm:
            response = llm.invoke([HumanMessage(content=f"Write a concise synthesis from: {research_context}")])
            summary = response.content
        else:
            summary = (
                "Writing team summary:\n"
                "- Create clear boundaries between teams and pass only the context each team needs.\n"
                "- Reserve a top-level supervisor for cross-team sequencing and final synthesis.\n"
                f"- Source context: {research_context}"
            )
        return {
            "notes": [summary],
            "summary": summary,
            "messages": [AIMessage(content="Writing team finished its synthesis.")],
        }

    workflow = StateGraph(TeamState)
    workflow.add_node("lead", lead_node)
    workflow.add_node("writer", writer_node)
    workflow.add_edge(START, "lead")
    workflow.add_edge("writer", END)
    return workflow.compile(checkpointer=InMemorySaver())


def build_graph(mode: str, model: str):
    """Build a top-level supervisor graph that delegates to nested teams."""
    research_team = _build_research_team(mode, model)
    writing_team = _build_writing_team(mode, model)

    def top_supervisor(state: TeamOfTeamsState) -> Command[Literal["research_team", "writing_team", "finalize"]]:
        completed = state.get("completed_teams", [])
        if "research_team" not in completed:
            return Command(goto="research_team")
        if "writing_team" not in completed:
            return Command(goto="writing_team")
        return Command(goto="finalize")

    def research_team_node(state: TeamOfTeamsState):
        substate: TeamState = {
            "messages": [HumanMessage(content=state["messages"][0].content)],
            "notes": [],
        }
        result = research_team.invoke(substate)
        return {
            "completed_teams": ["research_team"],
            "team_outputs": {"research_team": result.get("summary", "")},
            "messages": [AIMessage(content="Top-level supervisor received the research team output.")],
        }

    def writing_team_node(state: TeamOfTeamsState):
        research_summary = state.get("team_outputs", {}).get("research_team", "")
        substate: TeamState = {
            "messages": [HumanMessage(content=research_summary)],
            "notes": [],
        }
        result = writing_team.invoke(substate)
        return {
            "completed_teams": ["writing_team"],
            "team_outputs": {"writing_team": result.get("summary", "")},
            "messages": [AIMessage(content="Top-level supervisor received the writing team output.")],
        }

    def finalize_node(state: TeamOfTeamsState):
        outputs = state.get("team_outputs", {})
        final_output = "\n\n".join(
            [
                "# Hierarchical Teams Summary",
                outputs.get("research_team", ""),
                outputs.get("writing_team", ""),
            ]
        )
        return {"final_output": final_output, "messages": [AIMessage(content="Hierarchical workflow finished.")]}

    workflow = StateGraph(TeamOfTeamsState)
    workflow.add_node("top_supervisor", top_supervisor)
    workflow.add_node("research_team", research_team_node)
    workflow.add_node("writing_team", writing_team_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_edge(START, "top_supervisor")
    workflow.add_edge("research_team", "top_supervisor")
    workflow.add_edge("writing_team", "top_supervisor")
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=InMemorySaver())


def run_demo(task: str, *, mode: str = "stub", model: str = "gpt-4.1-mini"):
    """Execute the hierarchical teams example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(mode, model)
    config = make_thread_config()
    initial_state: TeamOfTeamsState = {
        "messages": [HumanMessage(content=task)],
        "completed_teams": [],
        "team_outputs": {},
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    final_state = {}
    for step in graph.stream(initial_state, config=config, stream_mode="values"):
        trace_step(
            "hierarchical-step",
            {
                "completed_teams": step.get("completed_teams", []),
                "team_outputs": step.get("team_outputs", {}),
                "final_output": step.get("final_output", ""),
            },
        )
        final_state = dict(step)
    trace_step("hierarchical-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run a hierarchical teams example.",
        "Produce a concise explanation of when to use a team-of-teams LangGraph workflow.",
    )
    args = parser.parse_args()
    result = run_demo(args.task, mode=args.mode, model=args.model)
    print("\nFinal output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
