"""Critique-Revise Loop Pattern Example - Iterative Refinement System

This example demonstrates how to use the CritiqueLoopPattern from the
langgraph_system_generator pattern library to create systems with
iterative quality improvement through critique and revision cycles.

The critique-revise pattern is ideal for:
- Improving output quality through iteration
- Implementing quality control workflows
- Creating self-improving agent systems

Usage:
    python examples/critique_revise_pattern_example.py

Requirements:
    - langchain-openai
    - langgraph
    - OPENAI_API_KEY environment variable
"""

import asyncio
import os

from langgraph_system_generator.patterns import CritiqueLoopPattern


def generate_content_refinement_system():
    """Generate a content refinement system with critique-revise loops.
    
    This example creates a system for iteratively improving written content
    through cycles of generation, critique, and revision.
    """
    
    task_description = "Write a comprehensive technical blog post"
    criteria = [
        "Technical accuracy and correctness",
        "Clarity and readability for target audience",
        "Completeness of information",
        "Logical structure and flow",
        "Proper use of examples and code snippets",
    ]
    
    # Generate complete example code
    complete_code = CritiqueLoopPattern.generate_complete_example(
        task_description=task_description,
        criteria=criteria,
        max_revisions=3,
    )
    
    print("=" * 80)
    print("Generated Critique-Revise Content Refinement System")
    print("=" * 80)
    print(complete_code)
    print("=" * 80)
    
    return complete_code


def generate_custom_quality_system():
    """Generate a custom quality assurance system.
    
    This demonstrates customization of the critique-revise pattern.
    """
    
    print("\n" + "=" * 80)
    print("Custom Quality Assurance Configuration")
    print("=" * 80)
    
    # Step 1: Generate custom state
    additional_fields = {
        "target_audience": "Intended audience for the content",
        "content_type": "Type of content (blog, documentation, report)",
        "improvement_history": "Record of improvements made",
    }
    state_code = CritiqueLoopPattern.generate_state_code(
        additional_fields=additional_fields
    )
    print("\n1. Custom State Schema:")
    print("-" * 40)
    print(state_code)
    
    # Step 2: Generate generation node
    task = "Generate API documentation for a RESTful web service"
    generation_code = CritiqueLoopPattern.generate_generation_node_code(
        task_description=task, llm_model="gpt-4"
    )
    print("\n2. Generation Node:")
    print("-" * 40)
    print(generation_code[:500] + "...")
    
    # Step 3: Generate critique with custom criteria
    custom_criteria = [
        "API endpoint documentation completeness",
        "Request/response examples provided",
        "Error handling documented",
        "Authentication methods explained",
        "Rate limiting information included",
    ]
    
    critique_code = CritiqueLoopPattern.generate_critique_node_code(
        criteria=custom_criteria, use_structured_output=True
    )
    print("\n3. Critique Node with Structured Assessment:")
    print("-" * 40)
    print(critique_code[:600] + "...")
    
    # Step 4: Generate revision node
    revise_code = CritiqueLoopPattern.generate_revise_node_code(llm_model="gpt-4")
    print("\n4. Revision Node:")
    print("-" * 40)
    print(revise_code[:400] + "...")
    
    # Step 5: Generate conditional edge with custom thresholds
    conditional_code = CritiqueLoopPattern.generate_conditional_edge_code(
        max_revisions=5, min_quality_score=0.85
    )
    print("\n5. Quality Control Logic:")
    print("-" * 40)
    print(conditional_code[:400] + "...")
    print("\nQuality Thresholds:")
    print(f"  - Max Revisions: 5")
    print(f"  - Min Quality Score: 0.85 (85%)")


