"""Shared helpers for runnable example scripts and notebooks."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

from langchain_core.messages import BaseMessage

DEFAULT_LIVE_MODEL = "gpt-4.1-mini"

# Simple, documented pricing assumptions for examples and benchmark reporting.
PRICE_PER_1K_TOKENS_USD: Dict[str, Dict[str, float]] = {
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    "gpt-5-mini": {"input": 0.00025, "output": 0.0010},
}


@dataclass
class RunMetrics:
    """Basic execution metrics captured by example runs."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_seconds: float = 0.0
    estimated_cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metrics as a plain dictionary."""
        return asdict(self)


def build_example_parser(
    description: str,
    default_task: str,
    *,
    include_max_steps: bool = False,
    include_max_parallel: bool = False,
    include_decision: bool = False,
) -> argparse.ArgumentParser:
    """Create a shared CLI parser for example scripts."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--mode",
        choices=("stub", "live"),
        default="stub",
        help="Use deterministic offline behavior or invoke a live model.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_LIVE_MODEL,
        help="Chat model used when --mode live is selected.",
    )
    parser.add_argument(
        "--task",
        default=default_task,
        help="Task prompt used for the example run.",
    )
    parser.add_argument(
        "--input",
        dest="task",
        help="Alias for --task to keep older example invocations working.",
    )
    if include_max_steps:
        parser.add_argument(
            "--max-steps",
            type=int,
            default=4,
            help="Maximum number of planner or revision steps to allow.",
        )
    if include_max_parallel:
        parser.add_argument(
            "--max-parallel",
            type=int,
            default=2,
            help="Maximum number of tasks to fan out in one scheduling pass.",
        )
    if include_decision:
        parser.add_argument(
            "--decision",
            choices=("approve", "edit", "reject"),
            default="edit",
            help="Human decision to use when auto-resuming HITL examples in stub mode.",
        )
    return parser


def ensure_live_credentials(mode: str) -> None:
    """Exit early when a live run is requested without credentials."""
    if mode == "live" and not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required when running examples in live mode.")


def trace_step(label: str, payload: Any | None = None) -> None:
    """Print a compact trace line for example progress."""
    print(f"[trace] {label}")
    if payload is None:
        return
    if isinstance(payload, (dict, list, tuple)):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(payload)


def message_text(message: BaseMessage | Mapping[str, Any] | str) -> str:
    """Extract readable text from a LangChain message-like object."""
    if isinstance(message, str):
        return message
    if isinstance(message, Mapping):
        content = message.get("content", "")
        return content if isinstance(content, str) else json.dumps(content)
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)


def extract_usage_metadata(value: Any) -> Dict[str, int]:
    """Extract token usage metadata from a LangChain response if present."""
    candidates: Iterable[Any] = (
        getattr(value, "usage_metadata", None),
        getattr(value, "response_metadata", None),
        value if isinstance(value, Mapping) else None,
    )
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        usage = candidate.get("token_usage", candidate)
        if isinstance(usage, Mapping):
            prompt_tokens = int(
                usage.get("prompt_tokens")
                or usage.get("input_tokens")
                or usage.get("prompt_token_count")
                or 0
            )
            completion_tokens = int(
                usage.get("completion_tokens")
                or usage.get("output_tokens")
                or usage.get("completion_token_count")
                or 0
            )
            total_tokens = int(
                usage.get("total_tokens")
                or prompt_tokens + completion_tokens
            )
            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def estimate_cost_usd(model: str, usage: Mapping[str, int]) -> Optional[float]:
    """Estimate token cost from a simple checked-in pricing table."""
    pricing = PRICE_PER_1K_TOKENS_USD.get(model)
    if not pricing:
        return None
    return round(
        (usage.get("prompt_tokens", 0) / 1000.0) * pricing["input"]
        + (usage.get("completion_tokens", 0) / 1000.0) * pricing["output"],
        6,
    )


def build_metrics(model: str, start_time: float, response: Any | None = None) -> RunMetrics:
    """Build a metrics object from runtime information."""
    usage = extract_usage_metadata(response)
    return RunMetrics(
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
        latency_seconds=round(time.perf_counter() - start_time, 4),
        estimated_cost_usd=estimate_cost_usd(model, usage),
    )


def make_thread_config(thread_id: str | None = None) -> Dict[str, Dict[str, str]]:
    """Create a stable thread config for checkpointer-backed examples."""
    return {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}
