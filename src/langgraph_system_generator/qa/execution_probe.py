"""Assertions run inside the kernel against the generated compiled graph."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from langgraph_system_generator.qa.execution_fixtures import RuntimeModel
from langgraph_system_generator.qa.execution_models import ExecutionCase


def plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if value is None or isinstance(value, (str, float, int, bool)):
        return value
    return str(value)


def probe(namespace: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Observe streamed node updates and real thread checkpoints."""
    case = ExecutionCase.model_validate(payload)
    assertions: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = "") -> None:
        assertions.append(
            {"name": name, "passed": bool(passed), "detail": str(detail)[:2000]}
        )

    graph = namespace.get("graph")
    check("compiled_canonical_graph", isinstance(graph, CompiledStateGraph))
    check("interactive_loop_disabled", namespace.get("RUN_INTERACTIVE_LOOP") is False)
    if not isinstance(graph, CompiledStateGraph):
        return {"assertions": assertions, "observations": observations}
    check("real_in_memory_checkpointer", isinstance(graph.checkpointer, InMemorySaver))
    schema = namespace.get("CANONICAL_GRAPH_SPEC", {})
    check("canonical_graph_spec_present", bool(schema))
    expected_names = {node["name"] for node in schema.get("nodes", [])}
    check(
        "compiled_nodes_match_spec",
        expected_names == (set(graph.nodes) - {"__start__"}),
    )
    for invocation in case.invocations:
        RuntimeModel.calls.clear()
        RuntimeModel.fail_worker = "reviewer" if invocation.expected_error else None
        tool_events: list[dict[str, Any]] = []

        class ToolObserver(BaseCallbackHandler):
            def __init__(self, events: list[dict[str, Any]]):
                self.events = events

            def on_tool_start(
                self, serialized: Any, input_str: str, **kwargs: Any
            ) -> None:
                self.events.append(
                    {
                        "name": serialized.get("name"),
                        "arguments": kwargs.get("inputs"),
                        "input": input_str,
                    }
                )

        config: RunnableConfig = {
            "configurable": {"thread_id": invocation.thread_id},
            "recursion_limit": case.max_steps,
            "callbacks": [ToolObserver(tool_events)],
        }
        steps: list[dict[str, Any]] = []
        error: str | None = None
        try:
            for update in graph.stream(
                {"messages": [HumanMessage(content=invocation.text)]},
                config,
                stream_mode="updates",
            ):
                # Keep the partial trace if the next graph step raises.
                steps.append(update)  # noqa: PERF402
        except Exception as exc:  # noqa: BLE001
            error = type(exc).__name__
        finally:
            RuntimeModel.fail_worker = None
        snapshot = graph.get_state(config)
        final = snapshot.values
        nodes = [name for step in steps for name in step]
        prefix = invocation.id + ":"
        if invocation.expected_error:
            check(
                prefix + "declared_failure_policy",
                error == invocation.expected_error,
                error,
            )
            check(
                prefix + "no_false_terminal_on_failure",
                bool(snapshot.next),
                snapshot.next,
            )
        else:
            check(prefix + "no_runtime_error", error is None, error)
            # Same-superstep worker order is unspecified. Membership + exact counts
            # catches unselected branches while preserving parallel semantics.
            check(
                prefix + "executed_nodes",
                sorted(nodes) == sorted(invocation.expected_nodes),
                nodes,
            )
            check(
                prefix + "terminal",
                not snapshot.next if invocation.terminal else bool(snapshot.next),
                snapshot.next,
            )
        check(prefix + "bounded_steps", len(steps) <= case.max_steps, len(steps))
        for key, expected in invocation.expected_state.items():
            check(prefix + "state:" + key, final.get(key) == expected, final.get(key))
        messages = final.get("messages", [])
        history = "\n".join(str(message.content) for message in messages)
        if invocation.retained_text:
            check(
                prefix + "retained_thread_context",
                invocation.retained_text in history,
                history,
            )
        if invocation.absent_text:
            check(
                prefix + "thread_isolation",
                invocation.absent_text not in history,
                history,
            )
        tool_messages = [
            message
            for step in steps
            for update in step.values()
            if isinstance(update, dict)
            for message in update.get("messages", [])
            if isinstance(message, ToolMessage)
        ]
        tool_requests = [
            call
            for step in steps
            for update in step.values()
            if isinstance(update, dict)
            for message in update.get("messages", [])
            for call in getattr(message, "tool_calls", [])
        ]
        check(
            prefix + "actual_tool_executions",
            len(tool_messages) == invocation.expected_tool_calls,
            plain(tool_messages),
        )
        check(
            prefix + "tool_callbacks",
            len(tool_events) == invocation.expected_tool_calls,
            tool_events,
        )
        if invocation.expected_tool_calls:
            check(
                prefix + "tool_arguments",
                [event["arguments"] for event in tool_events] == [{"a": 2, "b": 3}],
                tool_events,
            )
            check(
                prefix + "tool_request",
                [call["args"] for call in tool_requests] == [{"a": 2, "b": 3}],
                tool_requests,
            )
            check(
                prefix + "tool_result",
                [message.content for message in tool_messages] == ["5"],
                plain(tool_messages),
            )
        if case.fixture == "supervisor-v1" and not invocation.expected_error:
            results = final.get("task_results", {})
            check(
                prefix + "reducer_combines_workers",
                results
                == {"researcher": "RESULT:researcher", "reviewer": "RESULT:reviewer"},
                results,
            )
            check(
                prefix + "aggregation_observes_results",
                all(
                    value in final.get("final_output", "") for value in results.values()
                )
                and len(results) == 2,
            )
            worker_calls = [
                call
                for call in RuntimeModel.calls
                if call["input"].startswith(
                    ("You are researcher.", "You are reviewer.")
                )
            ]
            check(
                prefix + "delegated_instructions",
                len(worker_calls) == 2
                and all(
                    "Investigate ticket 42" in call["input"] for call in worker_calls
                ),
            )
            checkpoints = list(graph.get_state_history(config))
            dispatched = [
                task.name
                for item in checkpoints
                for task in item.tasks
                if {task.name for task in item.tasks} == {"researcher", "reviewer"}
            ]
            check(prefix + "same_superstep_fanout", bool(dispatched), dispatched)
        observations.append(
            {
                "invocation": invocation.id,
                "thread_id": invocation.thread_id,
                "updates": plain(steps),
                "nodes": nodes,
                "state": plain(final),
                "pending": list(snapshot.next),
                "error_type": error,
                "tool_events": tool_events,
                "provider_calls": plain(RuntimeModel.calls),
            }
        )
    return {
        "assertions": assertions,
        "observations": observations,
        "canonical_spec": schema,
        "executed": [
            "LangGraph",
            "InMemorySaver",
            "generated node functions",
            "reducers",
            "ToolNode" if case.tool_fixture != "none" else "Send/conditional routing",
        ],
    }


def write_probe(namespace: dict[str, Any], case: dict[str, Any], path: str) -> None:
    """Persist bounded evidence without depending on display formatting."""
    from pathlib import Path

    result = probe(namespace, case)
    encoded = json.dumps(result, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > case["capture_bytes"]:
        raise RuntimeError("Execution evidence capture budget exceeded")
    Path(path).write_text(encoded, encoding="utf-8")
