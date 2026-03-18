"""Runnable critique-revise loop demo using current LangGraph state patterns."""

from __future__ import annotations

import operator
import sys
import time
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

DEFAULT_TASK = "Draft a release announcement for the new critique-revise workflow."
MIN_QUALITY_SCORE = 0.8


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
    """Structured critique output."""

    quality_score: float = Field(ge=0.0, le=1.0)
    approved: bool
    strengths: List[str]
    weaknesses: List[str]
    suggestions: str


def _stub_generate(task: str, revision_count: int, feedback: str) -> str:
    if revision_count == 0:
        return (
            "Release announcement draft:\n"
            f"Product update: {task}\n"
            "Highlights:\n"
            "- Teams can now choose automated or human critique paths.\n"
            "- Review policies are configurable for predictable approval loops.\n"
            "- Updated examples and docs make the pattern easier to adopt."
        )
    return (
        "Revised release announcement:\n"
        f"Product update: {task}\n"
        "Highlights:\n"
        "- Customer value is explicit and the rollout is easy to understand.\n"
        "- Approval criteria are easier to audit across iterations.\n"
        "- The example suite demonstrates both deterministic and live review paths.\n"
        f"Applied revision guidance: {feedback or 'Tighten the customer-facing summary.'}"
    )


def _stub_critique(revision_count: int, draft: str) -> CritiqueAssessment:
    if revision_count == 0:
        return CritiqueAssessment(
            quality_score=0.67,
            approved=False,
            strengths=[
                "The draft identifies the workflow clearly.",
                "The announcement mentions rollout-related benefits.",
            ],
            weaknesses=[
                "Customer impact is still abstract.",
                "The closing sentence is more verbose than needed.",
            ],
            suggestions="Emphasize user value and shorten the final paragraph.",
        )
    return CritiqueAssessment(
        quality_score=0.9,
        approved=True,
        strengths=[
            "The user impact is now explicit.",
            "The structure is concise and easy to scan.",
        ],
        weaknesses=[],
        suggestions="No further revision required.",
    )


def build_graph(
    mode: str,
    model: str,
    *,
    max_revisions: int = 3,
    min_quality_score: float = MIN_QUALITY_SCORE,
):
    """Build the runnable critique-revise graph for the selected mode."""
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def generate_node(state: CritiqueState) -> Dict[str, object]:
        task = state["messages"][0].content if state.get("messages") else ""
        revision_count = state.get("revision_count", 0)
        critique_feedback = state.get("critique_feedback", "")
        if llm:
            response = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "You write concise release announcements with clear product value, "
                            "customer impact, and rollout clarity."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Task: {task}\n\n"
                            f"Revision count: {revision_count}\n"
                            f"Critique feedback: {critique_feedback or 'No critique yet.'}"
                        )
                    ),
                ]
            )
            draft = response.content
        else:
            draft = _stub_generate(task, revision_count, critique_feedback)
        return {
            "current_draft": draft,
            "revision_history": [draft],
            "messages": [
                AIMessage(content=f"Draft revision {revision_count + 1} prepared.")
            ],
        }

    def critique_node(
        state: CritiqueState,
    ) -> Command[Literal["revise", "finalize"]]:
        draft = state.get("current_draft", "")
        revision_count = state.get("revision_count", 0)
        criteria = state.get(
            "criteria",
            [
                "Explain the feature clearly.",
                "Make customer value concrete.",
                "Keep the announcement concise.",
            ],
        )

        assessment = (
            llm.with_structured_output(CritiqueAssessment).invoke(
                [
                    SystemMessage(
                        content=(
                            "You are a release communications reviewer.\n"
                            "Evaluate the draft against:\n"
                            + "\n".join(f"- {criterion}" for criterion in criteria)
                        )
                    ),
                    HumanMessage(content=f"Review this draft:\n\n{draft}"),
                ]
            )
            if llm
            else _stub_critique(revision_count, draft)
        )

        feedback = "\n".join(
            [
                f"Quality Score: {assessment.quality_score}",
                f"Status: {'APPROVED' if assessment.approved else 'NEEDS REVISION'}",
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
            or revision_count >= max_revisions
            or assessment.quality_score >= min_quality_score
        )
        return Command(
            update={
                "critique_feedback": feedback,
                "quality_score": assessment.quality_score,
                "approved": assessment.approved,
                "messages": [AIMessage(content=f"Critique: {feedback}")],
            },
            goto="finalize" if should_finalize else "revise",
        )

    def revise_node(state: CritiqueState) -> Dict[str, object]:
        return {
            "revision_count": state.get("revision_count", 0) + 1,
            "messages": [
                AIMessage(
                    content="Applying critique feedback to prepare the next revision."
                )
            ],
        }

    def finalize_node(state: CritiqueState) -> Dict[str, object]:
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


def run_demo(
    task: str,
    *,
    mode: str = "stub",
    model: str = "gpt-4.1-mini",
    max_steps: int = 3,
) -> Dict[str, object]:
    """Execute the critique example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(mode, model, max_revisions=max_steps)
    config = make_thread_config()
    state: CritiqueState = {
        "messages": [HumanMessage(content=task)],
        "current_draft": "",
        "critique_feedback": "",
        "revision_count": 0,
        "quality_score": 0.0,
        "approved": False,
        "criteria": [
            "Explain the pattern clearly.",
            "Include practical implementation guidance.",
            "Stay concise but concrete.",
        ],
        "revision_history": [],
        "final_output": "",
    }

    start = time.perf_counter()
    final_state: Dict[str, object] = {}
    for step in graph.stream(state, config=config, stream_mode="values"):
        trace_step(
            "critique-step",
            {
                "revision_count": step.get("revision_count"),
                "quality_score": step.get("quality_score"),
                "approved": step.get("approved"),
                "current_draft": step.get("current_draft", ""),
                "final_output": step.get("final_output", ""),
            },
        )
        final_state = dict(step)
    trace_step("critique-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run a critique-revise pattern example.",
        DEFAULT_TASK,
        include_max_steps=True,
    )
    args = parser.parse_args()
    result = run_demo(
        args.task,
        mode=args.mode,
        model=args.model,
        max_steps=args.max_steps,
    )
    print("Critique-Revise Pattern Example")
    print(f"Mode: {args.mode}")
    print("Quality score:", result.get("quality_score"))
    print("Final output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
