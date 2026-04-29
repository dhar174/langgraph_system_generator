"""Experimental Deep Agents pattern generator.

The generated notebook code keeps ``deepagents`` optional at generation time and
falls back to deterministic local behavior when the SDK or live credentials are
not available in the notebook runtime.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Union

from langgraph_system_generator.patterns.utils import render_additional_fields
from langgraph_system_generator.utils.config import ModelConfig


class DeepAgentsPattern:
    """Template generator for opt-in Deep Agents harness workflows."""

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate a TypedDict state schema for Deep Agents workflows."""

        additional = render_additional_fields(additional_fields)
        return f'''import operator
from typing import Annotated, Any, Dict, List
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer used to merge Deep Agents artifacts and subagent outputs."""
    merged = dict(left or {{}})
    merged.update(right or {{}})
    return merged


class WorkflowState(TypedDict, total=False):
    """State schema for an experimental Deep Agents workflow."""

    messages: Annotated[List[BaseMessage], add_messages]
    task_plan: Annotated[List[str], operator.add]
    artifacts: Annotated[Dict[str, Any], merge_dicts]
    subagent_results: Annotated[Dict[str, Any], merge_dicts]
    final_output: str
    deepagents_available: bool
{additional}'''

    @staticmethod
    def generate_agent_node_code(
        subagents: Optional[List[str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        *,
        tools: Optional[List[str]] = None,
    ) -> str:
        """Generate a Deep Agents node with a deterministic fallback path."""

        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config

        model_name = config.model or "gpt-5-mini"
        default_model = model_name if ":" in model_name else f"openai:{model_name}"
        tool_names = []
        for tool_name in tools or []:
            normalized_name = str(tool_name or "").strip()
            if normalized_name and normalized_name not in tool_names:
                tool_names.append(normalized_name)
        subagent_names = subagents or ["researcher", "critic"]
        subagent_items = []
        for name in subagent_names:
            label = str(name or "").strip() or "specialist"
            subagent_items.append(
                {
                    "name": label.replace("_", "-"),
                    "description": f"Handles {label.replace('_', ' ')} work for the Deep Agent.",
                    "system_prompt": (
                        f"You are the {label.replace('_', ' ')} specialist. "
                        "Return concise findings for the main Deep Agent."
                    ),
                }
            )

        subagent_literal = json.dumps(subagent_items, indent=4)
        tool_literal = json.dumps(tool_names, indent=4)
        return f'''import os
from typing import Any, Dict, List


def _latest_user_text(messages: List[Any]) -> str:
    """Return the most recent user-facing message text."""
    if not messages:
        return "Run the Deep Agents workflow."
    last_message = messages[-1]
    return str(getattr(last_message, "content", last_message))


def _deterministic_deepagents_fallback(goal: str) -> Dict[str, Any]:
    """Return a runnable local fallback when Deep Agents is unavailable."""
    return {{
        "task_plan": [
            "Clarify the user goal.",
            "Use Deep Agents planning, tools, and subagents when the SDK is installed.",
            "Summarize the outcome for notebook users.",
        ],
        "artifacts": {{
            "deepagents_status": (
                "Deep Agents SDK was not invoked. Install `deepagents` and configure "
                "model credentials to run the live harness."
            )
        }},
        "subagent_results": {{}},
        "final_output": f"Deterministic Deep Agents scaffold prepared for: {{goal}}",
        "deepagents_available": False,
    }}


def _build_deep_agent():
    """Create the Deep Agents harness lazily if optional runtime deps exist."""
    try:
        from deepagents import create_deep_agent
    except ModuleNotFoundError:
        return None

    if not os.environ.get("OPENAI_API_KEY"):
        return None

    model_name = os.environ.get(
        "DEEP_AGENTS_MODEL",
        "{default_model}",
    )
    subagents = {subagent_literal}
    tool_names = {tool_literal}
    available_tools = [
        globals()[tool_name]
        for tool_name in tool_names
        if callable(globals().get(tool_name))
    ]
    return create_deep_agent(
        model=model_name,
        tools=available_tools,
        system_prompt=(
            "You are an experimental Deep Agent generated by LangGraph Notebook "
            "Foundry. Plan before acting, delegate to subagents when useful, and "
            "return a compact final answer."
        ),
        subagents=subagents,
    )


def deep_agent_node(state: WorkflowState) -> WorkflowState:
    """Run the optional Deep Agents harness or a deterministic fallback."""
    messages = state.get("messages", [])
    goal = _latest_user_text(messages)
    agent = _build_deep_agent()
    if agent is None:
        return _deterministic_deepagents_fallback(goal)

    result = agent.invoke({{"messages": [{{"role": "user", "content": goal}}]}})
    result_messages = result.get("messages", []) if isinstance(result, dict) else []
    if result_messages:
        last_message = result_messages[-1]
        final_message = str(getattr(last_message, "content", last_message))
    else:
        final_message = str(result)
    return {{
        "task_plan": ["Deep Agents SDK executed the requested workflow."],
        "artifacts": {{"deepagents_status": "Deep Agents SDK invoked successfully."}},
        "subagent_results": {{}},
        "final_output": final_message,
        "deepagents_available": True,
    }}'''

    @staticmethod
    def generate_graph_code() -> str:
        """Generate graph wiring for the Deep Agents one-shot harness."""

        return '''from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


workflow = StateGraph(WorkflowState)
workflow.add_node("deep_agent", deep_agent_node)
workflow.add_edge(START, "deep_agent")
workflow.add_edge("deep_agent", END)

memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)'''

    @staticmethod
    def generate_execution_code() -> str:
        """Generate an execution snippet for Deep Agents notebooks."""

        return '''from langchain_core.messages import HumanMessage

# Execute the workflow. Without `deepagents` and OPENAI_API_KEY, this uses the
# deterministic fallback path so the notebook remains runnable offline.
config = {"configurable": {"thread_id": "lnf-deepagents-demo"}}
initial_state: WorkflowState = {
    "messages": [HumanMessage(content="Plan and summarize a small research task.")],
    "task_plan": [],
    "artifacts": {},
    "subagent_results": {},
    "final_output": "",
    "deepagents_available": False,
}

final_state = graph.invoke(initial_state, config)
print(final_state.get("final_output", final_state))'''

    @staticmethod
    def generate_overview_markdown() -> str:
        """Return notebook-facing overview copy for the experimental harness."""

        return (
            "## Deep Agents Harness\n\n"
            "This section uses the optional `deepagents` SDK when it is installed "
            "and provider credentials are configured. If not, the generated node "
            "falls back to a deterministic local scaffold so the notebook still "
            "runs in offline or stub-mode environments."
        )
