"""Router pattern for multi-agent workflows.

This module provides templates and code generators for implementing
router-based LangGraph architectures where a central router node
dynamically dispatches requests to specialized agent nodes.

Architecture:
    The router pattern implements a hub-and-spoke architecture:
    
        START -> router_node -> [route_1, route_2, ..., route_n] -> END
    
    The router node analyzes incoming requests and directs them to the
    appropriate specialized agent based on content, intent, or other criteria.
    Each route handler is optimized for a specific domain or task type.

Key Features:
    - Dynamic routing based on LLM classification
    - Support for structured output (type-safe routing decisions)
    - Extensible state management with custom fields
    - Conditional edge routing for complex workflows
    - Configurable LLM models for different performance/cost tradeoffs

Use Cases:
    - Customer support systems with specialized agents (billing, technical, general)
    - Multi-domain question answering (search, calculation, reasoning)
    - Content processing pipelines (analysis, summarization, translation)
    - Task delegation in multi-agent systems

Example Usage:
    Basic router pattern generation:
    
        >>> from langgraph_system_generator.patterns.router import RouterPattern
        >>>
        >>> # Generate complete workflow
        >>> routes = ["search", "analyze", "summarize"]
        >>> route_purposes = {
        ...     "search": "Search for information from various sources",
        ...     "analyze": "Analyze data and identify patterns",
        ...     "summarize": "Create concise summaries of content"
        ... }
        >>> code = RouterPattern.generate_complete_example(routes, route_purposes)
        >>> # Save to file or execute
        >>> with open("my_router_workflow.py", "w") as f:
        ...     f.write(code)
    
    Custom state with additional fields:
    
        >>> # Add custom tracking fields
        >>> custom_fields = {
        ...     "user_id": "User identifier for personalization",
        ...     "priority": "Request priority level",
        ...     "metadata": "Additional context"
        ... }
        >>> state_code = RouterPattern.generate_state_code(
        ...     additional_fields=custom_fields
        ... )
    
    Generate individual components:
    
        >>> # Generate just the router node
        >>> from langgraph_system_generator.utils.config import ModelConfig
        >>> config = ModelConfig(model="gpt-5-mini", temperature=0.5)
        >>> router_code = RouterPattern.generate_router_node_code(
        ...     routes=["search", "analyze"],
        ...     model_config=config,
        ...     use_structured_output=True
        ... )
        >>>
        >>> # Generate a specific route handler
        >>> route_code = RouterPattern.generate_route_node_code(
        ...     route_name="search",
        ...     route_purpose="Perform web searches and retrieve information",
        ...     model_config=config
        ... )

Integration with Generated Workflows:
    The generated code is production-ready and can be integrated into
    larger systems. Each pattern method generates syntactically valid
    Python code that can be saved to files, executed dynamically, or
    incorporated into notebook cells.

See Also:
    - SubagentsPattern: For supervisor-coordinated multi-agent workflows
    - CritiqueLoopPattern: For iterative refinement workflows
    - examples/router_pattern_example.py: Complete working examples
"""

from typing import Dict, List, Optional, Union

from langgraph_system_generator.utils.config import ModelConfig


