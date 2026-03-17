"""Critique/revise pattern generator aligned with modern LangGraph APIs."""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from langgraph_system_generator.patterns.utils import (
    build_llm_init,
    render_additional_fields,
)
from langgraph_system_generator.utils.config import ModelConfig


class CritiqueLoopPattern:
    """Template generator for critique-revise workflows."""

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate a TypedDict state schema for iterative refinement."""
        additional = render_additional_fields(additional_fields)
        return f'''import operator
from typing import Annotated, List
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class WorkflowState(TypedDict, total=False):
    """State schema for a critique-revise workflow."""

    messages: Annotated[List[BaseMessage], add_messages]
    current_draft: str
    critique_feedback: str
    revision_count: int
    quality_score: float
    approved: bool
    criteria: List[str]
    revision_history: Annotated[List[str], operator.add]
    final_output: str
{additional}'''

    @staticmethod
    def generate_generation_node_code(
        task_description: str = "Generate an initial draft for the request.",
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate the initial draft node."""
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
        return f'''from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def generate_node(state: WorkflowState) -> dict:
    """Produce the first draft for the workflow."""
    messages = state.get("messages", [])
    llm = {llm_init}
    response = llm.invoke([
        SystemMessage(
            content="""You are generating the first draft in a critique-revise workflow.

Task:
{task_description}
"""
        ),
        *messages,
    ])

    return {{
        "current_draft": response.content,
        "revision_count": state.get("revision_count", 0),
        "revision_history": [response.content],
        "messages": [AIMessage(content="Initial draft generated.")],
    }}'''

    @staticmethod
    def generate_critique_node_code(
        criteria: Optional[List[str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
    ) -> str:
        """Generate a critique node that routes with ``Command``."""
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config

        if criteria is None:
            criteria = [
                "Accuracy and factual correctness",
                "Clarity and readability",
                "Completeness",
                "Useful structure and examples",
            ]

        llm_init = build_llm_init(
            config.model,
            0,
            config.api_base,
            config.max_tokens,
        )
        criteria_lines = "\n".join(f"- {item}" for item in criteria)

        if use_structured_output:
            return f'''from typing import List, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field


class CritiqueAssessment(BaseModel):
    """Structured critique output."""

    quality_score: float = Field(ge=0.0, le=1.0)
    approved: bool
    strengths: List[str]
    weaknesses: List[str]
    suggestions: str


def critique_node(state: WorkflowState) -> Command[Literal["revise", "finalize"]]:
    """Assess the draft and decide whether to revise or finalize."""
    current_draft = state.get("current_draft", "")
    revision_count = state.get("revision_count", 0)
    llm = {llm_init}

    assessment = llm.with_structured_output(CritiqueAssessment).invoke([
        SystemMessage(
            content="""You are an expert reviewer in a critique-revise loop.

Evaluate the draft against:
{criteria_lines}
"""
        ),
        HumanMessage(content=f"Draft to review:\\n\\n{{current_draft}}"),
    ])

    feedback = "\\n".join([
        f"Quality score: {{assessment.quality_score:.2f}}",
        "Strengths:",
        *[f"- {{item}}" for item in assessment.strengths],
        "Weaknesses:",
        *[f"- {{item}}" for item in assessment.weaknesses],
        "Suggestions:",
        assessment.suggestions,
    ])

    should_finalize = assessment.approved or revision_count >= {max_revisions} or assessment.quality_score >= {min_quality_score}
    return Command(
        update={{
            "critique_feedback": feedback,
            "quality_score": assessment.quality_score,
            "approved": assessment.approved,
            "messages": [
                AIMessage(
                    content="Critique complete. Finalizing." if should_finalize else "Critique complete. Revising next."
                )
            ],
        }},
        goto="finalize" if should_finalize else "revise",
    )'''

        return f'''from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command


def critique_node(state: WorkflowState) -> Command[Literal["revise", "finalize"]]:
    """Fallback critique node that parses a delimited text response."""
    current_draft = state.get("current_draft", "")
    revision_count = state.get("revision_count", 0)
    llm = {llm_init}
    response = llm.invoke([
        SystemMessage(
            content="""Reply as SCORE|APPROVED_OR_REVISE|FEEDBACK while evaluating:
{criteria_lines}
"""
        ),
        HumanMessage(content=f"Draft to review:\\n\\n{{current_draft}}"),
    ])

    score_text, _, rest = response.content.partition("|")
    decision_text, _, feedback = rest.partition("|")
    quality_score = float(score_text or 0.0)
    approved = decision_text.strip().upper() == "APPROVED"
    should_finalize = approved or revision_count >= {max_revisions} or quality_score >= {min_quality_score}

    return Command(
        update={{
            "critique_feedback": feedback or response.content,
            "quality_score": quality_score,
            "approved": approved,
            "messages": [
                AIMessage(
                    content="Critique complete. Finalizing." if should_finalize else "Critique complete. Revising next."
                )
            ],
        }},
        goto="finalize" if should_finalize else "revise",
    )'''

    @staticmethod
    def generate_revise_node_code(
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate the revision node."""
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
        return f'''from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def revise_node(state: WorkflowState) -> dict:
    """Revise the draft using critique feedback."""
    llm = {llm_init}
    current_draft = state.get("current_draft", "")
    critique_feedback = state.get("critique_feedback", "")
    revision_count = state.get("revision_count", 0)

    response = llm.invoke([
        SystemMessage(
            content="""You are revising a draft after receiving critique feedback.
Address the critique directly while preserving good parts of the draft."""
        ),
        HumanMessage(
            content=f"Current draft:\\n\\n{{current_draft}}\\n\\nCritique feedback:\\n\\n{{critique_feedback}}"
        ),
    ])

    return {{
        "current_draft": response.content,
        "revision_count": revision_count + 1,
        "revision_history": [response.content],
        "messages": [AIMessage(content=f"Revision {{revision_count + 1}} complete.")],
    }}'''

    @staticmethod
    def generate_conditional_edge_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
    ) -> str:
        """Generate helper logic describing the critique loop exit conditions."""
        return f'''def should_continue(state: WorkflowState) -> str:
    """Return the next step for the critique loop."""
    approved = state.get("approved", False)
    revision_count = state.get("revision_count", 0)
    quality_score = state.get("quality_score", 0.0)

    if approved or revision_count >= {max_revisions} or quality_score >= {min_quality_score}:
        return "finalize"
    return "revise"'''

    @staticmethod
    def generate_graph_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
    ) -> str:
        """Generate the graph wiring for the critique loop."""
        conditional_helper = CritiqueLoopPattern.generate_conditional_edge_code(
            max_revisions=max_revisions,
            min_quality_score=min_quality_score,
        )
        return f'''from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


{conditional_helper}


def finalize_node(state: WorkflowState) -> dict:
    """Finalize the best available draft."""
    return {{
        "final_output": state.get("current_draft", ""),
        "messages": [],
    }}


workflow = StateGraph(WorkflowState)
checkpointer = InMemorySaver()

workflow.add_node("generate", generate_node)
workflow.add_node("critique", critique_node)
workflow.add_node("revise", revise_node)
workflow.add_node("finalize", finalize_node)

workflow.add_edge(START, "generate")
workflow.add_edge("generate", "critique")
workflow.add_edge("revise", "critique")
workflow.add_edge("finalize", END)

graph = workflow.compile(checkpointer=checkpointer)

MAX_REVISIONS = {max_revisions}
MIN_QUALITY_SCORE = {min_quality_score}'''

    @staticmethod
    def generate_complete_example(
        task_description: str = "Create a polished response for the user request.",
        criteria: Optional[List[str]] = None,
        max_revisions: int = 3,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        min_quality_score: float = 0.8,
    ) -> str:
        """Generate a full runnable critique-revise example."""
        state_code = CritiqueLoopPattern.generate_state_code()
        generate_code = CritiqueLoopPattern.generate_generation_node_code(
            task_description=task_description,
            model_config=model_config,
        )
        critique_code = CritiqueLoopPattern.generate_critique_node_code(
            criteria=criteria,
            model_config=model_config,
            max_revisions=max_revisions,
            min_quality_score=min_quality_score,
        )
        revise_code = CritiqueLoopPattern.generate_revise_node_code(
            model_config=model_config,
        )
        graph_code = CritiqueLoopPattern.generate_graph_code(
            max_revisions=max_revisions,
            min_quality_score=min_quality_score,
        )

        return f'''"""Critique-Revise Loop Pattern Example."""

from __future__ import annotations

import argparse
import asyncio

from langchain_core.messages import HumanMessage

{state_code}

{generate_code}

{critique_code}

{revise_code}

{graph_code}


def build_initial_state(user_request: str) -> WorkflowState:
    """Create an initial workflow state for the demo."""
    return {{
        "messages": [HumanMessage(content=user_request)],
        "criteria": {criteria or ["Accuracy", "Clarity", "Completeness"]},
        "revision_count": 0,
        "revision_history": [],
        "final_output": "",
    }}


async def run_example(user_request: str) -> WorkflowState:
    """Run the critique loop and return the final state."""
    return await graph.ainvoke(build_initial_state(user_request))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the critique-revise pattern example.")
    parser.add_argument("prompt", nargs="?", default="Write a concise best-practices guide for AI code reviews.")
    args = parser.parse_args()

    result = asyncio.run(run_example(args.prompt))
    print("Quality Score:", result.get("quality_score"))
    print("Revision Count:", result.get("revision_count"))
    print("Final Output:")
    print(result.get("final_output", ""))


if __name__ == "__main__":
    main()
'''
