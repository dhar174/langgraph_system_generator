"""Runnable human-in-the-loop approval example using LangGraph interrupts."""

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
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

from langgraph_system_generator.examples_support import (
    build_example_parser,
    build_metrics,
    make_thread_config,
    trace_step,
)


class ApprovalState(TypedDict, total=False):
    """State for the approval gate example."""

    messages: Annotated[List[BaseMessage], add_messages]
    proposed_action: str
    action_args: Dict[str, str]
    approval_status: str
    audit_log: Annotated[List[str], operator.add]
    final_output: str


def build_graph():
    """Build the interrupt-driven approval workflow."""

    def draft_action(state: ApprovalState):
        task = state["messages"][0].content if state.get("messages") else "Send an external update."
        action_args = {
            "channel": "customer-success",
            "summary": task,
        }
        return {
            "proposed_action": "send_status_update",
            "action_args": action_args,
            "audit_log": [f"Drafted sensitive action with args: {action_args}"],
            "messages": [AIMessage(content="Sensitive action drafted and waiting for approval.")],
        }

    def approval_gate(state: ApprovalState) -> Command[Literal["execute_action", "finalize"]]:
        payload = {
            "action": state.get("proposed_action"),
            "args": state.get("action_args", {}),
            "instruction": "Approve, edit, or reject this sensitive action before it executes.",
        }
        decision = interrupt(payload)
        decision_type = decision.get("type", "reject")

        if decision_type == "edit":
            edited_args = dict(state.get("action_args", {}))
            edited_args.update(decision.get("args", {}))
            return Command(
                update={
                    "action_args": edited_args,
                    "approval_status": "edited",
                    "audit_log": [f"Human edited the action args: {edited_args}"],
                    "messages": [AIMessage(content="Human edited the action and approved execution.")],
                },
                goto="execute_action",
            )

        if decision_type == "approve":
            return Command(
                update={
                    "approval_status": "approved",
                    "audit_log": ["Human approved the action without edits."],
                    "messages": [AIMessage(content="Human approved the action.")],
                },
                goto="execute_action",
            )

        return Command(
            update={
                "approval_status": "rejected",
                "audit_log": [f"Human rejected the action: {decision.get('reason', 'No reason provided.')}"],
                "final_output": "The sensitive action was rejected and did not run.",
                "messages": [AIMessage(content="Human rejected the action.")],
            },
            goto="finalize",
        )

    def execute_action(state: ApprovalState):
        args = state.get("action_args", {})
        return {
            "audit_log": [f"Executed action {state.get('proposed_action')} with args {args}"],
            "final_output": (
                "Executed sensitive action:\n"
                f"- action: {state.get('proposed_action')}\n"
                f"- channel: {args.get('channel')}\n"
                f"- summary: {args.get('summary')}"
            ),
            "messages": [AIMessage(content="Sensitive action executed.")],
        }

    def finalize(state: ApprovalState):
        if state.get("final_output"):
            return {"messages": [AIMessage(content="Approval workflow finished.")]}
        return {
            "final_output": "Approval workflow finished without executing the action.",
            "messages": [AIMessage(content="Approval workflow finished.")],
        }

    workflow = StateGraph(ApprovalState)
    workflow.add_node("draft_action", draft_action)
    workflow.add_node("approval_gate", approval_gate)
    workflow.add_node("execute_action", execute_action)
    workflow.add_node("finalize", finalize)
    workflow.add_edge(START, "draft_action")
    workflow.add_edge("draft_action", "approval_gate")
    workflow.add_edge("execute_action", "finalize")
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=InMemorySaver())


def _interrupt_payload_from_step(step) -> Dict[str, object] | None:
    if "__interrupt__" in step:
        interrupt_value = step["__interrupt__"][0]
        return getattr(interrupt_value, "value", interrupt_value)
    if "interrupts" in step:
        interrupts = step["interrupts"]
        if interrupts:
            interrupt_value = interrupts[0]
            return getattr(interrupt_value, "value", interrupt_value)
    return None


def _resume_payload(decision: str, task: str) -> Dict[str, object]:
    if decision == "approve":
        return {"type": "approve"}
    if decision == "edit":
        return {
            "type": "edit",
            "args": {
                "summary": f"[Edited by human reviewer] {task}",
            },
        }
    return {"type": "reject", "reason": "Policy requires human rejection for this example path."}


def run_demo(task: str, *, decision: str = "edit"):
    """Execute the approval example and print the interrupt/resume trace."""
    graph = build_graph()
    config = make_thread_config()
    initial_state: ApprovalState = {
        "messages": [HumanMessage(content=task)],
        "audit_log": [],
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    interrupt_payload = None
    for step in graph.stream(initial_state, config=config, stream_mode="values"):
        interrupt_payload = _interrupt_payload_from_step(step)
        if interrupt_payload is not None:
            trace_step("approval-interrupt", interrupt_payload)
        else:
            trace_step("approval-step", {k: step.get(k) for k in ("approval_status", "audit_log", "final_output")})

    resume_payload = _resume_payload(decision, task)
    trace_step("approval-resume", resume_payload)

    final_state = {}
    for step in graph.stream(Command(resume=resume_payload), config=config, stream_mode="values"):
        trace_step(
            "approval-resumed-step",
            {k: step.get(k) for k in ("approval_status", "audit_log", "final_output")},
        )
        final_state = dict(step)

    trace_step("approval-metrics", build_metrics("stub", start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run a human-in-the-loop approval example.",
        "Send a customer-facing status update about a delayed rollout.",
        include_decision=True,
    )
    args = parser.parse_args()
    result = run_demo(args.task, decision=args.decision)
    print("\nApproval status:", result.get("approval_status"))
    print("Final output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