def _build_llm_init(model: str, temperature: float, api_base: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
    """Build ChatOpenAI initialization string with optional parameters."""
    params = [f'model="{model}"', f'temperature={temperature}']
    if api_base:
        params.append(f'base_url="{api_base}"')
    if max_tokens:
        params.append(f'max_tokens={max_tokens}')
    return f"ChatOpenAI({', '.join(params)})"


class RouterPattern:
    """Template generator for router-based multi-agent patterns.

    The router pattern is ideal for workflows where:
    - A central dispatcher routes requests to specialized agents
    - Each route handles a specific type of request or domain
    - Routing logic is based on input classification
    - Agents can be executed conditionally based on input

    Architecture:
        START -> router_node -> [route_a_node, route_b_node, ...] -> END
    """

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate state schema code for router pattern.

        Args:
            additional_fields: Optional dict mapping field names to descriptions

        Returns:
            Python code string defining the RouterState class
        """
        additional = ""
        if additional_fields:
            for field_name, description in additional_fields.items():
                additional += f"    {field_name}: str  # {description}\n"

        return f'''from typing import Annotated, Dict
from langgraph.graph import MessagesState


class WorkflowState(MessagesState):
    """State schema for router-based workflow.
    
    Inherits from MessagesState to maintain conversation history.
    Additional fields track routing decisions and agent outputs.
    """
    route: str  # Selected route/agent for processing
    results: Dict[str, str]  # Results from each route/agent
    final_output: str  # Aggregated final output
{additional}'''

    @staticmethod
    def generate_router_node_code(
        routes: List[str],
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
    ) -> str:
        """Generate router node implementation code.

        Args:
            routes: List of available route names
            model_config: ModelConfig instance or dict with model settings
            use_structured_output: Whether to use structured output for routing

        Returns:
            Python code string implementing the router node
        """
        # Handle model_config parameter
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config
        
        llm_model = config.model
        # Router decisions are classification-like; use deterministic temperature
        temperature = 0
        api_base = config.api_base
        max_tokens = config.max_tokens
        
        llm_init = _build_llm_init(llm_model, temperature, api_base, max_tokens)
        
        routes_str = ", ".join([f'"{r}"' for r in routes]) if routes else '"default"'
        routes_list_str = "\n".join(
            [f"- {route}: Handle {route}-related requests" for route in routes]
        ) if routes else "- default: Default route handler"

        if use_structured_output:
            return f'''from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from typing import Literal


class RouteDecision(BaseModel):
    """Structured output for route classification."""
    route: Literal[{routes_str}] = Field(
        description="The selected route for processing this request"
    )
    reasoning: str = Field(
        description="Explanation for why this route was selected"
    )


def router_node(state: WorkflowState) -> WorkflowState:
    """Routes requests to appropriate specialist based on input classification.
    
    Analyzes the user's message and determines which specialized agent
    should handle the request based on content and intent.
    """
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    
    # Initialize LLM with structured output
    llm = {llm_init}
    structured_llm = llm.with_structured_output(RouteDecision)
    
    # Classification prompt
    classification_prompt = f"""Analyze the following request and determine which route should handle it.

Available routes:
{routes_list_str}

User request: {{last_message}}

Select the most appropriate route and explain your reasoning."""
    
    # Get classification
    decision = structured_llm.invoke([HumanMessage(content=classification_prompt)])
    
    return {{
        **state,
        "route": decision.route,
        "messages": messages + [HumanMessage(content=f"Routing to: {{decision.route}} ({{decision.reasoning}})")],
    }}'''
        else:
            return f'''from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def router_node(state: WorkflowState) -> WorkflowState:
    """Routes requests to appropriate specialist based on input classification."""
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    
    llm = {llm_init}
    
    # Classification prompt
    system_prompt = SystemMessage(content=f"""You are a routing classifier.
Analyze requests and select the appropriate route from: {routes_str}
Respond with ONLY the route name.""")
    
    user_prompt = HumanMessage(content=f"Request: {{last_message}}\\nRoute:")
    
    # Get classification
    response = llm.invoke([system_prompt, user_prompt])
    selected_route = response.content.strip().lower()
    
    # Validate route
    valid_routes = [r.lower() for r in routes]
    if not valid_routes:
        raise ValueError("Router configuration must include at least one route.")
    if selected_route not in valid_routes:
        selected_route = valid_routes[0]  # Default to first route
    
    return {{
        **state,
        "route": selected_route,
    }}'''

    @staticmethod
    def generate_route_node_code(
        route_name: str,
        route_purpose: str,
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate code for a specific route handler node.

        Args:
            route_name: Name of the route/agent
            route_purpose: Description of what this route handles
            model_config: ModelConfig instance or dict with model settings

        Returns:
            Python code string implementing the route node
        """
        # Handle model_config parameter
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config
        
        llm_model = config.model
        temperature = config.temperature
        api_base = config.api_base
        max_tokens = config.max_tokens
        
        llm_init = _build_llm_init(llm_model, temperature, api_base, max_tokens)
        
        node_name = route_name.lower().replace(" ", "_").replace("-", "_")

        return f'''def {node_name}_node(state: WorkflowState) -> WorkflowState:
    """Handle {route_name} requests.
    
    Purpose: {route_purpose}
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    
    messages = state["messages"]
    
    # Initialize specialized LLM for this route
    llm = {llm_init}
    
    # System prompt for this specialist
    system_prompt = SystemMessage(content="""You are a {route_name} specialist.
{route_purpose}

Provide helpful, accurate, and detailed responses.""")
    
    # Get response from specialist
    response = llm.invoke([system_prompt] + messages)
    
    # Update state with results
    results = state.get("results", {{}})
    results["{route_name}"] = response.content
    
    return {{
        **state,
        "results": results,
        "final_output": response.content,
        "messages": messages + [response],
    }}'''

    @staticmethod
    def generate_graph_code(
        routes: List[str],
        entry_point: str = "router",
        use_conditional_edges: bool = True,
    ) -> str:
        """Generate complete router graph construction code.

        Args:
            routes: List of route names
            entry_point: Entry point node name
            use_conditional_edges: Whether to use conditional edges for routing

        Returns:
            Python code string for building the complete graph
        """
        # Generate node additions
        node_additions = "\n".join(
            [
                f'workflow.add_node("{route.lower().replace(" ", "_")}", {route.lower().replace(" ", "_")}_node)'
                for route in routes
            ]
        )

        if use_conditional_edges:
            # Generate conditional routing function
            route_conditions = "\n    ".join(
                [
                    f'if route == "{route}":\n        return "{route.lower().replace(" ", "_")}"'
                    for route in routes
                ]
            )

            return f'''from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver


def route_decision(state: WorkflowState) -> str:
    """Determine next node based on router decision."""
    route = state.get("route", "")
    {route_conditions}
    return END


# Create graph
workflow = StateGraph(WorkflowState)
memory = MemorySaver()

# Add router node
workflow.add_node("router", router_node)

# Add route-specific nodes
{node_additions}

# Connect start to router
workflow.add_edge(START, "router")

# Add conditional edges from router to routes
workflow.add_conditional_edges(
    "router",
    route_decision,
    {{{", ".join([f'"{route.lower().replace(" ", "_")}": "{route.lower().replace(" ", "_")}"' for route in routes])}, "END": END}}
)

# Connect all routes to END
{chr(10).join([f'workflow.add_edge("{route.lower().replace(" ", "_")}", END)' for route in routes])}

# Compile graph
graph = workflow.compile(checkpointer=memory)'''
        else:
            # Simple edge-based routing (less common, included for completeness)
            return f"""from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

# Create graph
workflow = StateGraph(WorkflowState)
memory = MemorySaver()

# Add router node
workflow.add_node("router", router_node)

# Add route-specific nodes
{node_additions}

# Connect nodes
workflow.add_edge(START, "router")
{chr(10).join([f'workflow.add_edge("router", "{route.lower().replace(" ", "_")}")' for route in routes])}
{chr(10).join([f'workflow.add_edge("{route.lower().replace(" ", "_")}", END)' for route in routes])}

# Compile graph
graph = workflow.compile(checkpointer=memory)"""

    @staticmethod
    def generate_complete_example(
        routes: List[str],
        route_purposes: Optional[Dict[str, str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate a complete, runnable router pattern example.

        Args:
            routes: List of route names
            route_purposes: Optional dict mapping route names to their purposes
            model_config: ModelConfig instance or dict with model settings

        Returns:
            Complete Python code for a router-based workflow
        """
        if route_purposes is None:
            route_purposes = {
                route: f"Handle {route}-related tasks" for route in routes
            }

        # Generate all components
        state_code = RouterPattern.generate_state_code()
        router_code = RouterPattern.generate_router_node_code(routes, model_config=model_config)

        route_nodes_code = "\n\n".join(
            [
                RouterPattern.generate_route_node_code(
                    route, route_purposes.get(route, f"Handle {route}-related tasks"),
                    model_config=model_config
                )
                for route in routes
            ]
        )

        graph_code = RouterPattern.generate_graph_code(routes)

        return f'''"""
Router Pattern Example
Generated by LangGraph System Generator

This example demonstrates a router-based workflow with the following routes:
{chr(10).join([f"- {route}: {route_purposes.get(route, f'Handle {route}-related tasks')}" for route in routes])}
"""

{state_code}


{router_code}


{route_nodes_code}


{graph_code}


# Example usage
if __name__ == "__main__":
    import asyncio
    from langchain_core.messages import HumanMessage
    
    async def run_example():
        # Initialize state
        initial_state = {{
            "messages": [HumanMessage(content="Your request here")],
            "route": "",
            "results": {{}},
            "final_output": "",
        }}
        
        # Run workflow
        config = {{"configurable": {{"thread_id": "example-thread"}}}}
        result = await graph.ainvoke(initial_state, config)
        
        print("Final Output:", result.get("final_output"))
        print("Route Taken:", result.get("route"))
    
    asyncio.run(run_example())
'''
