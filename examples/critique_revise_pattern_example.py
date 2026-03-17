"""Runnable critique-revise loop demo using current LangGraph APIs.

The graph defaults to ``stub`` mode so it can run offline. The same graph can
use ``ChatOpenAI`` in ``live`` mode for real structured critiques.

Examples:
    python examples/critique_revise_pattern_example.py --mode stub
    python examples/critique_revise_pattern_example.py --mode live --input "Draft onboarding docs"
"""

from __future__ import annotations

import argparse
import operator
import os
from typing import Annotated, List, Literal, Optional

from langgraph_system_generator.patterns import CritiqueLoopPattern
from langgraph_system_generator.utils.config import ModelConfig


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
        task_description=task,
        model_config=ModelConfig(model="gpt-4", temperature=0.3),
    )
    response = model.invoke(
        [
            SystemMessage(
                content="You write concise product documentation that is actionable and easy to skim."
            ),
            HumanMessage(content=prompt),
        ]
    )
    print("\n3. Critique Node with Structured Assessment:")
    print("-" * 40)
    print(critique_code[:600] + "...")
    
    # Step 4: Generate revision node
    revise_code = CritiqueLoopPattern.generate_revise_node_code(
        model_config=ModelConfig(model="gpt-4", temperature=0.7)
    )
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

    human_review_code = CritiqueLoopPattern.generate_complete_example(
        task_description="Prepare a customer-facing release announcement",
        feedback_source="human",
        failure_conditions={"fail_on_missing_feedback": True},
    )
    print("\n6. Human Feedback Variant:")
    print("-" * 40)
    print(human_review_code[:600] + "...")


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
    
    CritiqueLoopPattern.generate_graph_code(
        max_revisions=3, min_quality_score=0.8
    )


def build_critique_graph(mode: ExampleMode = "stub"):
    """Build a runnable critique-revise graph."""

    _require_live_api_key(mode)

    def generate_node(state: CritiqueState):
        user_input = state["messages"][0].content if state["messages"] else DEFAULT_INPUT
        revision_count = state.get("revision_count", 0)
        latest_feedback = state.get("latest_feedback", "")
        draft = (
            _generate_stub_draft(user_input, revision_count, latest_feedback)
            if mode == "stub"
            else _generate_live_draft(user_input, revision_count, latest_feedback)
        )
        label = "Initial draft" if revision_count == 0 else f"Revision {revision_count}"
        return {
            "draft": draft,
            "messages": [AIMessage(content=f"{label} generated.\n{draft}")],
        }

    def critique_node(state: CritiqueState):
        draft = state.get("draft", "")
        revision_count = state.get("revision_count", 0)
        assessment = (
            _critique_stub(revision_count, draft)
            if mode == "stub"
            else _critique_live(draft)
        )
        feedback = (
            f"Score: {assessment.quality_score}\n"
            f"Approved: {assessment.approved}\n"
            f"Strengths: {', '.join(assessment.strengths)}\n"
            f"Improvements: {', '.join(assessment.improvements) or 'None'}\n"
            f"Revision focus: {assessment.revision_focus}"
        )
        return {
            "latest_feedback": feedback,
            "quality_score": assessment.quality_score,
            "approved": assessment.approved,
            "critique_history": [feedback],
            "messages": [AIMessage(content=f"Critique complete.\n{feedback}")],
        }

    def revise_node(state: CritiqueState):
        return {
            "revision_count": state.get("revision_count", 0) + 1,
        }

    def finish_node(state: CritiqueState):
        return {
            "final_output": state.get("draft", ""),
            "messages": [AIMessage(content=f"Workflow complete.\n{state.get('draft', '')}")],
        }

    def should_continue(state: CritiqueState) -> Literal["revise", "finish"]:
        if state.get("approved", False):
            return "finish"
        if state.get("revision_count", 0) >= MAX_REVISIONS:
            return "finish"
        if state.get("quality_score", 0.0) >= MIN_QUALITY_SCORE:
            return "finish"
        return "revise"

    workflow = StateGraph(CritiqueState)
    workflow.add_node("generate", generate_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("revise", revise_node)
    workflow.add_node("finish", finish_node)
    workflow.add_edge(START, "generate")
    workflow.add_edge("generate", "critique")
    workflow.add_conditional_edges(
        "critique",
        should_continue,
        {
            "revise": "revise",
            "finish": "finish",
        },
    )
    workflow.add_edge("revise", "generate")
    workflow.add_edge("finish", END)
    return workflow.compile()


def run_critique_example(
    user_input: str = DEFAULT_INPUT,
    mode: ExampleMode = "stub",
) -> CritiqueState:
    """Execute the critique-revise example and return the final graph state."""

    graph = build_critique_graph(mode)
    return graph.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "critique_history": [],
            "draft": "",
            "latest_feedback": "",
            "quality_score": 0.0,
            "approved": False,
            "revision_count": 0,
            "final_output": "",
        }
    )


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["stub", "live"], default="stub")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    args = parser.parse_args(argv)

    result = run_critique_example(args.input, args.mode)

    print("Critique-Revise Pattern Example")
    print(f"Mode: {args.mode}")
    print(f"Revision count: {result['revision_count']}")
    print(f"Quality score: {result['quality_score']}")
    print(f"Approved: {result['approved']}")
    print("Critique history:")
    for entry in result["critique_history"]:
        print("-")
        print(entry)
    print("Final output:")
    print(result["final_output"])

    if args.mode == "stub":
        print("Live mode note: rerun with --mode live and OPENAI_API_KEY to use ChatOpenAI.")


if __name__ == "__main__":
    main()
