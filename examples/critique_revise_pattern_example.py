"""Runnable critique-revise loop demo using current LangGraph APIs.

The graph defaults to ``stub`` mode so it can run offline. The same graph can
use ``ChatOpenAI`` in ``live`` mode for real structured critiques.

Examples:
    python examples/critique_revise_pattern_example.py --mode stub
    python examples/critique_revise_pattern_example.py --mode live --input "Draft onboarding docs"
"""

from __future__ import annotations

import argparse
import operator
import os
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

ExampleMode = Literal["stub", "live"]

DEFAULT_INPUT = "Draft a short onboarding guide for a new analytics dashboard."
DEFAULT_MODEL = os.environ.get("LNF_EXAMPLE_MODEL", "gpt-5-mini")
MAX_REVISIONS = 2
MIN_QUALITY_SCORE = 0.85


class CritiqueAssessment(BaseModel):
    """Structured quality review returned by the critique node."""

    quality_score: float = Field(ge=0.0, le=1.0)
    approved: bool
    strengths: list[str]
    improvements: list[str]
    revision_focus: str


class CritiqueState(TypedDict):
    """Shared graph state for the critique/revise example."""

    messages: Annotated[list[AnyMessage], add_messages]
    critique_history: Annotated[list[str], operator.add]
    draft: str
    latest_feedback: str
    quality_score: float
    approved: bool
    revision_count: int
    final_output: str


def _require_live_api_key(mode: ExampleMode) -> None:
    if mode == "live" and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for --mode live.")


def _build_live_model(*, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(model=DEFAULT_MODEL, temperature=temperature)


def _generate_stub_draft(user_input: str, revision_count: int, latest_feedback: str) -> str:
    if revision_count == 0:
        return (
            "Draft guide:\n"
            "1. Connect your data source.\n"
            "2. Open the dashboard home page.\n"
            "3. Review the headline metrics.\n"
            "4. Share a dashboard link with your team."
        )
    return (
        "Revised guide:\n"
        "1. Connect your data source and confirm the sync banner is green.\n"
        "2. Review headline metrics, trends, and anomaly alerts on the home page.\n"
        "3. Save a filtered view for your team and share the dashboard link.\n"
        f"Revision focus applied: {latest_feedback}"
    )


def _generate_live_draft(user_input: str, revision_count: int, latest_feedback: str) -> str:
    model = _build_live_model(temperature=0.3)
    prompt = (
        f"User request:\n{user_input}\n\nCreate a concise, practical draft."
        if revision_count == 0
        else (
            f"User request:\n{user_input}\n\nCurrent feedback:\n{latest_feedback}\n\n"
            "Revise the draft to address the feedback."
        )
    )
    response = model.invoke(
        [
            SystemMessage(
                content="You write concise product documentation that is actionable and easy to skim."
            ),
            HumanMessage(content=prompt),
        ]
    )
    return response.content


def _critique_stub(revision_count: int, draft: str) -> CritiqueAssessment:
    if revision_count == 0:
        return CritiqueAssessment(
            quality_score=0.62,
            approved=False,
            strengths=["Good high-level sequence", "Simple language"],
            improvements=[
                "Add a validation step after connecting data",
                "Explain what to do on the home page",
            ],
            revision_focus="Add clearer verification and expected outcomes for each step.",
        )
    return CritiqueAssessment(
        quality_score=0.91,
        approved=True,
        strengths=["Instructions are more concrete", "Outcome is clearer for each step"],
        improvements=[],
        revision_focus="No further revision required.",
    )


def _critique_live(draft: str) -> CritiqueAssessment:
    model = _build_live_model(temperature=0)
    structured_model = model.with_structured_output(CritiqueAssessment)
    return structured_model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a strict reviewer. Score the draft, decide if it is ready, list strengths, "
                    "list improvements, and suggest a single revision focus."
                )
            ),
            HumanMessage(content=draft),
        ]
    )


def build_critique_graph(mode: ExampleMode = "stub"):
    """Build a runnable critique-revise graph."""

    _require_live_api_key(mode)

    def generate_node(state: CritiqueState):
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        revision_count = state.get("revision_count", 0)
        latest_feedback = state.get("latest_feedback", "")
        draft = (
            _generate_stub_draft(user_input, revision_count, latest_feedback)
            if mode == "stub"
            else _generate_live_draft(user_input, revision_count, latest_feedback)
        )
        label = "Initial draft" if revision_count == 0 else f"Revision {revision_count}"
        return {
            "draft": draft,
            "messages": [AIMessage(content=f"{label} generated.\n{draft}")],
        }

    def critique_node(state: CritiqueState):
        draft = state.get("draft", "")
        revision_count = state.get("revision_count", 0)
        assessment = (
            _critique_stub(revision_count, draft)
            if mode == "stub"
            else _critique_live(draft)
        )
        feedback = (
            f"Score: {assessment.quality_score}\n"
            f"Approved: {assessment.approved}\n"
            f"Strengths: {', '.join(assessment.strengths)}\n"
            f"Improvements: {', '.join(assessment.improvements) or 'None'}\n"
            f"Revision focus: {assessment.revision_focus}"
        )
        return {
            "latest_feedback": feedback,
            "quality_score": assessment.quality_score,
            "approved": assessment.approved,
            "critique_history": [feedback],
            "messages": [AIMessage(content=f"Critique complete.\n{feedback}")],
        }

    def revise_node(state: CritiqueState):
        return {
            "revision_count": state.get("revision_count", 0) + 1,
        }

    def finish_node(state: CritiqueState):
        return {
            "final_output": state.get("draft", ""),
            "messages": [AIMessage(content=f"Workflow complete.\n{state.get('draft', '')}")],
        }

    def should_continue(state: CritiqueState) -> Literal["revise", "finish"]:
        if state.get("approved", False):
            return "finish"
        if state.get("revision_count", 0) >= MAX_REVISIONS:
            return "finish"
        if state.get("quality_score", 0.0) >= MIN_QUALITY_SCORE:
            return "finish"
        return "revise"

    workflow = StateGraph(CritiqueState)
    workflow.add_node("generate", generate_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("revise", revise_node)
    workflow.add_node("finish", finish_node)
    workflow.add_edge(START, "generate")
    workflow.add_edge("generate", "critique")
    workflow.add_conditional_edges(
        "critique",
        should_continue,
        {
            "revise": "revise",
            "finish": "finish",
        },
    )
    workflow.add_edge("revise", "generate")
    workflow.add_edge("finish", END)
    return workflow.compile()


def run_critique_example(
    user_input: str = DEFAULT_INPUT,
    mode: ExampleMode = "stub",
) -> CritiqueState:
    """Execute the critique-revise example and return the final graph state."""

    graph = build_critique_graph(mode)
    return graph.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "critique_history": [],
            "draft": "",
            "latest_feedback": "",
            "quality_score": 0.0,
            "approved": False,
            "revision_count": 0,
            "final_output": "",
        }
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["stub", "live"], default="stub")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    args = parser.parse_args(argv)

    result = run_critique_example(args.input, args.mode)

    print("Critique-Revise Pattern Example")
    print(f"Mode: {args.mode}")
    print(f"Revision count: {result['revision_count']}")
    print(f"Quality score: {result['quality_score']}")
    print(f"Approved: {result['approved']}")
    print("Critique history:")
    for entry in result["critique_history"]:
        print("-")
        print(entry)
    print("Final output:")
    print(result["final_output"])

    if args.mode == "stub":
        print("Live mode note: rerun with --mode live and OPENAI_API_KEY to use ChatOpenAI.")


if __name__ == "__main__":
    main()
