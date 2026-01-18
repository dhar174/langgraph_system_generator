"""Subagents pattern for supervisor-based multi-agent workflows.

This module provides templates and code generators for implementing
supervisor-subagent LangGraph architectures where a supervisor agent
coordinates and delegates tasks to multiple specialized subagents.

Example Usage:
    >>> from langgraph_system_generator.patterns.subagents import SubagentsPattern
    >>>
    >>> # Generate state code
    >>> state_code = SubagentsPattern.generate_state_code()
    >>>
    >>> # Generate supervisor implementation
    >>> supervisor_code = SubagentsPattern.generate_supervisor_code(
    ...     subagents=["researcher", "writer", "reviewer"]
    ... )
    >>>
    >>> # Generate complete graph code
    >>> graph_code = SubagentsPattern.generate_graph_code(
    ...     subagents=["researcher", "writer", "reviewer"]
    ... )
"""

from typing import Dict, List, Optional


class SubagentsPattern:
    """Template generator for supervisor-subagent multi-agent patterns.

    The subagents pattern is ideal for workflows where:
    - A supervisor coordinates multiple specialized agents
    - Tasks need to be decomposed and delegated
    - Agents may need to collaborate or work sequentially
    - The supervisor maintains overall workflow state and decisions

    Architecture:
        START -> supervisor -> [subagent_a, subagent_b, ...] -> supervisor -> END
    """

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate state schema code for subagents pattern.

        Args:
            additional_fields: Optional dict mapping field names to descriptions

        Returns:
            Python code string defining the WorkflowState class
        """
        additional = ""
        if additional_fields:
            for field_name, description in additional_fields.items():
                additional += f"    {field_name}: str  # {description}\n"

        return f'''from typing import Annotated, Sequence
from langgraph.graph import MessagesState


class WorkflowState(MessagesState):
    """State schema for supervisor-subagent workflow.
    
    Inherits from MessagesState to maintain conversation history.
    Additional fields track the supervisor's decisions and coordination.
    """
    next: str  # Next agent to execute or "FINISH"
    instructions: str  # Supervisor's instructions to the next agent
    task_results: dict  # Results from each subagent
{additional}'''

    @staticmethod
    def generate_supervisor_code(
        subagents: List[str],
        subagent_descriptions: Optional[Dict[str, str]] = None,
        llm_model: str = "gpt-5-mini",
        use_structured_output: bool = True,
    ) -> str:
        """Generate supervisor node implementation code.

        Args:
            subagents: List of subagent names
            subagent_descriptions: Optional dict mapping agent names to descriptions
            llm_model: LLM model to use for supervisor decisions
            use_structured_output: Whether to use structured output

        Returns:
            Python code string implementing the supervisor node
        """
        if subagent_descriptions is None:
            subagent_descriptions = {
                agent: f"{agent} specialist" for agent in subagents
            }

        agents_info = "\n".join(
            [
                f"- {agent}: {subagent_descriptions.get(agent, f'{agent} specialist')}"
                for agent in subagents
            ]
        )

        agents_list = ", ".join([f'"{agent}"' for agent in subagents])

        if use_structured_output:
            return f'''from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import Literal


class SupervisorDecision(BaseModel):
    """Structured output for supervisor decisions."""
    next: Literal[{agents_list}, "FINISH"] = Field(
        description="The next agent to execute, or FINISH if task is complete"
    )
    instructions: str = Field(
        description="Specific instructions for the selected agent"
    )
    reasoning: str = Field(
        description="Explanation for this decision"
    )


def supervisor_node(state: WorkflowState) -> WorkflowState:
    """Supervisor coordinates subagents and delegates tasks.
    
    The supervisor analyzes the current state, determines which subagent
    should act next (or if the task is complete), and provides specific
    instructions to that agent.
    """
    messages = state["messages"]
    task_results = state.get("task_results", {{}})
    
    # Initialize LLM with structured output
    llm = ChatOpenAI(model="{llm_model}", temperature=0)
    structured_llm = llm.with_structured_output(SupervisorDecision)
    
    # Supervisor prompt
    system_prompt = """You are a supervisor coordinating a team of specialized agents.

