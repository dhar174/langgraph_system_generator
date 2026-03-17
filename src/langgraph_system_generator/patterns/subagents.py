"""Supervisor-subagent pattern generator aligned with modern LangGraph APIs."""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from langgraph_system_generator.patterns.utils import (
    build_llm_init,
    double_quoted_literal,
    render_additional_fields,
    sanitize_identifier,
)
from langgraph_system_generator.utils.config import ModelConfig


def _agent_specs(subagents: List[str]) -> List[tuple[str, str]]:
    """Return ``(label, node_name)`` pairs for generated subagents."""
    return [(agent, sanitize_identifier(agent)) for agent in (subagents or ["worker"])]


class SubagentsPattern:
    """Template generator for supervisor/subagent workflows."""

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate a TypedDict state schema for supervisor workflows."""
        additional = render_additional_fields(additional_fields)
        return f'''import operator
from typing import Annotated, Dict, List
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_dicts(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    """Reducer used to merge per-agent outputs into shared state."""
    merged = dict(left or {{}})
    merged.update(right or {{}})
    return merged


class WorkflowState(TypedDict, total=False):
    """State schema for a supervisor-subagent workflow."""

    messages: Annotated[List[BaseMessage], add_messages]
    next_agent: str
    instructions: str
    iterations: int
    dispatch_log: Annotated[List[str], operator.add]
    task_results: Annotated[Dict[str, str], merge_dicts]
    final_output: str
{additional}'''

    @staticmethod
    def generate_supervisor_code(
        subagents: List[str],
        subagent_descriptions: Optional[Dict[str, str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
    ) -> str:
        """Generate a supervisor node that routes with ``Command``."""
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config

        specs = _agent_specs(subagents)
        if subagent_descriptions is None:
            subagent_descriptions = {
                label: f"{label} specialist" for label, _ in specs
            }

        agent_literals = ", ".join(double_quoted_literal(label) for label, _ in specs)
        goto_literals = ", ".join(
            [double_quoted_literal(node_name) for _, node_name in specs] + ['"finish"']
        )
        route_map_lines = ",\n        ".join(
            f"{double_quoted_literal(label)}: {double_quoted_literal(node_name)}"
            for label, node_name in specs
        )
        agent_overview = "\n".join(
            f"- {label}: {subagent_descriptions.get(label, f'{label} specialist')}"
            for label, _ in specs
        )
        llm_init = build_llm_init(
            config.model,
            0,
            config.api_base,
            config.max_tokens,
        )

        if use_structured_output:
            return f'''from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field


class SupervisorDecision(BaseModel):
    """Typed supervisor routing decision."""

    next_agent: Literal[{agent_literals}, "FINISH"] = Field(
        description="Which specialist should work next, or FINISH when done."
    )
    instructions: str = Field(
        description="Concrete next-step instructions for the selected specialist."
    )
    reasoning: str = Field(
        description="Why this next step is the best choice right now."
    )


def supervisor_node(state: WorkflowState) -> Command[Literal[{goto_literals}]]:
    """Choose the next specialist and pass along instructions."""
    route_map = {{
        {route_map_lines}
    }}
    messages = state.get("messages", [])
    results = state.get("task_results", {{}})
    iterations = state.get("iterations", 0)
    if iterations >= MAX_ITERATIONS:
        return Command(
            update={{
                "next_agent": "FINISH",
                "instructions": "Maximum iterations reached; synthesize the work so far.",
                "dispatch_log": ["Supervisor stopped after reaching MAX_ITERATIONS."],
            }},
            goto="finish",
        )
    llm = {llm_init}

    result_summary = "\\n".join(
        f"- {{agent}}: {{output[:160]}}"
        for agent, output in results.items()
    ) or "No specialist results yet."

    decision = llm.with_structured_output(SupervisorDecision).invoke([
        SystemMessage(
            content="""You are a supervisor coordinating a LangGraph specialist team.

