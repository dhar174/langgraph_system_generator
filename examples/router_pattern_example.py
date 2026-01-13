"""Router Pattern Example - Multi-Agent Routing System

This example demonstrates how to use the RouterPattern from the
langgraph_system_generator pattern library to create a multi-agent system
with dynamic routing capabilities.

The router pattern is ideal for:
- Directing requests to specialized agents based on input classification
- Building modular systems with domain-specific expertise
- Implementing conditional agent execution

Usage:
    python examples/router_pattern_example.py

Requirements:
    - langchain-openai
    - langgraph
    - OPENAI_API_KEY environment variable
"""

import asyncio
import os
from typing import Dict

from langgraph_system_generator.patterns import RouterPattern


def generate_router_system():
    """Generate a complete router-based multi-agent system.
    
    This example creates a system with three specialized routes:
    - search: For information retrieval queries
    - analyze: For data analysis and interpretation
    - summarize: For text summarization tasks
    """
    
    # Define the routes and their purposes
    routes = ["search", "analyze", "summarize"]
    route_purposes = {
        "search": "Search and retrieve information from various sources",
        "analyze": "Analyze data, identify patterns, and provide insights",
        "summarize": "Condense long texts into concise summaries",
    }
    
    # Generate complete example code
    complete_code = RouterPattern.generate_complete_example(routes, route_purposes)
    
    print("=" * 80)
    print("Generated Router Pattern System")
    print("=" * 80)
    print(complete_code)
    print("=" * 80)
    
    return complete_code


def generate_custom_router():
    """Generate a custom router with specific configuration.
    
    This demonstrates how to customize individual components of the router pattern.
    """
    
    print("\n" + "=" * 80)
    print("Custom Router Configuration")
    print("=" * 80)
    
    # Step 1: Generate custom state with additional fields
    additional_fields = {
        "user_id": "Unique identifier for the user",
        "priority": "Request priority level (high, medium, low)",
    }
    state_code = RouterPattern.generate_state_code(additional_fields=additional_fields)
    print("\n1. Custom State Schema:")
    print("-" * 40)
    print(state_code)
    
    # Step 2: Generate router with structured output
    routes = ["technical_support", "billing", "general_inquiry"]
    router_code = RouterPattern.generate_router_node_code(
        routes=routes,
        llm_model="gpt-4",
        use_structured_output=True,
    )
    print("\n2. Router Node with Structured Output:")
    print("-" * 40)
    print(router_code[:500] + "...")
    
    # Step 3: Generate individual route handlers
    print("\n3. Route Handler Examples:")
    print("-" * 40)
    
    for route, purpose in {
        "technical_support": "Handle technical issues and troubleshooting",
        "billing": "Manage billing inquiries and payment issues",
        "general_inquiry": "Address general questions and information requests",
    }.items():
        route_code = RouterPattern.generate_route_node_code(route, purpose)
        print(f"\n{route.upper()} Handler:")
        print(route_code[:300] + "...")
    
    # Step 4: Generate graph construction code
    graph_code = RouterPattern.generate_graph_code(
        routes=routes,
        entry_point="router",
        use_conditional_edges=True,
    )
    print("\n4. Graph Construction:")
    print("-" * 40)
    print(graph_code[:500] + "...")


def demonstrate_integration():
    """Demonstrate how to integrate router pattern into existing workflows.
    
    This shows how pattern components can be used in custom agentic workflows.
    """
    
    print("\n" + "=" * 80)
    print("Integration Example - Using Pattern in Custom Workflow")
    print("=" * 80)
    
    # Generate just the state schema
    state_code = RouterPattern.generate_state_code()
    
    # You can now use this in your custom workflow
    print("\nGenerated State Schema (ready to use in your workflow):")
    print("-" * 40)
    print(state_code)
    
    # Generate router node for custom routes
    custom_routes = ["data_processing", "visualization", "export"]
    router_node_code = RouterPattern.generate_router_node_code(custom_routes)
    
    print("\nGenerated Router Node (integrate into your graph):")
    print("-" * 40)
    print(router_node_code[:400] + "...")
    
    print("\n" + "=" * 80)
    print("Integration Tips:")
    print("=" * 80)
    print("""
1. Copy the generated state code into your workflow file
2. Integrate the router_node function into your graph
3. Add custom route handlers using generate_route_node_code()
4. Build the graph using the generated graph construction code
5. Customize the LLM models, prompts, and logic as needed
    """)


def main():
    """Run all router pattern examples."""
    
    print("\n" + "=" * 80)
    print("LangGraph Router Pattern Examples")
    print("Pattern Library - langgraph_system_generator")
    print("=" * 80)
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  WARNING: OPENAI_API_KEY not found in environment")
        print("The generated code requires an API key to run.")
        print("Set it with: export OPENAI_API_KEY='your-key-here'\n")
    
    # Example 1: Generate complete system
    print("\n" + "=" * 80)
    print("Example 1: Complete Router System")
    print("=" * 80)
    print("Generating a fully functional router-based multi-agent system...")
    generate_router_system()
    
    # Example 2: Custom router configuration
    print("\n" + "=" * 80)
    print("Example 2: Custom Router Configuration")
    print("=" * 80)
    print("Demonstrating customization options...")
    generate_custom_router()
    
    # Example 3: Integration into existing workflows
    print("\n" + "=" * 80)
    print("Example 3: Integration with Custom Workflows")
    print("=" * 80)
    print("Showing how to use pattern components in your own code...")
    demonstrate_integration()
    
    print("\n" + "=" * 80)
    print("Examples Complete!")
    print("=" * 80)
    print("""
Next Steps:
1. Copy the generated code into your project
2. Customize the routes, prompts, and LLM models
3. Add your domain-specific logic to route handlers
4. Test the system with sample inputs
5. Deploy to production

For more information, see:
- Pattern documentation: docs/patterns.md
- LangGraph documentation: https://langchain-ai.github.io/langgraph/
    """)


if __name__ == "__main__":
    main()
