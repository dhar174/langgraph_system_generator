"""Compact experimental Deep Agents example.

The module is safe to import without installing ``deepagents``. Run in stub
mode for deterministic offline behavior, or pass ``--mode live`` after
installing ``deepagents`` and configuring model-provider credentials.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Callable, Dict, List


def lookup_topic(topic: str) -> str:
    """Deterministic toy research tool used by both stub and live examples."""

    facts = {
        "deep agents": "Deep Agents add planning, subagents, and filesystem-style context tools.",
        "langgraph": "LangGraph provides durable graph execution for agent workflows.",
    }
    return facts.get(topic.lower(), f"No canned fact is available for {topic!r}.")


def summarize_findings(text: str) -> str:
    """Small deterministic toy synthesis tool."""

    return "Summary: " + text.strip()[:160]


def build_subagents() -> List[Dict[str, Any]]:
    """Return optional dictionary-style Deep Agents subagent specs."""

    return [
        {
            "name": "researcher",
            "description": "Looks up concise background facts.",
            "system_prompt": "Return concise, source-aware research notes.",
            "tools": [lookup_topic],
        },
        {
            "name": "summarizer",
            "description": "Condenses findings for the final answer.",
            "system_prompt": "Return a compact summary and next action.",
            "tools": [summarize_findings],
        },
    ]


def run_stub(task: str) -> Dict[str, Any]:
    """Run a deterministic local version of the example."""

    fact = lookup_topic("deep agents")
    summary = summarize_findings(f"{task}: {fact}")
    return {
        "mode": "stub",
        "task_plan": [
            "Clarify the user request.",
            "Delegate lookup to a researcher subagent.",
            "Summarize the result for the user.",
        ],
        "final_output": summary,
    }


def build_live_agent(model: str, tools: List[Callable[..., str]]):
    """Create the optional live Deep Agents harness lazily."""

    from deepagents import create_deep_agent

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=(
            "You are an experimental Deep Agent. Plan before acting, delegate to "
            "subagents when useful, and keep the final response concise."
        ),
        subagents=build_subagents(),
    )


def run_live(task: str, model: str) -> Dict[str, Any]:
    """Run the live Deep Agents harness if optional dependencies are installed."""

    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "mode": "live-skipped",
            "final_output": "Set OPENAI_API_KEY before running the live Deep Agents example.",
        }

    try:
        agent = build_live_agent(model, tools=[lookup_topic, summarize_findings])
    except ModuleNotFoundError as exc:
        if exc.name == "deepagents":
            return {
                "mode": "live-skipped",
                "final_output": (
                    "Install the optional 'deepagents' package before running "
                    "the live Deep Agents example."
                ),
            }
        raise
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
    return {"mode": "live", "final_output": str(result)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["stub", "live"],
        default="stub",
        help="Use deterministic stub mode by default.",
    )
    parser.add_argument(
        "--task",
        default="Explain where Deep Agents fit in a LangGraph notebook.",
        help="Task sent to the example agent.",
    )
    parser.add_argument(
        "--model",
        default="openai:gpt-5-mini",
        help="Deep Agents model identifier for live mode.",
    )
    args = parser.parse_args()

    result = run_live(args.task, args.model) if args.mode == "live" else run_stub(args.task)
    print(result["final_output"])


if __name__ == "__main__":
    main()
