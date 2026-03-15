"""Runnable supervisor/subagents demo using modern LangGraph state patterns.

The script runs in ``stub`` mode by default with deterministic handoffs.
Use ``--mode live`` to swap the supervisor and workers onto ``ChatOpenAI``.

Examples:
    python examples/subagents_pattern_example.py --mode stub
    python examples/subagents_pattern_example.py --mode live --input "Draft a product launch brief"
"""

from __future__ import annotations

import argparse
import operator
import os
from typing import Annotated, List, Literal, Optional

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

ExampleMode = Literal["stub", "live"]
AgentName = Literal["researcher", "writer", "reviewer", "finish"]

DEFAULT_INPUT = "Prepare a concise launch brief for a new AI note-taking product."
DEFAULT_MODEL = os.environ.get("LNF_EXAMPLE_MODEL", "gpt-5-mini")


class SupervisorDecision(BaseModel):
    """Structured routing output for the supervisor."""

    next_agent: AgentName = Field(description="The next worker to run, or finish.")
    instructions: str = Field(description="Concrete instructions for the selected worker.")
    rationale: str = Field(description="Why this worker is the right next step.")


class TeamState(TypedDict):
    """Shared graph state for the supervisor/subagents example."""

    messages: Annotated[list[AnyMessage], add_messages]
    agent_history: Annotated[list[str], operator.add]
    artifacts: dict[str, str]
    active_agent: str
    supervisor_instructions: str
    final_output: str


def _require_live_api_key(mode: ExampleMode) -> None:
    if mode == "live" and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for --mode live.")


def _build_live_model(*, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(model=DEFAULT_MODEL, temperature=temperature)


def _supervisor_stub(user_input: str, artifacts: dict[str, str]) -> SupervisorDecision:
    if "researcher" not in artifacts:
        return SupervisorDecision(
            next_agent="researcher",
            instructions=f"Find the strongest positioning points for: {user_input}",
            rationale="Research should happen before drafting.",
        )
    if "writer" not in artifacts:
        return SupervisorDecision(
            next_agent="writer",
            instructions="Turn the research notes into a tight launch brief with headline, proof points, and CTA.",
            rationale="The team has enough source material to draft.",
        )
    if "reviewer" not in artifacts:
        return SupervisorDecision(
            next_agent="reviewer",
            instructions="Polish the brief, tighten phrasing, and call out any missing evidence.",
            rationale="A final review should improve clarity before delivery.",
        )
    return SupervisorDecision(
        next_agent="finish",
        instructions="Deliver the reviewed brief to the user.",
        rationale="All specialist steps are complete.",
    )


def _supervisor_live(user_input: str, artifacts: dict[str, str]) -> SupervisorDecision:
    artifact_summary = "\n".join(
        f"- {name}: {value[:200]}" for name, value in artifacts.items()
    ) or "No worker artifacts yet."
    model = _build_live_model(temperature=0)
    structured_model = model.with_structured_output(SupervisorDecision)
    return structured_model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a supervisor coordinating three stateless workers: researcher, writer, "
                    "reviewer. Choose the next agent or finish."
                )
            ),
            HumanMessage(
                content=(
                    f"User request:\n{user_input}\n\nExisting artifacts:\n{artifact_summary}\n\n"
                    "Select the next agent and provide focused instructions."
                )
            ),
        ]
    )


def _research_output(mode: ExampleMode, user_input: str, instructions: str) -> str:
    if mode == "stub":
        return (
            "Research notes:\n"
            "- Core audience: knowledge workers who juggle scattered notes.\n"
            "- Strong hook: AI turns messy notes into next actions.\n"
            "- Proof point: faster meeting follow-up and easier retrieval."
        )

    model = _build_live_model(temperature=0.2)
    response = model.invoke(
        [
            SystemMessage(
                content="You are a researcher. Return concise source notes that help a writer draft fast."
            ),
            HumanMessage(content=f"Task: {user_input}\nInstructions: {instructions}"),
        ]
    )
    return response.content


def _writer_output(
    mode: ExampleMode,
    user_input: str,
    instructions: str,
    artifacts: dict[str, str],
) -> str:
    if mode == "stub":
        research = artifacts.get("researcher", "No research notes available.")
        return (
            "Launch brief draft:\n"
            "Headline: Notes that turn into action.\n"
            f"Support:\n{research}\n"
            "CTA: Start with one meeting and get a structured recap in minutes."
        )

    model = _build_live_model(temperature=0.3)
    response = model.invoke(
        [
            SystemMessage(
                content="You are a product writer. Draft a polished launch brief using the research artifact."
            ),
            HumanMessage(
                content=(
                    f"Task: {user_input}\nInstructions: {instructions}\n\n"
                    f"Research artifact:\n{artifacts.get('researcher', '')}"
                )
            ),
        ]
    )
    return response.content


