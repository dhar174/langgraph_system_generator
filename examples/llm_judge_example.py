"""Runnable LLM-as-a-judge reflection example."""

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


class JudgeState(TypedDict, total=False):
    """State for the LLM-as-a-judge example."""

    messages: Annotated[List[BaseMessage], add_messages]
    rubric: Dict[str, int]
    candidate_response: str
    judge_feedback: str
    rubric_scores: Dict[str, int]
    revision_count: int
    revision_notes: Annotated[List[str], operator.add]
    final_output: str


class JudgeAssessment(BaseModel):
    """Structured rubric assessment."""

    factuality: int = Field(ge=1, le=5)
    usefulness: int = Field(ge=1, le=5)
    specificity: int = Field(ge=1, le=5)
    verdict: Literal["revise", "pass"]
    feedback: str


def _stub_candidate(task: str, revision_count: int) -> str:
    if revision_count == 0:
        return f"Candidate answer: {task} can use several agent patterns depending on complexity."
    return (
        f"Candidate answer: {task} should use router for one-shot delegation, supervisor/subagents for sequential collaboration, "
        "and critique/judge loops when answer quality needs explicit rubric gating."
    )


def _stub_assessment(state: JudgeState) -> JudgeAssessment:
    if state.get("revision_count", 0) == 0:
        return JudgeAssessment(
            factuality=4,
            usefulness=3,
            specificity=2,
            verdict="revise",
            feedback="Add concrete pattern-selection guidance and make the answer more specific.",
        )
    return JudgeAssessment(
        factuality=5,
        usefulness=5,
        specificity=5,
        verdict="pass",
        feedback="The answer is specific enough to ship. This shows how rubric-based judging can gate finalization.",
    )


def build_graph(mode: str, model: str):
    """Build the judge/reflection graph."""
    llm = ChatOpenAI(model=model, temperature=0) if mode == "live" else None

    def generate_candidate(state: JudgeState):
        task = state["messages"][0].content if state.get("messages") else ""
        revision_count = state.get("revision_count", 0)
        if llm:
            response = llm.invoke(
                [
                    SystemMessage(content="Draft a concise candidate answer that will later be judged against a rubric."),
                    HumanMessage(content=f"Task: {task}\nRevision count: {revision_count}\nJudge feedback: {state.get('judge_feedback', 'None')}"),
                ]
            )
            candidate = response.content
        else:
            candidate = _stub_candidate(task, revision_count)
        return {
            "candidate_response": candidate,
            "revision_notes": [f"Prepared candidate revision {revision_count + 1}."],
            "messages": [AIMessage(content="Candidate response prepared.")],
        }

    def judge_candidate(state: JudgeState) -> Command[Literal["revise", "finalize"]]:
        if llm:
            assessment = llm.with_structured_output(JudgeAssessment).invoke(
                [
                    SystemMessage(
                        content=(
                            "Judge the answer against a rubric with 1-5 scores for factuality, usefulness, and specificity. "
                            "Return 'pass' only if all scores are at least 4."
                        )
                    ),
                    HumanMessage(content=state.get("candidate_response", "")),
                ]
            )
        else:
            assessment = _stub_assessment(state)

        scores = {
            "factuality": assessment.factuality,
            "usefulness": assessment.usefulness,
            "specificity": assessment.specificity,
        }
        return Command(
            update={
                "judge_feedback": assessment.feedback,
                "rubric_scores": scores,
                "messages": [AIMessage(content=f"Judge verdict: {assessment.verdict}")],
            },
            goto="finalize" if assessment.verdict == "pass" else "revise",
        )

    def revise_candidate(state: JudgeState):
        return {
            "revision_count": state.get("revision_count", 0) + 1,
            "revision_notes": [f"Judge requested a revision: {state.get('judge_feedback', '')}"],
            "messages": [AIMessage(content="Judge feedback routed back into the critique/revise loop.")],
        }

    def finalize(state: JudgeState):
        return {"final_output": state.get("candidate_response", ""), "messages": [AIMessage(content="Judge workflow complete.")]}

    workflow = StateGraph(JudgeState)
    workflow.add_node("generate_candidate", generate_candidate)
    workflow.add_node("judge_candidate", judge_candidate)
    workflow.add_node("revise", revise_candidate)
    workflow.add_node("finalize", finalize)
    workflow.add_edge(START, "generate_candidate")
    workflow.add_edge("generate_candidate", "judge_candidate")
    workflow.add_edge("revise", "generate_candidate")
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=InMemorySaver())


def run_demo(task: str, *, mode: str = "stub", model: str = "gpt-4.1-mini"):
    """Execute the judge/reflection example and print a trace."""
    ensure_live_credentials(mode)
    graph = build_graph(mode, model)
    config = make_thread_config()
    initial_state: JudgeState = {
        "messages": [HumanMessage(content=task)],
        "rubric": {"factuality": 5, "usefulness": 5, "specificity": 5},
        "candidate_response": "",
        "judge_feedback": "",
        "rubric_scores": {},
        "revision_count": 0,
        "revision_notes": [],
        "final_output": "",
    }

    import time

    start = time.perf_counter()
    final_state = {}
    for step in graph.stream(initial_state, config=config, stream_mode="values"):
        trace_step(
            "judge-step",
            {
                "candidate_response": step.get("candidate_response", ""),
                "rubric_scores": step.get("rubric_scores", {}),
                "judge_feedback": step.get("judge_feedback", ""),
                "revision_notes": step.get("revision_notes", []),
            },
        )
        final_state = dict(step)
    trace_step("judge-metrics", build_metrics(model, start).to_dict())
    return final_state


def main() -> None:
    parser = build_example_parser(
        "Run an LLM-as-a-judge example.",
        "Answer when to use router, supervisor, and reflection patterns in LangGraph.",
    )
    args = parser.parse_args()
    result = run_demo(args.task, mode=args.mode, model=args.model)
    print("\nRubric scores:", result.get("rubric_scores", {}))
    print("Final output:\n", result.get("final_output", ""))


if __name__ == "__main__":
    main()
