"""
LangGraph code generator module.

Generates LangGraph Python code for multiagent systems based on user prompts.
"""

from typing import Dict, List, Optional, Any


class LangGraphGenerator:
    """
    Generates LangGraph-based multiagent systems.
    
    This class handles the generation of Python code that uses LangGraph
    to create multiagent systems based on user-defined constraints and prompts.
    """
    
    def __init__(self):
        """Initialize the LangGraph generator."""
        self.agents = []
        self.edges = []
        self.state_schema = {}
    
    def generate_from_prompt(self, prompt: str) -> str:
        """
        Generate LangGraph code from a text prompt.
        
        Args:
            prompt: User prompt describing the desired system
            
        Returns:
            Generated Python code as a string
        """
        # Parse the prompt to extract system requirements
        requirements = self._parse_prompt(prompt)
        
        # Generate the code structure
        code = self._generate_code(requirements)
        
        return code
    
    def _parse_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Parse the user prompt to extract system requirements.
        
        Args:
            prompt: User prompt
            
        Returns:
            Dictionary containing parsed requirements
        """
        # Basic parsing - can be extended with LLM integration
        requirements = {
            "agents": self._extract_agents(prompt),
            "workflow": self._extract_workflow(prompt),
            "state": self._extract_state_requirements(prompt)
        }
        return requirements
    
    def _extract_agents(self, prompt: str) -> List[str]:
        """Extract agent definitions from prompt."""
        # Placeholder - should be enhanced with NLP/LLM
        agents = []
        prompt_lower = prompt.lower()
        
        # Look for common agent keywords
        if "researcher" in prompt_lower:
            agents.append("researcher")
        if "writer" in prompt_lower:
            agents.append("writer")
        if "reviewer" in prompt_lower or "review" in prompt_lower:
            agents.append("reviewer")
        
        # Default to a basic agent if none found
        if not agents:
            agents.append("agent")
        
        return agents
    
    def _extract_workflow(self, prompt: str) -> str:
        """Extract workflow pattern from prompt."""
        prompt_lower = prompt.lower()
        
        if "sequential" in prompt_lower or "pipeline" in prompt_lower:
            return "sequential"
        elif "parallel" in prompt_lower:
            return "parallel"
        elif "conditional" in prompt_lower:
            return "conditional"
        else:
            return "sequential"  # Default
    
    def _extract_state_requirements(self, prompt: str) -> Dict[str, str]:
        """Extract state schema requirements from prompt."""
        # Placeholder for state extraction
        return {
            "messages": "List[BaseMessage]",
            "context": "str"
        }
    
    def _generate_code(self, requirements: Dict[str, Any]) -> str:
        """
        Generate the actual LangGraph code.
        
        Args:
            requirements: Parsed requirements dictionary
            
        Returns:
            Generated Python code
        """
        code_parts = []
        
        # Add imports
        code_parts.append(self._generate_imports())
        code_parts.append("\n")
        
        # Add state definition
        code_parts.append(self._generate_state_definition(requirements["state"]))
        code_parts.append("\n")
        
        # Add agent nodes
        for agent in requirements["agents"]:
            code_parts.append(self._generate_agent_node(agent))
            code_parts.append("\n")
        
        # Add graph construction
        code_parts.append(self._generate_graph_construction(
            requirements["agents"],
            requirements["workflow"]
        ))
        
        return "\n".join(code_parts)
    
    def _generate_imports(self) -> str:
        """Generate import statements."""
        return '''"""
Generated LangGraph multiagent system.
"""

from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import operator
'''
    
    def _generate_state_definition(self, state_schema: Dict[str, str]) -> str:
        """Generate the state TypedDict definition."""
        state_fields = []
        for field_name, field_type in state_schema.items():
            if field_name == "messages":
                state_fields.append(f'    {field_name}: Annotated[{field_type}, operator.add]')
            else:
                state_fields.append(f'    {field_name}: {field_type}')
        
        fields_str = "\n".join(state_fields)
        return f'''
class AgentState(TypedDict):
    """State for the multiagent system."""
{fields_str}
'''
    
    def _generate_agent_node(self, agent_name: str) -> str:
        """Generate code for an agent node."""
        # Use explicit string concatenation to avoid f-string escaping confusion
        code = f'''
def {agent_name}_node(state: AgentState) -> AgentState:
    """
    {agent_name.capitalize()} agent node.
    
    Processes the current state and returns updated state.
    """
    messages = state.get("messages", [])
    context = state.get("context", "")
    
    # Define the prompt for this agent
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a {agent_name} agent. '''
        code += '{context}"),\n'
        code += '''        ("human", "{input}")
    ])
    
    # Process the messages
    # Note: You'll need to configure with your LLM
    # llm = ChatOpenAI()  # or your preferred LLM
    # chain = prompt | llm | StrOutputParser()
    # result = chain.invoke({"input": messages[-1].content if messages else ""})
    
    result = f"{agent_name.capitalize()} processed the input"
    
    return {
        "messages": [HumanMessage(content=result)],
        "context": context
    }
'''
        return code
    
    def _generate_graph_construction(self, agents: List[str], workflow: str) -> str:
        """Generate the graph construction code."""
        code = '''
# Create the graph
workflow = StateGraph(AgentState)

'''
        
        # Add nodes
        for agent in agents:
            code += f'workflow.add_node("{agent}", {agent}_node)\n'
        
        code += "\n# Define the workflow\n"
        
        # Add edges based on workflow type
        if workflow == "sequential" and len(agents) > 1:
            code += f'workflow.set_entry_point("{agents[0]}")\n'
            for i in range(len(agents) - 1):
                code += f'workflow.add_edge("{agents[i]}", "{agents[i+1]}")\n'
            code += f'workflow.add_edge("{agents[-1]}", END)\n'
        elif workflow == "parallel":
            code += f'workflow.set_entry_point("{agents[0]}")\n'
            for agent in agents[1:]:
                code += f'workflow.add_edge("{agents[0]}", "{agent}")\n'
                code += f'workflow.add_edge("{agent}", END)\n'
        else:  # Simple sequential or single agent
            code += f'workflow.set_entry_point("{agents[0]}")\n'
            if len(agents) == 1:
                code += f'workflow.add_edge("{agents[0]}", END)\n'
            else:
                for i in range(len(agents) - 1):
                    code += f'workflow.add_edge("{agents[i]}", "{agents[i+1]}")\n'
                code += f'workflow.add_edge("{agents[-1]}", END)\n'
        
        code += '''
# Compile the graph
app = workflow.compile()

# Example usage
if __name__ == "__main__":
    initial_state = {
        "messages": [HumanMessage(content="Start the workflow")],
        "context": "Initial context"
    }
    
    result = app.invoke(initial_state)
    print("Final result:", result)
'''
        
        return code
