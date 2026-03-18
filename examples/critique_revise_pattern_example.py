"""Runnable critique-revise loop demo using current LangGraph state patterns.

The script defaults to ``stub`` mode so it can run without network access.
Use ``--mode live`` to swap the generation and critique steps onto
``ChatOpenAI``.

Examples:
    python examples/critique_revise_pattern_example.py --mode stub
    python examples/critique_revise_pattern_example.py --mode live --input "Draft onboarding docs"
"""

from __future__ import annotations

import operator
import os
import sys
from pathlib import Path
from typing import Annotated, List, Literal, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

ExampleMode = Literal["stub", "live"]

DEFAULT_INPUT = "Draft a release announcement for the new critique-revise workflow."
DEFAULT_MODEL = os.environ.get("LNF_EXAMPLE_MODEL", "gpt-5-mini")
MAX_REVISIONS = 3
MIN_QUALITY_SCORE = 0.8

def _build_live_model(*, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(model=DEFAULT_MODEL, temperature=temperature)
    
class CritiqueAssessment(BaseModel):
    """Structured critique output for the demo workflow."""

    quality_score: float = Field(ge=0.0, le=1.0)
    approved: bool
    strengths: List[str]
    improvements: List[str]
    revision_focus: str


class CritiqueState(TypedDict):
    """Shared graph state for the critique example."""

    messages: Annotated[list[AnyMessage], add_messages]
    critique_history: Annotated[List[str], operator.add]
    draft: str
    latest_feedback: str
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


def _generate_stub_draft(
    user_input: str,
    revision_count: int,
    latest_feedback: str,
) -> str:
    if revision_count == 0:
        return (
            "Release announcement draft:\n"
            f"Product update: {user_input}\n"
            "Highlights:\n"
            "- Teams can now choose automated or human critique paths.\n"
            "- Failure policies are configurable for tighter review workflows.\n"
            "- Pattern coverage includes deterministic tests and docs."
        )

    return (
        "Revised release announcement:\n"
        f"Product update: {user_input}\n"
        "Highlights:\n"
        "- Teams can now choose automated or human critique paths.\n"
        "- Review failure policies are configurable for predictable exits.\n"
        "- Updated docs and tests make the pattern easier to adopt safely.\n"
        f"Revision guidance applied: {latest_feedback or 'Improve clarity and specificity.'}"
    )


def _generate_live_draft(
    user_input: str,
    revision_count: int,
    latest_feedback: str,
) -> str:
    model = _build_live_model(temperature=0.2)
    revision_context = (
        f"Existing critique feedback:\n{latest_feedback}\n\n"
        if revision_count > 0 and latest_feedback
        else ""
    )
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "You draft concise release announcements with clear product value, "
                    "customer impact, and rollout clarity."
                )
            ),
            HumanMessage(
                content=(
                    f"Prepare a release announcement for:\n{user_input}\n\n"
                    f"{revision_context}"
                    "Keep it structured and customer-facing."
                )
            ),
        ]
    )
    return response.content


def _critique_stub(revision_count: int, draft: str) -> CritiqueAssessment:
    if revision_count == 0:
        return CritiqueAssessment(
            quality_score=0.68,
            approved=False,
            strengths=[
                "Explains the feature at a high level",
                "Names the new review options clearly",
            ],
            improvements=[
                "Make the customer value more concrete",
                "Tighten the rollout summary",
            ],
            revision_focus="Emphasize user impact and simplify the closing sentence.",
        )

    return CritiqueAssessment(
        quality_score=0.87,
        approved=True,
        strengths=[
            "Customer value is explicit",
            "Rollout summary is concise and actionable",
        ],
        improvements=[],
        revision_focus="No further revision needed.",
    )


def _critique_live(draft: str) -> CritiqueAssessment:
    model = _build_live_model(temperature=0)
    structured_model = model.with_structured_output(CritiqueAssessment)
    return structured_model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a release communications reviewer. Score the draft, decide whether "
                    "it is approved, and provide actionable revision guidance."
                )
            ),
            HumanMessage(content=f"Review this draft:\n\n{draft}"),
        ]
    )


def build_critique_graph(mode: ExampleMode = "stub"):
    """Build a runnable critique-revise graph."""

    _require_live_api_key(mode)

    def generate_node(state: CritiqueState):
        task = state["messages"][0].content if state.get("messages") else ""
        revision_count = state.get("revision_count", 0)
        if llm:
            response = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "Write or revise a response so it becomes clear, concrete, "
                            "and implementation-aware."
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
            "messages": [
                AIMessage(content=f"Draft revision {revision_count + 1} prepared.")
            ],
        }

    def critique_node(state: CritiqueState) -> Command:
        draft = state.get("draft", "")
        revision_count = state.get("revision_count", 0)
        assessment = (
            _critique_stub(revision_count, draft)
            if mode == "stub"
            else _critique_live(draft)
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
                        content=(
                            "Critique complete. Finalizing."
                            if should_finalize
                            else "Critique complete. Revising."
                        )
                    )
                ],
            },
            goto="finalize" if should_finalize else "revise",
        )
        if (
            assessment.approved
            or revision_count >= MAX_REVISIONS
            or assessment.quality_score >= MIN_QUALITY_SCORE
        ):
            goto: Literal["finish", "revise"] = "finish"
        else:
            goto = "revise"
        return Command(
            update={
                "latest_feedback": feedback,
                "quality_score": assessment.quality_score,
                "approved": assessment.approved,
                "critique_history": [feedback],
                "messages": [AIMessage(content=f"Critique complete.\n{feedback}")],
            },
            goto=goto,
        )

    def revise_node(state: CritiqueState):
        return {
            "revision_count": state.get("revision_count", 0) + 1,
            "messages": [
                AIMessage(
                    content="Applying critique feedback to prepare the next revision."
                )
            ],
        }

    def finalize_node(state: CritiqueState):
        return {
            "final_output": state.get("current_draft", ""),
            "messages": [AIMessage(content="Final draft approved.")],
        }

    checkpointer = InMemorySaver()
    workflow = StateGraph(CritiqueState)
    workflow.add_node("generate", generate_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("revise", revise_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_edge(START, "generate")
    workflow.add_edge("generate", "critique")
    # critique_node uses Command(goto=...) for routing -- no add_conditional_edges needed
    workflow.add_edge("revise", "generate")
    workflow.add_edge("finish", END)
    return workflow.compile(checkpointer=checkpointer)


def run_demo(
    task: str,
    *,
    mode: str = "stub",
    model: str = "gpt-4.1-mini",
    max_steps: int = 3,
):
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
        },
        config={"configurable": {"thread_id": "example-run"}})
def main() -> None:
    parser = build_example_parser(
        "Run a critique-revise pattern example.",
        "Write a crisp explanation of why reducer-backed state matters in LangGraph.",
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
