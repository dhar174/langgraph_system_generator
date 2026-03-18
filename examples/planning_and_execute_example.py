"""Runnable plan-and-execute example aligned with current LangGraph idioms."""

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


def merge_dicts(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class PlanStep(BaseModel):
    """A single planner-produced step."""

    step_id: str = Field(description="Stable identifier for the step.")
    objective: str = Field(description="What this step should accomplish.")


class ExecutionPlan(BaseModel):
    """Structured plan output from the planner."""

    steps: List[PlanStep]


class PlanExecuteState(TypedDict, total=False):
    """Shared state for the plan/execute workflow."""

    messages: Annotated[List[BaseMessage], add_messages]
    plan_steps: List[Dict[str, str]]
    current_step_index: int
    step_results: Annotated[Dict[str, str], merge_dicts]
    execution_trace: Annotated[List[str], operator.add]
    final_output: str


def _stub_plan(task: str, max_steps: int) -> ExecutionPlan:
    steps = [
        PlanStep(step_id="frame_problem", objective="Frame the task and extract the core question."),
        PlanStep(step_id="collect_evidence", objective="Collect the most important supporting facts."),
        PlanStep(step_id="synthesize_answer", objective="Combine the facts into a final answer."),
    ]
    return ExecutionPlan(steps=steps[:max_steps])


def _stub_step_result(step: PlanStep, task: str) -> str:
    if step.step_id == "frame_problem":
        return f"Framed task: {task}"
    if step.step_id == "collect_evidence":
        return "Collected evidence: Command keeps routing and state updates together; reducers make merges explicit."
    return "Synthesized answer: plan-and-execute is useful when planning and acting benefit from separate prompts."


def build_graph(
    mode: str,
    model: str,
    *,
    planner_model: str | None = None,
    executor_model: str | None = None,
    max_steps: int = 4,
):
    """Build the plan-and-execute graph."""
    planner_model_name = planner_model or model
    executor_model_name = executor_model or model
    planner_llm = (
        ChatOpenAI(model=planner_model_name, temperature=0) if mode == "live" else None
    )
    executor_llm = (
        ChatOpenAI(model=executor_model_name, temperature=0) if mode == "live" else None
    )

    def planner_node(state: PlanExecuteState):
        task = state["messages"][0].content if state.get("messages") else ""
        if planner_llm:
            plan = planner_llm.with_structured_output(ExecutionPlan).invoke(
                [
                    SystemMessage(
                        content=f"Create a concise actionable plan with at most {max_steps} steps."
                    ),
                    HumanMessage(content=f"Task: {task}"),
                ]
            )
        else:
            plan = _stub_plan(task, max_steps)
        return {
            "plan_steps": [step.model_dump() for step in plan.steps],
            "current_step_index": 0,
            "execution_trace": [f"Planner created {len(plan.steps)} steps."],
            "messages": [AIMessage(content="Planner finished.")],
        }

    def orchestrator_node(state: PlanExecuteState) -> Command[Literal["execute_step", "finalize"]]:
        index = state.get("current_step_index", 0)
        steps = state.get("plan_steps", [])
        if index >= len(steps):
            return Command(goto="finalize")
        step = steps[index]
        return Command(
            update={
                "execution_trace": [
                    f"Orchestrator dispatched step {index + 1}: {step['objective']}"
                ]
            },
            goto="execute_step",
        )

    def execute_step_node(state: PlanExecuteState):
        task = state["messages"][0].content if state.get("messages") else ""
        index = state.get("current_step_index", 0)
        step = PlanStep.model_validate(state["plan_steps"][index])
        if executor_llm:
            response = executor_llm.invoke(
                [
                    SystemMessage(content="Execute the planner step and return a concise result."),
                    HumanMessage(content=f"Task: {task}\nStep objective: {step.objective}"),
                ]
            )
            content = response.content
        else:
            content = _stub_step_result(step, task)
        return {
            "step_results": {step.step_id: content},
            "current_step_index": index + 1,
            "execution_trace": [f"Executor completed {step.step_id}."],
            "messages": [AIMessage(content=f"Step {step.step_id} complete.")],
        }

    def finalize_node(state: PlanExecuteState):
        lines = ["# Plan-and-Execute Summary"]
        for step in state.get("plan_steps", []):
            step_id = step["step_id"]
            lines.append(f"- {step_id}: {state.get('step_results', {}).get(step_id, '')}")
        return {"final_output": "\n".join(lines), "messages": [AIMessage(content="Workflow complete.")]}

    workflow = StateGraph(PlanExecuteState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("execute_step", execute_step_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "orchestrator")
    workflow.add_edge("execute_step", "orchestrator")
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=InMemorySaver())


def run_demo(
    task: str,
    *,
    mode: str = "stub",
    model: str = "gpt-4.1-mini",
    planner_model: str | None = None,
    executor_model: str | None = None,
    max_steps: int = 4,
):
    """Execute the plan-and-execute example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(
        mode,
        model,
        planner_model=planner_model,
        executor_model=executor_model,
        max_steps=max_steps,
    )
    config = make_thread_config()
    initial_state: PlanExecuteState = {
        "messages": [HumanMessage(content=task)],
        "plan_steps": [],
        "current_step_index": 0,
        "step_results": {},
        "execution_trace": [],
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    final_state = {}
    for step in graph.stream(initial_state, config=config, stream_mode="values"):
        trace_step(
            "plan-execute-step",
            {
                "current_step_index": step.get("current_step_index"),
                "plan_steps": step.get("plan_steps", []),
                "step_results": step.get("step_results", {}),
                "execution_trace": step.get("execution_trace", []),
            },
        )
        final_state = dict(step)
    trace_step("plan-execute-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run a plan-and-execute example.",
        "Plan and execute a short answer explaining when planner/executor separation helps.",
        include_max_steps=True,
    )
    parser.add_argument(
        "--planner-model",
        help="Optional live-mode override for the planner model. Defaults to --model.",
    )
    parser.add_argument(
        "--executor-model",
        help="Optional live-mode override for the executor model. Defaults to --model.",
    )
    args = parser.parse_args()
    result = run_demo(
        args.task,
        mode=args.mode,
        model=args.model,
        planner_model=args.planner_model,
        executor_model=args.executor_model,
        max_steps=args.max_steps,
    )
    print("\nExecution trace:")
    for entry in result.get("execution_trace", []):
        print("-", entry)
    print("\nFinal output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