Available agents:
{agents_info}

Your role is to:
1. Analyze the current conversation and task progress
2. Decide which agent should act next (or FINISH if complete)
3. Provide clear, specific instructions to the selected agent

Consider the results from previous agents when making decisions."""
    
    # Build context from task results
    results_summary = "\\n".join([
        f"- {{agent}}: {{result[:200]}}..." if len(result) > 200 else f"- {{agent}}: {{result}}"
        for agent, result in task_results.items()
    ]) if task_results else "No results yet."
    
    user_prompt = f"""Current conversation: {{messages[-1].content if messages else "Starting task"}}

Previous agent results:
{{results_summary}}

Decide which agent should act next and provide instructions."""
    
    # Get supervisor decision
    decision = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ])
    
    # Update state
    next_message = HumanMessage(
        content=f"Supervisor decision: {{decision.next}} - {{decision.instructions}}"
    )
    
    return {{
        **state,
        "next": decision.next,
        "instructions": decision.instructions,
        "messages": messages + [next_message],
    }}'''
        else:
            return f'''from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def supervisor_node(state: WorkflowState) -> WorkflowState:
    """Supervisor coordinates subagents and delegates tasks."""
    messages = state["messages"]
    task_results = state.get("task_results", {{}})
    
    llm = ChatOpenAI(model="{llm_model}", temperature=0)
    
    # Supervisor prompt
    system_prompt = SystemMessage(content=f"""You are a supervisor coordinating agents.
Available agents: {agents_list}, or FINISH to complete.

Respond with: AGENT_NAME|instructions
Example: researcher|Find information about X""")
    
    results_summary = str(task_results) if task_results else "No results yet"
    user_prompt = HumanMessage(
        content=f"Task: {{messages[-1].content if messages else 'Start'}}\\nResults: {{results_summary}}\\nDecision:"
    )
    
    # Get decision
    response = llm.invoke([system_prompt, user_prompt])
    parts = response.content.split("|", 1)
    next_agent = parts[0].strip()
    instructions = parts[1].strip() if len(parts) > 1 else ""
    
    return {{
        **state,
        "next": next_agent,
        "instructions": instructions,
    }}'''

    @staticmethod
    def generate_subagent_code(
        agent_name: str,
        agent_description: str,
        llm_model: str = "gpt-5-mini",
        include_tools: bool = False,
    ) -> str:
        """Generate code for a specific subagent node.

        Args:
            agent_name: Name of the subagent
            agent_description: Description of agent's role and capabilities
            llm_model: LLM model to use
            include_tools: Whether to include tool binding example

        Returns:
            Python code string implementing the subagent node
        """
        node_name = agent_name.lower().replace(" ", "_").replace("-", "_")

        tools_code = ""
        llm_var = "llm"
        if include_tools:
            tools_code = """
    # Example: Bind tools to this agent
    # from langchain_community.tools import DuckDuckGoSearchRun
    # tools = [DuckDuckGoSearchRun()]
    tools = []  # TODO: replace with actual tool instances
    llm_with_tools = llm.bind_tools(tools)"""
            llm_var = "llm_with_tools"

        return f'''def {node_name}_node(state: WorkflowState) -> WorkflowState:
    """Subagent: {agent_name}.
    
    Role: {agent_description}
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    
    messages = state["messages"]
    instructions = state.get("instructions", "")
    task_results = state.get("task_results", {{}})
    
    # Initialize specialized LLM for this agent
    llm = ChatOpenAI(model="{llm_model}", temperature=0.7){tools_code}
    
    # Agent-specific system prompt
    system_prompt = SystemMessage(content="""You are {agent_name}.
{agent_description}

Execute the supervisor's instructions carefully and provide detailed results.""")
    
    # Build context
    user_prompt = HumanMessage(
        content=f"Instructions: {{instructions}}\\n\\nContext: {{messages[-1].content if messages else 'Begin task'}}"
    )
    
    # Execute agent task
    response = {llm_var}.invoke([system_prompt, user_prompt])
    
    # Update task results
    task_results["{agent_name}"] = response.content
    
    return {{
        **state,
        "task_results": task_results,
        "messages": messages + [HumanMessage(content=f"{agent_name} result: {{response.content}}")],
    }}'''

    @staticmethod
    def generate_graph_code(subagents: List[str], max_iterations: int = 10) -> str:
        """Generate complete subagents graph construction code.

        Args:
            subagents: List of subagent names
            max_iterations: Maximum iterations before forcing completion

        Returns:
            Python code string for building the complete graph
        """
        # Generate node additions
        node_additions = "\n".join(
            [
                f'workflow.add_node("{agent.lower().replace(" ", "_")}", {agent.lower().replace(" ", "_")}_node)'
                for agent in subagents
            ]
        )

        # Generate routing logic
        route_conditions = "\n    ".join(
            [
                f'elif next_agent == "{agent}":\n        return "{agent.lower().replace(" ", "_")}"'
                for agent in subagents
            ]
        )

        return f'''from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver


