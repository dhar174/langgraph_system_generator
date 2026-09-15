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
from typing import Annotated, Any, Dict, List
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer used to merge per-agent outputs into shared state."""
    merged = dict(left or {{}})
    merged.update(right or {{}})
    return merged


class WorkflowState(TypedDict, total=False):
    """State schema for a supervisor-subagent workflow."""

    messages: Annotated[List[BaseMessage], add_messages]
    next_agent: str
    next_agents: List[str]
    instructions: str
    iterations: int
    dispatch_log: Annotated[List[str], operator.add]
    task_results: Annotated[Dict[str, str], merge_dicts]
    task_result_versions: Annotated[Dict[str, int], merge_dicts]
    task_results_summary: str
    task_results_summary_fingerprint: str
    final_output: str
{additional}'''

    @staticmethod
    def generate_supervisor_code(
        subagents: List[str],
        subagent_descriptions: Optional[Dict[str, str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
        use_notebook_helper: bool = False,
    ) -> str:
        """Generate a supervisor node that prepares Send-based fan-out routing."""
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config

        specs = _agent_specs(subagents)
        if subagent_descriptions is None:
            subagent_descriptions = {label: f"{label} specialist" for label, _ in specs}

        agent_literals = ", ".join(double_quoted_literal(label) for label, _ in specs)
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
            use_notebook_helper=use_notebook_helper,
        )
        summary_model = config.summary_model or (
            "gpt-4o-mini" if config.api_base is None else config.model
        )
        if use_notebook_helper:
            params = []
            if summary_model != config.model or config.summary_model is not None:
                params.append(f"model={summary_model!r}")
            params.append("temperature=0")
            if config.max_tokens is not None:
                params.append(f"max_tokens={config.max_tokens}")
            summary_llm_init = f"make_llm({', '.join(params)})"
        else:
            summary_llm_init = build_llm_init(
                summary_model,
                0,
                config.api_base,
                config.max_tokens,
                use_notebook_helper=False,
            )

        context_window_helpers = f'''MAX_RESULT_CHARS = 2000
MAX_TOTAL_RESULT_CHARS = 8000
RECENT_FULL_RESULTS = 2


def _truncate_result(text: str, limit: int) -> str:
    """Truncate text cleanly at character budget with indicator."""
    if len(text) <= limit:
        return text
    indicator = "... [truncated]"
    return text[: max(0, limit - len(indicator))] + indicator


def _format_results(items: list) -> str:
    """Format a list of (agent, result) tuples into bullet items."""
    if not items:
        return "No specialist results yet."
    return "\\n".join(
        f"- {{agent}}: {{_truncate_result(str(result), MAX_RESULT_CHARS)}}"
        for agent, result in items
    )


def _chunk_items(items: list, max_chunk_chars: int) -> list:
    """Group (agent, result) items into text chunks of at most max_chunk_chars."""
    chunks = []
    current_chunk = []
    current_len = 0
    for agent, result in items:
        item_text = f"- {{agent}}: {{_truncate_result(str(result), MAX_RESULT_CHARS)}}"
        item_len = len(item_text) + (1 if current_chunk else 0)
        if current_chunk and (current_len + item_len > max_chunk_chars):
            chunks.append("\\n".join(current_chunk))
            current_chunk = [item_text]
            current_len = len(item_text)
        else:
            current_chunk.append(item_text)
            current_len += item_len
    if current_chunk:
        chunks.append("\\n".join(current_chunk))
    return chunks


def _summarize_chunk(text_to_summarize: str) -> str:
    """Summarize a single text chunk with safe fallback."""
    if not text_to_summarize:
        return ""

    try:
        summarizer = {summary_llm_init}
        summary_prompt = (
            "Summarize the older agent results into concise supervisor context. "
            "Preserve completed work, important findings, unresolved issues, "
            "and constraints that future agents should know."
        )
        response = summarizer.invoke(
            [
                SystemMessage(content=summary_prompt),
                HumanMessage(content=f"Older agent results:\\n{{text_to_summarize}}"),
            ]
        )
        return _truncate_result(str(getattr(response, "content", response)).strip(), MAX_TOTAL_RESULT_CHARS)
    except Exception:
        return _truncate_result(text_to_summarize, MAX_TOTAL_RESULT_CHARS // 2)


def _summarize_older_results(
    older_items_or_text,
    target_budget: int = MAX_TOTAL_RESULT_CHARS // 2,
) -> str:
    """Condense older results using chunked summarization and bounded consolidation."""
    if not older_items_or_text:
        return ""

    if isinstance(older_items_or_text, str):
        if len(older_items_or_text) <= MAX_TOTAL_RESULT_CHARS:
            return _truncate_result(_summarize_chunk(older_items_or_text), target_budget)
        lines = older_items_or_text.strip().split("\\n")
        chunks = []
        curr = []
        curr_len = 0
        for line in lines:
            line_len = len(line) + (1 if curr else 0)
            if curr and (curr_len + line_len > MAX_TOTAL_RESULT_CHARS):
                chunks.append("\\n".join(curr))
                curr = [line]
                curr_len = len(line)
            else:
                curr.append(line)
                curr_len += line_len
        if curr:
            chunks.append("\\n".join(curr))
    else:
        chunks = _chunk_items(older_items_or_text, MAX_TOTAL_RESULT_CHARS)

    if not chunks:
        return ""
    if len(chunks) == 1:
        return _truncate_result(_summarize_chunk(chunks[0]), target_budget)

    chunk_summaries = [_summarize_chunk(chunk) for chunk in chunks]
    combined = "\\n\\n".join([s for s in chunk_summaries if s])
    if len(combined) <= target_budget:
        return combined
    consolidated = _summarize_chunk(_truncate_result(combined, MAX_TOTAL_RESULT_CHARS))
    return _truncate_result(consolidated, target_budget)


def _prepare_task_results_context(
    task_results: dict,
    existing_summary: str = "",
    task_result_versions: dict = None,
    existing_fingerprint: str = "",
):
    """Return summarized older results plus recent full results and summary fingerprint."""
    if not task_results:
        return "", "No specialist results yet.", ""

    versions = task_result_versions or {{}}
    ordered_items = sorted(
        task_results.items(),
        key=lambda item: versions.get(item[0], 0),
    )
    all_results = _format_results(ordered_items)

    if len(all_results) <= MAX_TOTAL_RESULT_CHARS:
        return "", all_results, ""

    if len(ordered_items) <= RECENT_FULL_RESULTS:
        notice = "Earlier results were truncated to fit the supervisor context window."
        available_budget = max(MAX_TOTAL_RESULT_CHARS - len(notice) - 2, MAX_TOTAL_RESULT_CHARS // 2)
        truncated_recent = _truncate_result(all_results, available_budget)
        return notice, truncated_recent, ""

    recent_items = ordered_items[-RECENT_FULL_RESULTS:]
    older_items = ordered_items[:-RECENT_FULL_RESULTS]

    # Calculate fingerprint from complete logical older snapshot before any truncation or chunking
    snapshot_parts = [
        f"{{agent}}:{{versions.get(agent, 0)}}:"
        f"{{hashlib.sha256(str(result).encode('utf-8')).hexdigest()}}"
        for agent, result in older_items
    ]
    fingerprint = hashlib.sha256(
        "\\n".join(snapshot_parts).encode("utf-8")
    ).hexdigest()[:16]

    recent_results = _format_results(recent_items)
    remaining_summary_budget = max(MAX_TOTAL_RESULT_CHARS - len(recent_results), 0)

    if existing_fingerprint and existing_fingerprint == fingerprint and existing_summary:
        updated_summary = existing_summary
        updated_fingerprint = existing_fingerprint
    else:
        target_budget = max(remaining_summary_budget, MAX_TOTAL_RESULT_CHARS // 2)
        updated_summary = _summarize_older_results(older_items, target_budget=target_budget)
        updated_fingerprint = fingerprint

    if remaining_summary_budget == 0:
        return "", _truncate_result(recent_results, MAX_TOTAL_RESULT_CHARS), updated_fingerprint
    updated_summary = _truncate_result(updated_summary, remaining_summary_budget)
    return updated_summary, recent_results, updated_fingerprint'''

        if use_structured_output:
            return f'''import hashlib
from typing import List, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


class SupervisorDecision(BaseModel):
    """Typed supervisor routing decision with optional parallel fan-out."""

    next: List[Literal[{agent_literals}, "FINISH"]] = Field(
        description="One or more specialists that can work next, or FINISH when done."
    )
    instructions: str = Field(
        description="Concrete next-step instructions for the selected specialist(s)."
    )
    reasoning: str = Field(
        description="Why this next step is the best choice right now."
    )


{context_window_helpers}


def supervisor_node(state: WorkflowState) -> dict:
    """Choose the next specialist batch and pass along instructions."""
    route_map = {{
        {route_map_lines}
    }}
    messages = state.get("messages", [])
    iterations = state.get("iterations", 0)
    if iterations >= MAX_ITERATIONS:
        return {{
            "next_agent": "FINISH",
            "next_agents": ["FINISH"],
            "instructions": "Maximum iterations reached; synthesize the work so far.",
            "dispatch_log": ["Supervisor stopped after reaching MAX_ITERATIONS."],
        }}
    llm = {llm_init}

    task_results = state.get("task_results", {{}})
    task_results_summary = state.get("task_results_summary", "")
    task_result_versions = state.get("task_result_versions", {{}})
    task_results_summary_fingerprint = state.get("task_results_summary_fingerprint", "")
    task_results_summary, recent_results, task_results_summary_fingerprint = _prepare_task_results_context(
        task_results,
        task_results_summary,
        task_result_versions=task_result_versions,
        existing_fingerprint=task_results_summary_fingerprint,
    )

    decision = llm.with_structured_output(SupervisorDecision).invoke([
        SystemMessage(
            content="""You are a supervisor coordinating a LangGraph specialist team.