def _reviewer_output(
    mode: ExampleMode,
    user_input: str,
    instructions: str,
    artifacts: dict[str, str],
) -> str:
    if mode == "stub":
        writer_artifact = artifacts.get("writer", "No draft available.")
        return (
            "Reviewed launch brief:\n"
            f"{writer_artifact}\n"
            "Reviewer note: tighten the proof point and keep the CTA action-oriented."
        )

    model = _build_live_model(temperature=0.2)
    response = model.invoke(
        [
            SystemMessage(
                content="You are an editorial reviewer. Improve clarity, tighten claims, and flag weak evidence."
            ),
            HumanMessage(
                content=(
                    f"Task: {user_input}\nInstructions: {instructions}\n\n"
                    f"Draft artifact:\n{artifacts.get('writer', '')}"
                )
            ),
        ]
    )
    return response.content


def build_subagents_graph(mode: ExampleMode = "stub"):
    """Build a runnable supervisor/subagents graph."""

    _require_live_api_key(mode)

    def supervisor_node(
        state: TeamState,
    ) -> Command[Literal["researcher", "writer", "reviewer", "finish"]]:
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        artifacts = dict(state.get("artifacts", {}))
        decision = (
            _supervisor_stub(user_input, artifacts)
            if mode == "stub"
            else _supervisor_live(user_input, artifacts)
        )

        return Command(
            update={
                "active_agent": decision.next_agent,
                "supervisor_instructions": decision.instructions,
                "agent_history": [f"supervisor->{decision.next_agent}"],
                "messages": [
                    AIMessage(
                        content=(
                            f"Supervisor selected {decision.next_agent}: "
                            f"{decision.instructions} ({decision.rationale})"
                        )
                    )
                ],
            },
            goto=decision.next_agent,
        )

    def researcher_node(state: TeamState):
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        artifact = _research_output(mode, user_input, state.get("supervisor_instructions", ""))
        artifacts = dict(state.get("artifacts", {}))
        artifacts["researcher"] = artifact
        return {
            "artifacts": artifacts,
            "agent_history": ["researcher"],
            "messages": [AIMessage(content=artifact)],
        }

    def writer_node(state: TeamState):
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        artifact = _writer_output(
            mode,
            user_input,
            state.get("supervisor_instructions", ""),
            dict(state.get("artifacts", {})),
        )
        artifacts = dict(state.get("artifacts", {}))
        artifacts["writer"] = artifact
        return {
            "artifacts": artifacts,
            "agent_history": ["writer"],
            "messages": [AIMessage(content=artifact)],
        }

    def reviewer_node(state: TeamState):
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        artifact = _reviewer_output(
            mode,
            user_input,
            state.get("supervisor_instructions", ""),
            dict(state.get("artifacts", {})),
        )
        artifacts = dict(state.get("artifacts", {}))
        artifacts["reviewer"] = artifact
        return {
            "artifacts": artifacts,
            "agent_history": ["reviewer"],
            "messages": [AIMessage(content=artifact)],
        }

    def finish_node(state: TeamState):
        final_output = (
            state.get("artifacts", {}).get("reviewer")
            or state.get("artifacts", {}).get("writer")
            or state.get("artifacts", {}).get("researcher")
            or "No artifact generated."
        )
        return {
            "final_output": final_output,
            "agent_history": ["finish"],
            "messages": [AIMessage(content=f"Final deliverable ready.\n{final_output}")],
        }

    workflow = StateGraph(TeamState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("finish", finish_node)
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("researcher", "supervisor")
    workflow.add_edge("writer", "supervisor")
    workflow.add_edge("reviewer", "supervisor")
    workflow.add_edge("finish", END)
    return workflow.compile()


def run_subagents_example(
    user_input: str = DEFAULT_INPUT,
    mode: ExampleMode = "stub",
) -> TeamState:
    """Execute the supervisor/subagents example and return the final state."""

    graph = build_subagents_graph(mode)
    return graph.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "agent_history": [],
            "artifacts": {},
            "active_agent": "",
            "supervisor_instructions": "",
            "final_output": "",
        }
    )


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["stub", "live"], default="stub")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    args = parser.parse_args(argv)

    result = run_subagents_example(args.input, args.mode)

    print("Subagents Pattern Example")
    print(f"Mode: {args.mode}")
    print("Agent history:")
    for entry in result["agent_history"]:
        print(f"- {entry}")
    print("Artifacts generated:")
    for name in result["artifacts"]:
        print(f"- {name}")
    print("Final output:")
    print(result["final_output"])

    if args.mode == "stub":
        print("Live mode note: rerun with --mode live and OPENAI_API_KEY to use ChatOpenAI.")


if __name__ == "__main__":
    main()
