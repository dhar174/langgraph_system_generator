"""Repository-controlled fake provider responses; real generator and graph code."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from contextlib import ExitStack
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, ToolMessage

from langgraph_system_generator.qa.execution_models import ExecutionCase

TOOL_SOURCE = '''from langchain_core.tools import tool

@tool
def calculator(a: int, b: int) -> int:
    """Add two integers deterministically without external services."""
    return a + b
'''


def _async_fixture_node(
    collaborator: AsyncMock,
) -> Callable[[Any], Awaitable[dict[str, Any]]]:
    """Expose a real coroutine signature to LangGraph on Python 3.10 too."""

    async def node(state: Any) -> dict[str, Any]:
        return await collaborator(state)

    return node


def graph_response(case: ExecutionCase) -> dict[str, Any]:
    """Model output fed through GraphDesigner validation and canonical export."""
    common: dict[str, Any] = {
        "state_schema": {"messages": "Conversation messages"},
        "domain_terms": ["support"],
        "checkpointing": True,
        "compiled_graph_variable": "graph",
        "edges": [],
    }
    if case.fixture == "support-router-v1":
        common.update(
            nodes=[
                {"name": name, "purpose": f"Handle {name} requests"}
                for name in ["router", "billing", "technical", "fallback"]
            ],
            entry_point="router",
            conditional_edges=[
                {
                    "from": "router",
                    "condition": "Select support destination",
                    "branches": {
                        name: name for name in ["billing", "technical", "fallback"]
                    },
                }
            ],
        )
    elif case.fixture == "supervisor-v1":
        common.update(
            nodes=[
                {"name": name, "purpose": f"{name} specialist", "role": role}
                for name, role in [
                    ("supervisor", "coordinator"),
                    ("researcher", "worker"),
                    ("reviewer", "worker"),
                    ("finish", "synthesizer"),
                ]
            ],
            entry_point="supervisor",
            edges=[
                {"from": name, "to": "supervisor"}
                for name in ["researcher", "reviewer"]
            ],
            conditional_edges=[
                {
                    "from": "supervisor",
                    "condition": "Fan out independent work or finish",
                    "guarded_cycle": True,
                    "branches": {
                        "researcher": "researcher",
                        "reviewer": "reviewer",
                        "FINISH": "finish",
                    },
                }
            ],
        )
    else:
        common.update(
            nodes=[
                {
                    "name": "router",
                    "purpose": "Start each conversation turn",
                    "role": "router",
                },
                {
                    "name": "chat",
                    "purpose": "Chatbot assistant with calculator",
                    "role": "assistant",
                    "required_tools": ["data_processor"],
                },
                {
                    "name": "tools",
                    "purpose": "Execute calculator requests",
                    "role": "tool_executor",
                    "required_tools": ["data_processor"],
                },
            ],
            entry_point="router",
            edges=[{"from": "router", "to": "chat"}, {"from": "tools", "to": "chat"}],
            conditional_edges=[
                {
                    "from": "chat",
                    "condition": "Execute tool calls or finish this turn",
                    "guarded_cycle": True,
                    "branches": {"tools": "tools", "complete": "END"},
                }
            ],
            tool_reachability=[
                {
                    "tool_id": "data_processor",
                    "execution_path": "tool_node",
                    "node": "tools",
                    "rationale": "The assistant emits calculator tool calls, executed by ToolNode",
                }
            ],
        )
    return common


async def generate_fixture(case: ExecutionCase, output: Path) -> dict[str, Any]:
    """Run generate_artifacts with only provider/retrieval/environment fixtures."""
    from langchain_community.embeddings import FakeEmbeddings

    from langgraph_system_generator.cli import generate_artifacts
    from langgraph_system_generator.utils.config import settings

    def constructor(stage: str):
        class GenerationModel:
            def __init__(self, **kwargs: Any):
                pass

            async def ainvoke(self, messages: Any) -> AIMessage:
                if stage == "requirements_analyst":
                    payload: Any = [
                        {"type": "goal", "value": case.prompt, "priority": 5}
                    ]
                elif stage == "graph_designer":
                    payload = graph_response(case)
                elif stage == "toolchain_engineer":
                    payload = (
                        [
                            {
                                "tool_id": "data_processor",
                                "name": "calculator",
                                "purpose": "Add two integers",
                                "configuration": {},
                            }
                        ]
                        if case.tool_fixture == "calculator-v1"
                        else []
                    )
                elif stage == "notebook_composer":
                    return AIMessage(content=TOOL_SOURCE)
                else:
                    raise AssertionError(f"Unexpected model invocation: {stage}")
                return AIMessage(content=json.dumps(payload))

        return GenerationModel

    with ExitStack() as stack:
        for stage in [
            "requirements_analyst",
            "architecture_selector",
            "graph_designer",
            "toolchain_engineer",
            "notebook_composer",
        ]:
            stack.enter_context(
                patch(
                    f"langgraph_system_generator.generator.agents.{stage}.ChatOpenAI",
                    constructor(stage),
                )
            )
        stack.enter_context(
            patch(
                "langgraph_system_generator.generator.nodes.rag_retrieval_node",
                _async_fixture_node(AsyncMock(return_value={"docs_context": []})),
            )
        )
        stack.enter_context(
            patch(
                "langgraph_system_generator.generator.nodes.runtime_qa_node",
                _async_fixture_node(AsyncMock(return_value={})),
            )
        )
        stack.enter_context(
            patch(
                "langgraph_system_generator.rag.retriever.DocsRetriever.retrieve",
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "langgraph_system_generator.rag.retriever.DocsRetriever.retrieve_for_pattern",
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "langgraph_system_generator.rag.embeddings.OpenAIEmbeddings",
                return_value=FakeEmbeddings(size=8),
            )
        )
        stack.enter_context(patch.object(settings, "max_repair_attempts", 0))
        return dict(
            await generate_artifacts(
                case.prompt,
                output_dir=output,
                mode=case.generator_mode,
                agent_type=case.architecture,
                formats=["ipynb"],
            )
        )


class RuntimeModel:
    """Fake provider only: LangGraph, reducers, checkpointing and tools stay real."""

    calls: ClassVar[list[dict[str, Any]]] = []
    fail_worker: ClassVar[str | None] = None

    def __init__(self, **kwargs: Any):
        self.schema: Any = None

    def with_structured_output(self, schema: Any, **kwargs: Any) -> RuntimeModel:
        instance = RuntimeModel()
        instance.schema = schema
        return instance

    def bind_tools(self, tools: Any, **kwargs: Any) -> RuntimeModel:
        return self

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        text = "\n".join(str(message.content) for message in messages)
        system = str(messages[0].content) if messages else ""
        record: dict[str, Any] = {
            "schema": getattr(self.schema, "__name__", None),
            "input": text,
        }
        self.calls.append(record)
        if self.schema is not None:
            if self.schema.__name__ == "RouteDecision":
                latest = text.rsplit("Latest user request:", 1)[-1].lower()
                route = (
                    "billing"
                    if "bill" in latest
                    else "technical" if "technical" in latest else "fallback"
                )
                return self.schema(
                    route=route, reasoning="deterministic support classifier"
                )
            if self.schema.__name__ == "SupervisorDecision":
                completed = "RESULT:researcher" in text and "RESULT:reviewer" in text
                return self.schema(
                    next=["FINISH"] if completed else ["researcher", "reviewer"],
                    instructions="Investigate ticket 42",
                    reasoning="Independent specialists",
                )
            raise AssertionError(f"Unexpected runtime schema: {self.schema}")
        for worker in ["researcher", "reviewer"]:
            if system.startswith(f"You are {worker}."):
                if self.fail_worker == worker:
                    raise ValueError(f"fixture worker failure: {worker}")
                return AIMessage(content=f"RESULT:{worker}")
        if "You are the " in system:
            route = system.split("You are the ", 1)[1].split(" specialist", 1)[0]
            return AIMessage(content=f"RESULT:{route}")
        if messages and isinstance(messages[-1], ToolMessage):
            return AIMessage(content=f"Tool result: {messages[-1].content}")
        latest = str(messages[-1].content) if messages else ""
        if latest.endswith("add 2 and 3"):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculator",
                        "args": {"a": 2, "b": 3},
                        "id": "eval-add",
                        "type": "tool_call",
                    }
                ],
            )
        retained = "remember cobalt" in text
        return AIMessage(
            content=(
                "cobalt"
                if latest.endswith("what did I ask?") and retained
                else "Acknowledged"
            )
        )


def install_runtime_fixtures() -> None:
    """External kernel bootstrap; no original notebook cell is rewritten."""
    import builtins

    import langchain_openai

    langchain_openai.ChatOpenAI = RuntimeModel  # type: ignore[misc,assignment]

    def blocked_input(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Interactive input is forbidden in evaluation")

    builtins.input = blocked_input