def supervisor_router(state: WorkflowState) -> str:
    """Route to next agent based on supervisor decision."""
    next_agent = state.get("next", "FINISH")
    
    if next_agent == "FINISH":
        return END
    {route_conditions}
    else:
        return END


# Create graph
workflow = StateGraph(WorkflowState)
memory = MemorySaver()

# Add supervisor node
workflow.add_node("supervisor", supervisor_node)

# Add subagent nodes
{node_additions}

# Connect start to supervisor
workflow.add_edge(START, "supervisor")

# Add conditional edges from supervisor
workflow.add_conditional_edges(
    "supervisor",
    supervisor_router,
    {{{", ".join([f'"{agent.lower().replace(" ", "_")}": "{agent.lower().replace(" ", "_")}"' for agent in subagents])}, "END": END}}
)

# All subagents return to supervisor for next decision
{chr(10).join([f'workflow.add_edge("{agent.lower().replace(" ", "_")}", "supervisor")' for agent in subagents])}

# Compile graph
graph = workflow.compile(checkpointer=memory)'''

    @staticmethod
    def generate_complete_example(
        subagents: List[str], subagent_descriptions: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate a complete, runnable subagents pattern example.

        Args:
            subagents: List of subagent names
            subagent_descriptions: Optional dict mapping agent names to descriptions

        Returns:
            Complete Python code for a supervisor-subagent workflow
        """
        if subagent_descriptions is None:
            subagent_descriptions = {
                agent: f"{agent} specialist agent" for agent in subagents
            }

        # Generate all components
        state_code = SubagentsPattern.generate_state_code()
        supervisor_code = SubagentsPattern.generate_supervisor_code(
            subagents, subagent_descriptions
        )

        subagent_nodes_code = "\n\n".join(
            [
                SubagentsPattern.generate_subagent_code(
                    agent, subagent_descriptions.get(agent, f"{agent} specialist")
                )
                for agent in subagents
            ]
        )

        graph_code = SubagentsPattern.generate_graph_code(subagents)

        return f'''"""
Subagents Pattern Example
Generated by LangGraph System Generator

This example demonstrates a supervisor-subagent workflow with:
- Supervisor: Coordinates and delegates tasks
- Subagents: {", ".join(subagents)}
"""

{state_code}


{supervisor_code}


{subagent_nodes_code}


{graph_code}


# Example usage
if __name__ == "__main__":
    import asyncio
    from langchain_core.messages import HumanMessage
    
    async def run_example():
        # Initialize state
        initial_state = {{
            "messages": [HumanMessage(content="Complete this multi-step task")],
            "next": "",
            "instructions": "",
            "task_results": {{}},
        }}
        
        # Run workflow
        config = {{"configurable": {{"thread_id": "example-thread"}}}}
        result = await graph.ainvoke(initial_state, config)
        
        print("Task Results:", result.get("task_results"))
        print("Final Messages:", result.get("messages")[-1].content)
    
    asyncio.run(run_example())
'''
