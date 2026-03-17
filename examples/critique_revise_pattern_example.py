"""Runnable critique-revise example aligned with current LangGraph idioms."""

from __future__ import annotations

import operator
import sys
from pathlib import Path
from typing import Annotated, List, Literal

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


class CritiqueState(TypedDict, total=False):
    """State for the critique-revise example."""

    messages: Annotated[List[BaseMessage], add_messages]
    current_draft: str
    critique_feedback: str
    revision_count: int
    quality_score: float
    approved: bool
    criteria: List[str]
    revision_history: Annotated[List[str], operator.add]
    final_output: str


class CritiqueAssessment(BaseModel):
    """Structured rubric assessment."""

    quality_score: float = Field(ge=0.0, le=1.0)
    approved: bool
    strengths: List[str]
    weaknesses: List[str]
    suggestions: str


def _stub_generate(task: str, revision_count: int) -> str:
    if revision_count == 0:
        return (
            "Draft v1:\n"
            "- LangGraph helps build stateful agent workflows.\n"
            "- Supervisors can coordinate specialists.\n"
            "- More detail still needed."
        )
    return (
        "Draft v2:\n"
        "- LangGraph enables durable, stateful workflows with explicit control flow.\n"
        "- Command keeps routing decisions colocated with state updates.\n"
        "- Reducers make shared-state merges predictable across branches.\n"
        f"- Example task addressed: {task}"
    )


def _stub_assessment(state: CritiqueState) -> CritiqueAssessment:
    if state.get("revision_count", 0) == 0:
        return CritiqueAssessment(
            quality_score=0.62,
            approved=False,
            strengths=["The draft names the core framework and supervision idea."],
            weaknesses=["It lacks explanation of why the patterns matter.", "There are no concrete implementation details."],
            suggestions="Add practical guidance on Command, reducers, and when to choose this pattern.",
        )
    return CritiqueAssessment(
        quality_score=0.91,
        approved=True,
        strengths=["The revision explains why Command and reducers matter.", "The draft now ties recommendations to a concrete task."],
        weaknesses=["Minor room remains for extra examples."],
        suggestions="Optionally add one more concrete example, but the draft is ready.",
    )


def build_graph(mode: str, model: str, *, max_revisions: int = 3, min_quality_score: float = 0.85):
    """Build the runnable critique-revise graph."""
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def generate_node(state: CritiqueState):
        task = state["messages"][0].content if state.get("messages") else ""
        revision_count = state.get("revision_count", 0)
        if llm:
            response = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "Write or revise a response so it becomes clear, concrete, and implementation-aware."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Task: {task}\n\n"
                            f"Revision count: {revision_count}\n"
                            f"Feedback: {state.get('critique_feedback', 'No critique yet.')}"
                        )
                    ),
                ]
            )
            draft = response.content
        else:
            draft = _stub_generate(task, revision_count)
        return {
            "current_draft": draft,
            "revision_history": [draft],
            "messages": [AIMessage(content=f"Draft revision {revision_count + 1} prepared.")],
        }

    def critique_node(state: CritiqueState) -> Command[Literal["revise", "finalize"]]:
        if llm:
            criteria = "\n".join(f"- {item}" for item in state.get("criteria", []))
            assessment = llm.with_structured_output(CritiqueAssessment).invoke(
                [
                    SystemMessage(
                        content=(
                            "Review the draft using the rubric below.\n"
                            f"{criteria}"
                        )
                    ),
                    HumanMessage(content=f"Draft:\n\n{state.get('current_draft', '')}"),
                ]
            )
        else:
            assessment = _stub_assessment(state)
        feedback = "\n".join(
            [
                f"Quality score: {assessment.quality_score:.2f}",
                "Strengths:",
                *[f"- {item}" for item in assessment.strengths],
                "Weaknesses:",
                *[f"- {item}" for item in assessment.weaknesses],
                "Suggestions:",
                assessment.suggestions,
            ]
        )
        should_finalize = (
            assessment.approved
            or state.get("revision_count", 0) >= max_revisions
            or assessment.quality_score >= min_quality_score
        )
        return Command(
            update={
                "critique_feedback": feedback,
                "quality_score": assessment.quality_score,
                "approved": assessment.approved,
                "messages": [
                    AIMessage(
                        content="Critique complete. Finalizing." if should_finalize else "Critique complete. Revising."
                    )
                ],
            },
            goto="finalize" if should_finalize else "revise",
        )

    def revise_node(state: CritiqueState):
        return {
            "revision_count": state.get("revision_count", 0) + 1,
            "messages": [AIMessage(content="Applying critique feedback to prepare the next revision.")],
        }

    def finalize_node(state: CritiqueState):
        return {
            "final_output": state.get("current_draft", ""),
            "messages": [AIMessage(content="Final draft approved.")],
        }

    workflow = StateGraph(CritiqueState)
    workflow.add_node("generate", generate_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("revise", revise_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_edge(START, "generate")
    workflow.add_edge("generate", "critique")
    workflow.add_edge("revise", "generate")
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=InMemorySaver())


def run_demo(task: str, *, mode: str = "stub", model: str = "gpt-4.1-mini", max_steps: int = 3):
    """Execute the critique-revise example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(mode, model, max_revisions=max_steps)
    config = make_thread_config()
    initial_state: CritiqueState = {
        "messages": [HumanMessage(content=task)],
        "criteria": [
            "Explain the pattern clearly.",
            "Include practical implementation guidance.",
            "Stay concise but concrete.",
        ],
        "revision_count": 0,
        "revision_history": [],
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    final_state = {}
    for step in graph.stream(initial_state, config=config, stream_mode="values"):
        trace_step(
            "critique-step",
            {
                "revision_count": step.get("revision_count"),
                "quality_score": step.get("quality_score"),
                "approved": step.get("approved"),
                "current_draft": step.get("current_draft", ""),
            },
        )
        final_state = dict(step)
    trace_step("critique-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run a critique-revise pattern example.",
        "Write a crisp explanation of why reducer-backed state matters in LangGraph.",
        include_max_steps=True,
    )
    args = parser.parse_args()
    result = run_demo(args.task, mode=args.mode, model=args.model, max_steps=args.max_steps)
    print("\nQuality score:", result.get("quality_score"))
    print("Final output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
