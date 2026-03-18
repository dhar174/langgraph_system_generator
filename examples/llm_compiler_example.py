"""Runnable LLMCompiler-style dependency-graph execution example."""

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


class CompilerTask(BaseModel):
    """A single dependency-graph task."""

    task_id: str = Field(description="Stable task identifier.")
    objective: str = Field(description="What the task should produce.")
    depends_on: List[str] = Field(default_factory=list, description="Upstream task IDs.")


class CompilerPlan(BaseModel):
    """Structured task graph."""

    tasks: List[CompilerTask]


class CompilerState(TypedDict, total=False):
    """Shared state for the dependency-graph compiler example."""

    messages: Annotated[List[BaseMessage], add_messages]
    task_graph: List[Dict[str, object]]
    ready_queue: List[Dict[str, object]]
    scheduled_tasks: Annotated[List[str], operator.add]
    completed_tasks: Annotated[List[str], operator.add]
    task_results: Annotated[Dict[str, str], merge_dicts]
    execution_log: Annotated[List[str], operator.add]
    final_output: str
    current_task_id: str
    current_task_objective: str


def _stub_plan() -> CompilerPlan:
    return CompilerPlan(
        tasks=[
            CompilerTask(task_id="collect_constraints", objective="Collect the most important implementation constraints."),
            CompilerTask(task_id="collect_examples", objective="Collect the most relevant LangGraph example patterns."),
            CompilerTask(
                task_id="draft_recommendation",
                objective="Draft a final recommendation using the collected constraints and examples.",
                depends_on=["collect_constraints", "collect_examples"],
            ),
        ]
    )


def _stub_task_result(task_id: str) -> str:
    if task_id == "collect_constraints":
        return "Constraints: keep stub mode offline-friendly, expose clear typed state, and preserve docs alignment."
    if task_id == "collect_examples":
        return "Examples: router for one-shot delegation, supervisor for staged collaboration, judge loops for rubric gating."
    return "Recommendation: use dependency-graph execution when independent subtasks can run in parallel before synthesis."


def build_graph(mode: str, model: str, *, max_parallel: int = 2):
    """Build the dependency-graph execution example."""
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def planner_node(state: CompilerState):
        if llm:
            plan = llm.with_structured_output(CompilerPlan).invoke(
                [
                    SystemMessage(
                        content="Create exactly three tasks, allowing at least two to run in parallel before a final synthesis task."
                    ),
                    HumanMessage(content=state["messages"][0].content if state.get("messages") else ""),
                ]
            )
        else:
            plan = _stub_plan()
        return {
            "task_graph": [task.model_dump() for task in plan.tasks],
            "ready_queue": [],
            "execution_log": [f"Planner created {len(plan.tasks)} dependency-graph tasks."],
            "messages": [AIMessage(content="Compiler planner finished.")],
        }

    def scheduler_node(state: CompilerState):
        tasks = state.get("task_graph", [])
        completed = set(state.get("completed_tasks", []))
        scheduled = set(state.get("scheduled_tasks", []))
        ready = []
        for task in tasks:
            task_id = str(task["task_id"])
            dependencies = set(task.get("depends_on", []))
            if task_id in scheduled or task_id in completed:
                continue
            if dependencies.issubset(completed):
                ready.append(task)
        ready = ready[:max_parallel]
        scheduled_ids = [str(task["task_id"]) for task in ready]
        log = (
            [f"Scheduler queued: {', '.join(scheduled_ids)}"]
            if scheduled_ids
            else ["Scheduler found no new ready tasks in this branch."]
        )
        return {
            "ready_queue": ready,
            "scheduled_tasks": scheduled_ids,
            "execution_log": log,
            "messages": [AIMessage(content="Scheduler evaluated task readiness.")],
        }

    def route_ready_tasks(state: CompilerState):
        task_graph = state.get("task_graph", [])
        completed = set(state.get("completed_tasks", []))
        if task_graph and len(completed) >= len(task_graph):
            return "finalize"
        if state.get("ready_queue"):
            return [
                Send(
                    "execute_task",
                    {
                        "messages": state.get("messages", []),
                        "task_graph": state.get("task_graph", []),
                        "scheduled_tasks": state.get("scheduled_tasks", []),
                        "completed_tasks": state.get("completed_tasks", []),
                        "task_results": state.get("task_results", {}),
                        "execution_log": state.get("execution_log", []),
                        "current_task_id": task["task_id"],
                        "current_task_objective": task["objective"],
                    },
                )
                for task in state.get("ready_queue", [])
            ]
        return "wait"

    def execute_task_node(state: CompilerState):
        task_id = state["current_task_id"]
        if llm:
            response = llm.invoke(
                [
                    SystemMessage(content="Execute the assigned dependency-graph task and return a concise result."),
                    HumanMessage(content=state["current_task_objective"]),
                ]
            )
            content = response.content
        else:
            content = _stub_task_result(task_id)
        return {
            "completed_tasks": [task_id],
            "task_results": {task_id: content},
            "execution_log": [f"Executed {task_id}."],
            "messages": [AIMessage(content=f"Task {task_id} complete.")],
        }

    def finalize_node(state: CompilerState):
        lines = ["# LLMCompiler-Style Execution Summary"]
        for task in state.get("task_graph", []):
            task_id = str(task["task_id"])
            lines.append(f"- {task_id}: {state.get('task_results', {}).get(task_id, '')}")
        return {"final_output": "\n".join(lines), "messages": [AIMessage(content="Dependency-graph workflow complete.")]}

    workflow = StateGraph(CompilerState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("scheduler", scheduler_node)
    workflow.add_node("execute_task", execute_task_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "scheduler")
    workflow.add_edge("execute_task", "scheduler")
    workflow.add_conditional_edges(
        "scheduler",
        route_ready_tasks,
        {"finalize": "finalize", "wait": END},
    )
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=InMemorySaver())


def run_demo(task: str, *, mode: str = "stub", model: str = "gpt-4.1-mini", max_parallel: int = 2):
    """Execute the compiler-style example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(mode, model, max_parallel=max_parallel)
    config = make_thread_config()
    initial_state: CompilerState = {
        "messages": [HumanMessage(content=task)],
        "task_graph": [],
        "ready_queue": [],
        "scheduled_tasks": [],
        "completed_tasks": [],
        "task_results": {},
        "execution_log": [],
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    final_state = {}
    for step in graph.stream(initial_state, config=config, stream_mode="values"):
        trace_step(
            "compiler-step",
            {
                "ready_queue": step.get("ready_queue", []),
                "scheduled_tasks": step.get("scheduled_tasks", []),
                "completed_tasks": step.get("completed_tasks", []),
                "task_results": step.get("task_results", {}),
                "execution_log": step.get("execution_log", []),
            },
        )
        final_state = dict(step)
    trace_step("compiler-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run an LLMCompiler-style dependency-graph example.",
        "Compile a short recommendation on when to use dependency-graph execution in LangGraph.",
        include_max_parallel=True,
    )
    args = parser.parse_args()
    result = run_demo(args.task, mode=args.mode, model=args.model, max_parallel=args.max_parallel)
    print("\nExecution log:")
    for entry in result.get("execution_log", []):
        print("-", entry)
    print("\nFinal output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