Available specialists:
{agent_overview}
"""
        ),
        HumanMessage(
            content=f"Latest request: {{messages[-1].content if messages else 'Start the workflow.'}}\\n\\n"
            f"Current results:\\n{{result_summary}}"
        ),
    ])

    target = "finish" if decision.next_agent == "FINISH" else route_map[decision.next_agent]
    return Command(
        update={{
            "next_agent": decision.next_agent,
            "instructions": decision.instructions,
            "iterations": iterations + (0 if decision.next_agent == "FINISH" else 1),
            "dispatch_log": [
                f"Supervisor -> {{decision.next_agent}}: {{decision.reasoning}}"
            ],
            "messages": [
                AIMessage(
                    content=f"Supervisor selected {{decision.next_agent}}. {{decision.instructions}}"
                )
            ],
        }},
        goto=target,
    )'''

        default_agent = specs[0][0]
        return f'''from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command


def supervisor_node(state: WorkflowState) -> Command[Literal[{goto_literals}]]:
    """Fallback supervisor that emits a simple route instruction."""
    route_map = {{
        {route_map_lines}
    }}
    iterations = state.get("iterations", 0)
    if iterations >= MAX_ITERATIONS:
        return Command(
            update={{
                "next_agent": "FINISH",
                "instructions": "Maximum iterations reached; synthesize the work so far.",
                "dispatch_log": ["Supervisor stopped after reaching MAX_ITERATIONS."],
            }},
            goto="finish",
        )
    llm = {llm_init}
    response = llm.invoke([
        SystemMessage(
            content="Reply with AGENT|INSTRUCTIONS where AGENT is one of: {', '.join(label for label, _ in specs)}, FINISH."
        ),
        HumanMessage(content=f"Latest request: {{state.get('messages', [])[-1].content if state.get('messages') else 'Start the workflow.'}}"),
    ])

    raw = response.content.strip()
    agent_name, _, instructions = raw.partition("|")
    next_agent = agent_name.strip() or {double_quoted_literal(default_agent)}
    if next_agent not in route_map:
        next_agent = {double_quoted_literal(default_agent)}
    target = route_map[next_agent]

    return Command(
        update={{
            "next_agent": next_agent,
            "instructions": instructions.strip(),
            "iterations": iterations + 1,
            "dispatch_log": [f"Supervisor -> {{next_agent}}"],
            "messages": [AIMessage(content=f"Supervisor selected {{next_agent}}")],
        }},
        goto=target,
    )'''

    @staticmethod
    def generate_subagent_code(
        agent_name: str,
        agent_description: str,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        include_tools: bool = False,
    ) -> str:
        """Generate a specialist node implementation."""
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config

        llm_init = build_llm_init(
            config.model,
            config.temperature,
            config.api_base,
            config.max_tokens,
        )
        node_name = sanitize_identifier(agent_name)

        tool_snippet = ""
        llm_variable = "llm"
        if include_tools:
            llm_variable = "llm_with_tools"
            tool_snippet = '''
    def lookup_context(query: str) -> str:
        """Placeholder tool for auxiliary context lookup."""
        return f"Context for: {query}"

    tools = [lookup_context]
    llm_with_tools = llm.bind_tools(tools)'''

        return f'''from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def {node_name}_node(state: WorkflowState) -> dict:
    """Execute the {agent_name} specialist."""
    llm = {llm_init}{tool_snippet}
    messages = state.get("messages", [])
    instructions = state.get("instructions", "Complete the assigned task.")

    response = {llm_variable}.invoke([
        SystemMessage(
            content="""You are {agent_name}.

Role:
{agent_description}
"""
        ),
        HumanMessage(content=f"Supervisor instructions: {{instructions}}"),
        *messages,
    ])

    return {{
        "task_results": {{"{agent_name}": getattr(response, "content", str(response))}},
        "messages": [
            AIMessage(content=f"{agent_name} completed the assigned task.")
        ],
    }}'''

    @staticmethod
    def generate_graph_code(subagents: List[str], max_iterations: int = 10) -> str:
        """Generate the graph wiring for the supervisor workflow."""
        specs = _agent_specs(subagents)
        node_additions = "\n".join(
            f'workflow.add_node("{node_name}", {node_name}_node)'
            for _, node_name in specs
        )
        return_edges = "\n".join(
            f'workflow.add_edge("{node_name}", "supervisor")' for _, node_name in specs
        )

        return f'''from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver


def finish_node(state: WorkflowState) -> dict:
    """Synthesize a final answer from the accumulated specialist outputs."""
    results = state.get("task_results", {{}})
    if results:
        final_output = "\\n\\n".join(
            f"## {{agent}}\\n{{output}}" for agent, output in results.items()
        )
    else:
        final_output = "No specialist results were produced."
    return {{
        "final_output": final_output,
        "messages": [],
    }}


workflow = StateGraph(WorkflowState)
memory = InMemorySaver()
checkpointer = InMemorySaver()

workflow.add_node("supervisor", supervisor_node)
{node_additions}
workflow.add_node("finish", finish_node)

workflow.add_edge(START, "supervisor")
{return_edges}
workflow.add_edge("finish", END)

graph = workflow.compile(checkpointer=checkpointer)

MAX_ITERATIONS = {max_iterations}'''

    @staticmethod
    def generate_complete_example(
        subagents: List[str],
        subagent_descriptions: Optional[Dict[str, str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate a complete runnable supervisor/subagent example."""
        specs = _agent_specs(subagents)
        if subagent_descriptions is None:
            subagent_descriptions = {
                label: f"{label} specialist" for label, _ in specs
            }

        state_code = SubagentsPattern.generate_state_code()
        supervisor_code = SubagentsPattern.generate_supervisor_code(
            [label for label, _ in specs],
            subagent_descriptions,
            model_config=model_config,
        )
        agent_nodes = "\n\n".join(
            SubagentsPattern.generate_subagent_code(
                label,
                subagent_descriptions.get(label, f"{label} specialist"),
                model_config=model_config,
            )
            for label, _ in specs
        )
        graph_code = SubagentsPattern.generate_graph_code([label for label, _ in specs])

        return f'''"""Subagents Pattern Example."""

from __future__ import annotations

import argparse
import asyncio

from langchain_core.messages import HumanMessage

{state_code}

{supervisor_code}

{agent_nodes}

{graph_code}


def build_initial_state(user_request: str) -> WorkflowState:
    """Create an initial workflow state for the demo."""
    return {{
        "messages": [HumanMessage(content=user_request)],
        "task_results": {{}},
        "dispatch_log": [],
        "iterations": 0,
        "final_output": "",
    }}


async def run_example(user_request: str) -> WorkflowState:
    """Run the supervisor workflow and return the final state."""
    return await graph.ainvoke(build_initial_state(user_request))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the subagents pattern example.")
    parser.add_argument("prompt", nargs="?", default="Prepare a concise research brief on autonomous agents.")
    args = parser.parse_args()

    result = asyncio.run(run_example(args.prompt))
    print("Dispatch Log:")
    for entry in result.get("dispatch_log", []):
        print("-", entry)
    print("\\nFinal Output:")
    print(result.get("final_output", ""))


if __name__ == "__main__":
    main()
'''
