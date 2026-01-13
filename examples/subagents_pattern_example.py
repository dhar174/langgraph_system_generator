"""Subagents Pattern Example - Supervisor-Based Multi-Agent System

This example demonstrates how to use the SubagentsPattern from the
langgraph_system_generator pattern library to create a supervisor-subagent
coordination system.

The subagents pattern is ideal for:
- Decomposing complex tasks across specialized agents
- Coordinating multi-step workflows with a supervisor
- Building collaborative agent systems

Usage:
    python examples/subagents_pattern_example.py

Requirements:
    - langchain-openai
    - langgraph
    - OPENAI_API_KEY environment variable
"""

import os

from langgraph_system_generator.patterns import SubagentsPattern


def generate_research_team_system():
    """Generate a research team with supervisor coordination.
    
    This example creates a system with:
    - Supervisor: Coordinates the research workflow
    - Researcher: Gathers information and data
    - Analyst: Analyzes findings and identifies patterns
    - Writer: Creates comprehensive reports
    """
    
    subagents = ["researcher", "analyst", "writer"]
    subagent_descriptions = {
        "researcher": "Expert at finding and gathering information from multiple sources. "
                      "Skilled in web search, database queries, and literature review.",
        "analyst": "Specializes in data analysis, pattern recognition, and insight generation. "
                   "Provides statistical analysis and data interpretation.",
        "writer": "Professional technical writer who creates clear, comprehensive reports. "
                  "Excels at synthesizing complex information into readable content.",
    }
    
    # Generate complete example code
    complete_code = SubagentsPattern.generate_complete_example(
        subagents, subagent_descriptions
    )
    
    print("=" * 80)
    print("Generated Supervisor-Subagent Research Team")
    print("=" * 80)
    print(complete_code)
    print("=" * 80)
    
    return complete_code


def generate_custom_supervisor_system():
    """Generate a custom supervisor-subagent system.
    
    This demonstrates customization of the subagents pattern.
    """
    
    print("\n" + "=" * 80)
    print("Custom Supervisor-Subagent Configuration")
    print("=" * 80)
    
    # Step 1: Generate custom state
    additional_fields = {
        "task_priority": "Priority level of the current task",
        "deadline": "Task completion deadline",
    }
    state_code = SubagentsPattern.generate_state_code(additional_fields=additional_fields)
    print("\n1. Custom State Schema:")
    print("-" * 40)
    print(state_code)
    
    # Step 2: Generate supervisor with structured output
    subagents = ["data_collector", "data_processor", "report_generator"]
    subagent_descriptions = {
        "data_collector": "Collects raw data from various sources",
        "data_processor": "Cleans and processes collected data",
        "report_generator": "Generates final reports and visualizations",
    }
    
    supervisor_code = SubagentsPattern.generate_supervisor_code(
        subagents=subagents,
        subagent_descriptions=subagent_descriptions,
        llm_model="gpt-4",
        use_structured_output=True,
    )
    print("\n2. Supervisor Node with Structured Decision Making:")
    print("-" * 40)
    print(supervisor_code[:600] + "...")
    
    # Step 3: Generate subagent with tool integration
    print("\n3. Subagent with Tool Integration:")
    print("-" * 40)
    
    subagent_with_tools = SubagentsPattern.generate_subagent_code(
        agent_name="data_collector",
        agent_description="Collects data using various tools and APIs",
        llm_model="gpt-4",
        include_tools=True,
    )
    print(subagent_with_tools[:500] + "...")
    
    # Step 4: Generate graph construction
    graph_code = SubagentsPattern.generate_graph_code(
        subagents=subagents, max_iterations=10
    )
    print("\n4. Graph Construction with Max Iterations:")
    print("-" * 40)
    print(graph_code[:500] + "...")


