"""
LangGraph templates for common agent patterns.
"""

BASIC_AGENT_TEMPLATE = '''def {agent_name}_node(state: AgentState) -> AgentState:
    """
    {agent_description}
    """
    messages = state.get("messages", [])
    context = state.get("context", "")
    
    # Process the input
    # Add your LLM integration here
    result = "{agent_name} processed the input"
    
    return {{
        "messages": [HumanMessage(content=result)],
        "context": context
    }}
'''

SEQUENTIAL_WORKFLOW_TEMPLATE = '''# Create sequential workflow
workflow = StateGraph(AgentState)

{node_additions}

# Set up sequential flow
workflow.set_entry_point("{first_agent}")
{edge_additions}
workflow.add_edge("{last_agent}", END)

app = workflow.compile()
'''

PARALLEL_WORKFLOW_TEMPLATE = '''# Create parallel workflow
workflow = StateGraph(AgentState)

{node_additions}

# Set up parallel flow from entry point
workflow.set_entry_point("{entry_agent}")
{edge_additions}

app = workflow.compile()
'''

CONDITIONAL_WORKFLOW_TEMPLATE = '''# Create conditional workflow
def route_decision(state: AgentState) -> str:
    """Decide which path to take based on state."""
    # Add your routing logic here
    return "next_agent"

workflow = StateGraph(AgentState)

{node_additions}

workflow.set_entry_point("{entry_agent}")
workflow.add_conditional_edges(
    "{entry_agent}",
    route_decision,
    {conditional_edges}
)

app = workflow.compile()
'''

STATE_TEMPLATE = '''class AgentState(TypedDict):
    """State for the multiagent system."""
    messages: Annotated[List[BaseMessage], operator.add]
    context: str
{additional_fields}
'''

IMPORTS_TEMPLATE = '''"""
Generated LangGraph multiagent system.
"""

from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import operator
'''