def demonstrate_iterative_improvement():
    """Demonstrate how the critique-revise loop improves output quality.
    
    Shows the iterative refinement process step by step.
    """
    
    print("\n" + "=" * 80)
    print("Iterative Improvement Workflow")
    print("=" * 80)
    
    print("""
The Critique-Revise Loop Pattern implements a continuous improvement cycle:

WORKFLOW STAGES:
═══════════════════════════════════════════════════════════════════════════

1. GENERATION
   ┌─────────────────────────────────────┐
   │ Initial content is generated based  │
   │ on the task description and user    │
   │ requirements                        │
   └─────────────────────────────────────┘
                    ↓

2. CRITIQUE
   ┌─────────────────────────────────────┐
   │ Expert critique evaluates the       │
   │ output against quality criteria:    │
   │ • Quality score (0.0 - 1.0)        │
   │ • Strengths identified             │
   │ • Weaknesses highlighted           │
   │ • Specific improvement suggestions │
   └─────────────────────────────────────┘
                    ↓
            ┌───────────────┐
            │ Quality Check │
            └───────────────┘
                    ↓
        ┌───────────────────────┐
        │  Approved?            │
        │  Quality >= Threshold?│
        │  Max Revisions?       │
        └───────────────────────┘
           ↓              ↓
          YES            NO
           ↓              ↓
          END         3. REVISE
                      ┌─────────────────────────────────────┐
                      │ Revision agent improves the draft:  │
                      │ • Addresses weaknesses              │
                      │ • Applies suggestions               │
                      │ • Preserves strengths              │
                      │ • Increments revision count        │
                      └─────────────────────────────────────┘
                                  ↓
                         (Loop back to CRITIQUE)

═══════════════════════════════════════════════════════════════════════════
    """)
    
    # Generate example with detailed logging
    print("\nGenerating example system with detailed workflow...")
    
    task = "Create a Python tutorial for beginners"
    criteria = [
        "Appropriate for beginners",
        "Clear explanations",
        "Working code examples",
        "Best practices included",
    ]
    
    graph_code = CritiqueLoopPattern.generate_graph_code(
        max_revisions=3, min_quality_score=0.8
    )
    
    print("\n✓ Generated critique-revise loop system")
    print(f"  - Task: {task}")
    print(f"  - Quality criteria: {len(criteria)} items")
    print(f"  - Max revisions: 3")
    print(f"  - Quality threshold: 0.8 (80%)")
    
    print("\nExpected Behavior:")
    print("-" * 40)
    print("""
Iteration 1:
  Generate → Critique (score: 0.6) → Needs Revision
  
Iteration 2:
  Revise → Critique (score: 0.75) → Needs Revision
  
Iteration 3:
  Revise → Critique (score: 0.85) → APPROVED ✓
  
Result: Final output with quality score ≥ 0.8
    """)


def demonstrate_quality_criteria():
    """Demonstrate different quality criteria for various use cases.
    
    Shows how to customize evaluation criteria for different content types.
    """
    
    print("\n" + "=" * 80)
    print("Quality Criteria Examples for Different Use Cases")
    print("=" * 80)
    
    use_cases = {
        "Technical Documentation": [
            "Accuracy of technical information",
            "Completeness of coverage",
            "Clear step-by-step instructions",
            "Working code examples",
            "Proper formatting and structure",
            "Searchable and navigable",
        ],
        "Marketing Content": [
            "Engaging and persuasive language",
            "Clear value proposition",
            "Target audience alignment",
            "Call-to-action effectiveness",
            "Brand voice consistency",
            "SEO optimization",
        ],
        "Research Reports": [
            "Data accuracy and citations",
            "Methodology transparency",
            "Logical argument flow",
            "Visual data representation",
            "Unbiased analysis",
            "Reproducible results",
        ],
        "Code Generation": [
            "Syntactic correctness",
            "Best practices adherence",
            "Code readability",
            "Error handling",
            "Performance considerations",
            "Security vulnerabilities check",
        ],
    }
    
    for use_case, criteria in use_cases.items():
        print(f"\n{use_case}:")
        print("-" * 40)
        for i, criterion in enumerate(criteria, 1):
            print(f"  {i}. {criterion}")
        
        # Generate example for this use case
        print(f"\n  Generating critique node for {use_case}...")
        critique_code = CritiqueLoopPattern.generate_critique_node_code(
            criteria=criteria, use_structured_output=True
        )
        print(f"  ✓ Generated with {len(criteria)} evaluation criteria")