def demonstrate_collaborative_workflow():
    """Demonstrate a collaborative content creation workflow.
    
    Shows how multiple agents work together under supervisor coordination.
    """
    
    print("\n" + "=" * 80)
    print("Collaborative Content Creation Workflow")
    print("=" * 80)
    
    # Define content creation team
    subagents = ["topic_researcher", "outline_creator", "content_writer", "editor"]
    descriptions = {
        "topic_researcher": "Researches the topic and gathers relevant information and sources",
        "outline_creator": "Creates structured outlines based on research findings",
        "content_writer": "Writes the main content following the outline",
        "editor": "Reviews and refines the content for quality and clarity",
    }
    
    # Generate the system
    SubagentsPattern.generate_complete_example(subagents, descriptions)
    
    print("\nGenerated Collaborative Content Creation System:")
    print("-" * 40)
    print("System includes:")
    print(f"  - 1 Supervisor agent (coordinates workflow)")
    print(f"  - {len(subagents)} Specialized subagents:")
    for agent in subagents:
        print(f"    • {agent}: {descriptions[agent]}")
    print("\n" + "=" * 40)
    print("Sample workflow:")
    print("""
    1. User submits content request to supervisor
    2. Supervisor assigns topic_researcher to gather information
    3. topic_researcher returns findings to supervisor
    4. Supervisor assigns outline_creator to structure content
    5. outline_creator returns outline to supervisor
    6. Supervisor assigns content_writer to write draft
    7. content_writer returns draft to supervisor
    8. Supervisor assigns editor to review and refine
    9. editor returns final content
    10. Supervisor marks task as FINISH
    """)
    
    # Show key components
    print("\nKey Code Components Generated:")
    print("-" * 40)
    
    # Show supervisor decision logic
    supervisor = SubagentsPattern.generate_supervisor_code(
        subagents, descriptions, use_structured_output=True
    )
    print("\nSupervisor Decision Structure:")
    if "class SupervisorDecision" in supervisor:
        print("✓ Structured output with Pydantic models")
        print("✓ Next agent selection with reasoning")
        print("✓ Specific instructions for each agent")
    
    print("\nSubagent Capabilities:")
    print("✓ Access to full conversation history")
    print("✓ Specialized system prompts")
    print("✓ Result tracking in shared state")
    print("✓ Seamless supervisor handoff")


def demonstrate_scalability():
    """Demonstrate how the pattern scales to many agents.
    
    Shows that the pattern can handle complex workflows with many subagents.
    """
    
    print("\n" + "=" * 80)
    print("Scalability Example - Large Agent Team")
    print("=" * 80)
    
    # Create a larger team
    large_team = [
        "requirements_analyst",
        "architect",
        "backend_developer",
        "frontend_developer",
        "database_designer",
        "qa_tester",
        "security_auditor",
        "documentation_writer",
    ]
    
    print(f"\nGenerating system with {len(large_team)} specialized agents...")
    
    # Generate graph code for large team
    graph_code = SubagentsPattern.generate_graph_code(
        subagents=large_team, max_iterations=20
    )
    
    print("\n✓ Successfully generated supervisor system for large team")
    print(f"  - Team size: {len(large_team)} agents")
    print(f"  - Max iterations: 20")
    print(f"  - Conditional routing: ✓")
    print(f"  - Supervisor coordination: ✓")
    
    print("\nScalability Features:")
    print("-" * 40)
    print("""
1. Dynamic Agent Selection: Supervisor chooses appropriate agent per task
2. Iteration Control: Prevents infinite loops with max_iterations
3. State Management: Shared state tracks all agent results
4. Flexible Workflow: Agents can be invoked in any order
5. Easy Extension: Add new agents without changing core logic
    """)


def main():
    """Run all subagents pattern examples."""
    
    print("\n" + "=" * 80)
    print("LangGraph Subagents Pattern Examples")
    print("Pattern Library - langgraph_system_generator")
    print("=" * 80)
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  WARNING: OPENAI_API_KEY not found in environment")
        print("The generated code requires an API key to run.")
        print("Set it with: export OPENAI_API_KEY='your-key-here'\n")
    
    # Example 1: Research team system
    print("\n" + "=" * 80)
    print("Example 1: Research Team with Supervisor")
    print("=" * 80)
    print("Generating a research team coordination system...")
    generate_research_team_system()
    
    # Example 2: Custom configuration
    print("\n" + "=" * 80)
    print("Example 2: Custom Supervisor Configuration")
    print("=" * 80)
    print("Demonstrating customization options...")
    generate_custom_supervisor_system()
    
    # Example 3: Collaborative workflow
    print("\n" + "=" * 80)
    print("Example 3: Collaborative Workflow")
    print("=" * 80)
    print("Creating a content creation workflow...")
    demonstrate_collaborative_workflow()
    
    # Example 4: Scalability
    print("\n" + "=" * 80)
    print("Example 4: Scalability with Many Agents")
    print("=" * 80)
    print("Demonstrating large-scale agent coordination...")
    demonstrate_scalability()
    
    print("\n" + "=" * 80)
    print("Examples Complete!")
    print("=" * 80)
    print("""
Next Steps:
1. Copy the generated code into your project
2. Customize the subagent descriptions and capabilities
3. Add tools to subagents as needed
4. Adjust max_iterations based on your workflow complexity
5. Test with various task types

Pattern Advantages:
- Clear task delegation and coordination
- Modular agent design (easy to add/remove agents)
- Supervisor maintains workflow state and decisions
- Agents can be specialized for specific tasks
- Scalable to large teams

For more information, see:
- Pattern documentation: docs/patterns.md
- LangGraph documentation: https://langchain-ai.github.io/langgraph/
    """)


if __name__ == "__main__":
    main()