Available specialists:
{agent_overview}

Select one or more specialists when their work can proceed independently.
Select FINISH only when the accumulated results are ready to synthesize.
"""
        ),
        HumanMessage(
            content=f"Latest request: {{messages[-1].content if messages else 'Start the workflow.'}}\\n\\n"
            f"Older summarized results:\\n{{task_results_summary or 'No summarized results yet.'}}\\n\\n"
            f"Recent full results:\\n{{recent_results}}"
        ),
    ])

    selected_agents = []
    finish_requested = False
    for agent_name in decision.next:
        if agent_name == "FINISH":
            finish_requested = True
            continue
        if agent_name in route_map and agent_name not in selected_agents:
            selected_agents.append(agent_name)

    if finish_requested or not selected_agents:
        next_agents = ["FINISH"]
    else:
        next_agents = selected_agents

    dispatch_targets = ", ".join(next_agents)
    return {{
        "next_agent": next_agents[0],
        "next_agents": next_agents,
        "instructions": decision.instructions,
        "iterations": iterations + (0 if next_agents == ["FINISH"] else 1),
        "task_results_summary": task_results_summary,
        "task_results_summary_fingerprint": task_results_summary_fingerprint,
        "dispatch_log": [
            f"Supervisor -> {{dispatch_targets}}: {{decision.reasoning}}"
        ],
        "messages": [
            AIMessage(
                content=f"Supervisor selected {{dispatch_targets}}. {{decision.instructions}}"
            )
        ],
    }}'''

        default_agent = specs[0][0]
        return f'''import hashlib
from typing import List, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

{context_window_helpers}


def supervisor_node(state: WorkflowState) -> dict:
    """Fallback supervisor that emits one or more route instructions."""
    route_map = {{
        {route_map_lines}
    }}
    iterations = state.get("iterations", 0)
    if iterations >= MAX_ITERATIONS:
        return {{
            "next_agent": "FINISH",
            "next_agents": ["FINISH"],
            "instructions": "Maximum iterations reached; synthesize the work so far.",
            "dispatch_log": ["Supervisor stopped after reaching MAX_ITERATIONS."],
        }}
    llm = {llm_init}

    task_results = state.get("task_results", {{}})
    task_results_summary = state.get("task_results_summary", "")
    task_result_versions = state.get("task_result_versions", {{}})
    task_results_summary_fingerprint = state.get("task_results_summary_fingerprint", "")
    task_results_summary, recent_results, task_results_summary_fingerprint = _prepare_task_results_context(
        task_results,
        task_results_summary,
        task_result_versions=task_result_versions,
        existing_fingerprint=task_results_summary_fingerprint,
    )

    response = llm.invoke([
        SystemMessage(
            content="Reply with AGENT[,AGENT...]|INSTRUCTIONS where AGENT is one of: {', '.join(label for label, _ in specs)}, FINISH."
        ),
        HumanMessage(
            content=f"Latest request: {{state.get('messages', [])[-1].content if state.get('messages') else 'Start the workflow.'}}\\n\\n"
            f"Older summarized results:\\n{{task_results_summary or 'No summarized results yet.'}}\\n\\n"
            f"Recent full results:\\n{{recent_results}}\\n\\n"
            "Decision:"
        ),
    ])

    raw = response.content.strip()
    agent_names, _, instructions = raw.partition("|")
    requested_agents = [
        name.strip()
        for name in agent_names.split(",")
        if name.strip()
    ] or [{double_quoted_literal(default_agent)}]
    if any(name == "FINISH" for name in requested_agents):
        next_agents = ["FINISH"]
    else:
        next_agents = []
        for agent_name in requested_agents:
            if agent_name in route_map and agent_name not in next_agents:
                next_agents.append(agent_name)
        if not next_agents:
            next_agents = [{double_quoted_literal(default_agent)}]

    dispatch_targets = ", ".join(next_agents)
    return {{
        "next_agent": next_agents[0],
        "next_agents": next_agents,
        "instructions": instructions.strip(),
        "iterations": iterations + (0 if next_agents == ["FINISH"] else 1),
        "task_results_summary": task_results_summary,
        "task_results_summary_fingerprint": task_results_summary_fingerprint,
        "dispatch_log": [f"Supervisor -> {{dispatch_targets}}"],
        "messages": [AIMessage(content=f"Supervisor selected {{dispatch_targets}}")],
    }}'''

    @staticmethod
    def generate_subagent_code(
        agent_name: str,
        agent_description: str,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        include_tools: bool = False,
        use_notebook_helper: bool = False,
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
            use_notebook_helper=use_notebook_helper,
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

    current_version = max(
        state.get("iterations", 0),
        max(state.get("task_result_versions", {{}}).values(), default=0) + 1,
    )

    return {{
        "task_results": {{"{agent_name}": getattr(response, "content", str(response))}},
        "task_result_versions": {{"{agent_name}": current_version}},
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
        route_map_lines = ",\n        ".join(
            [
                f"{double_quoted_literal(label)}: {double_quoted_literal(node_name)}"
                for label, node_name in specs
            ]
            + [
                f"{double_quoted_literal(node_name)}: {double_quoted_literal(node_name)}"
                for _, node_name in specs
            ]
            + ['"FINISH": "finish"', '"finish": "finish"']
        )
        worker_nodes_literal = (
            "{"
            + ", ".join(double_quoted_literal(node_name) for _, node_name in specs)
            + "}"
        )
        path_map_entries = ", ".join(
            [
                f"{double_quoted_literal(node_name)}: {double_quoted_literal(node_name)}"
                for _, node_name in specs
            ]
            + ['"finish": "finish"']
        )

        return f'''from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Send


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


def supervisor_router(state: WorkflowState):
    """Fan out to selected specialists or finish when supervision is complete."""
    route_map = {{
        {route_map_lines}
    }}
    worker_nodes = {worker_nodes_literal}
    requested_agents = state.get("next_agents") or []
    if not requested_agents and state.get("next_agent"):
        requested_agents = [state.get("next_agent")]

    destinations = []
    for agent_name in requested_agents:
        target = route_map.get(agent_name)
        if target == "finish":
            return "finish"
        if target in worker_nodes and target not in destinations:
            destinations.append(target)

    if not destinations:
        return "finish"
    return [Send(destination, state) for destination in destinations]


workflow = StateGraph(WorkflowState)
memory = InMemorySaver()
checkpointer = InMemorySaver()

workflow.add_node("supervisor", supervisor_node)
{node_additions}
workflow.add_node("finish", finish_node)

workflow.add_edge(START, "supervisor")
workflow.add_conditional_edges(
    "supervisor",
    supervisor_router,
    {{{path_map_entries}}},
)
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
            subagent_descriptions = {label: f"{label} specialist" for label, _ in specs}

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
        "task_result_versions": {{}},
        "task_results_summary": "",
        "task_results_summary_fingerprint": "",
        "dispatch_log": [],
        "next_agents": [],
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