def demonstrate_advanced_configurations():
    """Demonstrate advanced configuration options.
    
    Shows various ways to customize the pattern for specific needs.
    """
    
    print("\n" + "=" * 80)
    print("Advanced Configuration Options")
    print("=" * 80)
    
    configurations = [
        {
            "name": "Strict Quality Control",
            "max_revisions": 5,
            "min_quality_score": 0.95,
            "description": "High quality threshold with multiple revision opportunities",
        },
        {
            "name": "Fast Iteration",
            "max_revisions": 2,
            "min_quality_score": 0.7,
            "description": "Quick turnaround with acceptable quality",
        },
        {
            "name": "Single-Pass Review",
            "max_revisions": 1,
            "min_quality_score": 0.8,
            "description": "One revision attempt with moderate quality bar",
        },
        {
            "name": "Continuous Improvement",
            "max_revisions": 10,
            "min_quality_score": 0.9,
            "description": "Extensive refinement for critical content",
        },
    ]
    
    for config in configurations:
        print(f"\n{config['name']}:")
        print("-" * 40)
        print(f"Description: {config['description']}")
        print(f"Max Revisions: {config['max_revisions']}")
        print(f"Quality Threshold: {config['min_quality_score']} "
              f"({config['min_quality_score']*100}%)")
        
        # Generate conditional edge code
        edge_code = CritiqueLoopPattern.generate_conditional_edge_code(
            max_revisions=config["max_revisions"],
            min_quality_score=config["min_quality_score"],
        )
        print("✓ Generated conditional routing logic")


def main():
    """Run all critique-revise pattern examples."""
    
    print("\n" + "=" * 80)
    print("LangGraph Critique-Revise Loop Pattern Examples")
    print("Pattern Library - langgraph_system_generator")
    print("=" * 80)
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  WARNING: OPENAI_API_KEY not found in environment")
        print("The generated code requires an API key to run.")
        print("Set it with: export OPENAI_API_KEY='your-key-here'\n")
    
    # Example 1: Content refinement system
    print("\n" + "=" * 80)
    print("Example 1: Content Refinement System")
    print("=" * 80)
    print("Generating a content refinement system with critique loops...")
    generate_content_refinement_system()
    
    # Example 2: Custom quality system
    print("\n" + "=" * 80)
    print("Example 2: Custom Quality Assurance System")
    print("=" * 80)
    print("Demonstrating customization options...")
    generate_custom_quality_system()
    
    # Example 3: Iterative improvement
    print("\n" + "=" * 80)
    print("Example 3: Iterative Improvement Workflow")
    print("=" * 80)
    print("Understanding the improvement cycle...")
    demonstrate_iterative_improvement()
    
    # Example 4: Quality criteria
    print("\n" + "=" * 80)
    print("Example 4: Domain-Specific Quality Criteria")
    print("=" * 80)
    print("Customizing evaluation for different content types...")
    demonstrate_quality_criteria()
    
    # Example 5: Advanced configurations
    print("\n" + "=" * 80)
    print("Example 5: Advanced Configuration Patterns")
    print("=" * 80)
    print("Exploring different quality control strategies...")
    demonstrate_advanced_configurations()
    
    print("\n" + "=" * 80)
    print("Examples Complete!")
    print("=" * 80)
    print("""
Next Steps:
1. Copy the generated code into your project
2. Define quality criteria specific to your use case
3. Set appropriate max_revisions and min_quality_score
4. Customize generation and critique prompts
5. Test with sample inputs and monitor quality improvements

Pattern Advantages:
- Automated quality improvement through iteration
- Structured feedback with specific suggestions
- Configurable quality thresholds
- Prevents over-iteration with max_revisions
- Transparent quality scoring

Use Cases:
- Content creation and refinement
- Code generation with review cycles
- Documentation quality assurance
- Report writing and editing
- Any task requiring iterative improvement

For more information, see:
- Pattern documentation: docs/patterns.md
- LangGraph documentation: https://langchain-ai.github.io/langgraph/
    """)


if __name__ == "__main__":
    main()
