"""Critique/revise pattern generator aligned with modern LangGraph APIs."""

from __future__ import annotations

import keyword
import textwrap
from typing import Any, List, Optional, Union

from langgraph_system_generator.patterns.utils import (
    build_llm_init,
    render_additional_fields,
)
from langgraph_system_generator.utils.config import ModelConfig


class CritiqueLoopPattern:
    """Template generator for critique-revise loop patterns."""

    @staticmethod
    def _quote_string(value: str) -> str:
        """Return a Python-safe string literal for generated code."""
        return repr(value)

    @staticmethod
    def _quote_string_list(values: List[str]) -> str:
        """Return a Python-safe list literal for generated code."""
        return "[" + ", ".join(repr(value) for value in values) + "]"

    @staticmethod
    def _validate_field_name(field_name: str) -> str:
        """Validate that a generated state field name is a safe identifier."""
        if not field_name.isidentifier():
            raise ValueError(
                f"Invalid additional field name {field_name!r}; expected a Python identifier"
            )
        if keyword.iskeyword(field_name):
            raise ValueError(
                f"Invalid additional field name {field_name!r}; Python keywords are not allowed"
            )
        return field_name

    @staticmethod
    def _coerce_float_setting(value: Any, setting_name: str) -> float:
        """Parse a float setting with a clear error for invalid inputs."""
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{setting_name} must be numeric, got {value!r} ({type(value).__name__})"
            ) from exc

    @staticmethod
    def generate_state_code(
        additional_fields: Optional[dict[str, str]] = None,
        include_human_feedback: bool = False,
        include_failure_tracking: bool = False,
    ) -> str:
        """Generate state schema code for critique-revise pattern."""
        validated_fields = {}
        if additional_fields:
            for field_name, description in additional_fields.items():
                safe_name = CritiqueLoopPattern._validate_field_name(field_name)
                validated_fields[safe_name] = description

        built_in_fields = [
            "    current_draft: str  # Current version of the output being refined",
            "    critique_feedback: str  # Latest critique and suggestions",
            "    revision_count: int  # Number of revisions completed",
            "    quality_score: float  # Quality assessment score (0-1)",
            "    approved: bool  # Whether output meets quality standards",
            "    criteria: List[str]  # Quality criteria to evaluate",
            "    draft_history: Annotated[List[DraftSnapshot], operator.add]  # Historical draft snapshots with quality scores",
            "    revision_history: Annotated[List[str], operator.add]",
            "    final_output: str",
        ]
        if include_human_feedback:
            built_in_fields.append(
                "    human_feedback_handler: Callable[..., Dict[str, Any]]  # Trusted callback returning quality_score, approved, and feedback"
            )
        if include_failure_tracking:
            built_in_fields.append(
                "    previous_quality_score: float  # Previous critique score for improvement checks"
            )

        additional_rendered = render_additional_fields(validated_fields)
        additional_section = additional_rendered.rstrip()
        field_lines = "\n".join(built_in_fields)
        if additional_section:
            field_lines = f"{field_lines}\n{additional_section}"

        return textwrap.dedent(
            f'''import operator
from typing import Annotated, Any, Callable, Dict, List, TypedDict

from langgraph.graph import MessagesState


class DraftSnapshot(TypedDict):
    """Stored draft candidate with its measured quality."""

    content: str
    quality_score: float


class WorkflowState(MessagesState):
    """State schema for critique-revise loop workflow."""

{field_lines}
'''
        )

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
        safe_task_description = CritiqueLoopPattern._quote_string(task_description)

        return textwrap.dedent(
            f'''from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def generate_node(state: WorkflowState) -> dict:
    """Generate the initial draft for the workflow."""
    messages = state.get("messages", [])
    revision_count = state.get("revision_count", 0)
    task_description = {safe_task_description}
    llm = {llm_init}

    prompt_messages = [
        SystemMessage(
            content=f"""You are an expert content generator.
{{task_description}}
Return a polished draft that can be reviewed and revised."""
        ),
        *messages,
    ]

    response = llm.invoke(prompt_messages)
    return {{
        "current_draft": response.content,
        "revision_count": revision_count,
        "revision_history": [response.content],
        "messages": [AIMessage(content="Initial draft generated.")],
    }}
'''
        )

    @staticmethod
    def generate_critique_node_code(
        criteria: Optional[List[str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
        feedback_source: str = "automated",
    ) -> str:
        """Generate code for critique/review node."""
        if feedback_source not in {"automated", "human"}:
            raise ValueError(
                "feedback_source must be either 'automated' or 'human'"
            )

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

        criteria_literal = CritiqueLoopPattern._quote_string_list(criteria)

        if feedback_source == "human":
            return textwrap.dedent(
                '''import math

from langchain_core.messages import HumanMessage


def critique_node(state: WorkflowState) -> dict:
    """Collect human feedback from trusted application code and normalize it."""
    current_draft = state.get("current_draft", "")
    messages = state["messages"]
    criteria = state.get("criteria", [])
    revision_count = state.get("revision_count", 0)
    previous_quality_score = state.get("quality_score", 0.0)
    feedback_handler = state.get("human_feedback_handler")

    if feedback_handler is None:
        raise ValueError(
            "Human feedback mode requires a 'human_feedback_handler' callback in state"
        )
    if not callable(feedback_handler):
        raise TypeError("human_feedback_handler must be callable")

    review = feedback_handler(
        draft=current_draft,
        criteria=criteria,
        revision_count=revision_count,
        previous_feedback=state.get("critique_feedback", ""),
    )

    if not isinstance(review, dict):
        raise TypeError("human_feedback_handler must return a dict")

    quality_score = float(review.get("quality_score", previous_quality_score))
    approved = review.get("approved", False)
    if not isinstance(approved, bool):
        raise TypeError("human_feedback_handler must return a boolean 'approved' value")
    if not math.isfinite(quality_score) or not 0.0 <= quality_score <= 1.0:
        raise ValueError(
            "human_feedback_handler must return a finite quality_score between 0.0 and 1.0"
        )

    feedback_text = str(review.get("feedback", "")).strip()
    if not feedback_text:
        feedback_text = (
            "Human reviewer requested another revision without additional notes."
        )

    criteria_summary = (
        chr(10).join([f"- {criterion}" for criterion in criteria])
        if criteria
        else "- No explicit criteria provided"
    )
    normalized_feedback = f"""Quality Score: {quality_score}
Status: {"APPROVED" if approved else "NEEDS REVISION"}

Human Review:
{feedback_text}

Criteria Reviewed:
{criteria_summary}"""

    return {
        **state,
        "critique_feedback": normalized_feedback,
        "quality_score": quality_score,
        "approved": approved,
        "previous_quality_score": previous_quality_score,
        "messages": [
            HumanMessage(content=f"Human critique: {normalized_feedback}")
        ],
    }
'''
            )

        llm_init = build_llm_init(
            config.model,
            0,
            config.api_base,
            config.max_tokens,
        )

        if use_structured_output:
            return textwrap.dedent(
                f'''from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


class CritiqueAssessment(BaseModel):
    """Structured critique output."""

    quality_score: float = Field(ge=0.0, le=1.0)
    approved: bool
    strengths: List[str]
    weaknesses: List[str]
    suggestions: str


def critique_node(state: WorkflowState) -> dict:
    """Assess the draft and return critique feedback."""
    current_draft = state.get("current_draft", "")
    messages = state["messages"]
    criteria = state.get("criteria", []) or {criteria_literal}
    previous_quality_score = state.get("quality_score", 0.0)
    criteria_summary = chr(10).join([f"- {{criterion}}" for criterion in criteria])

    llm = {llm_init}
    structured_llm = llm.with_structured_output(CritiqueAssessment)
    assessment = structured_llm.invoke(
        [
            SystemMessage(
                content=(
                    "You are an expert critic and reviewer. Evaluate the draft against:\\n"
                    f"{{criteria_summary}}"
                )
            ),
            HumanMessage(content=f"Review this output:\\n\\n{{current_draft}}"),
        ]
    )

    feedback = "\\n".join(
        [
            f"Quality Score: {{assessment.quality_score}}",
            f"Status: {{'APPROVED' if assessment.approved else 'NEEDS REVISION'}}",
            "Strengths:",
            *[f"- {{item}}" for item in assessment.strengths],
            "Weaknesses:",
            *[f"- {{item}}" for item in assessment.weaknesses],
            "Suggestions:",
            assessment.suggestions,
        ]
    )

    return {{
        **state,
        "critique_feedback": feedback,
        "quality_score": assessment.quality_score,
        "approved": assessment.approved,
        "previous_quality_score": previous_quality_score,
        "messages": [HumanMessage(content=f"Critique: {{feedback}}")],
    }}
'''
            )

        return textwrap.dedent(
            f'''from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def critique_node(state: WorkflowState) -> dict:
    """Fallback critique node that parses a delimited text response."""
    current_draft = state.get("current_draft", "")
    messages = state["messages"]
    criteria = state.get("criteria", []) or {criteria_literal}
    previous_quality_score = state.get("quality_score", 0.0)
    criteria_summary = chr(10).join([f"- {{criterion}}" for criterion in criteria])

    llm = {llm_init}
    response = llm.invoke(
        [
            SystemMessage(
                content=(
                    "You are an expert critic. Evaluate the draft against:\\n"
                    f"{{criteria_summary}}\\n\\n"
                    "Format: SCORE|APPROVED or NEEDS_REVISION|feedback"
                )
            ),
            HumanMessage(content=f"Review:\\n{{current_draft}}"),
        ]
    )
    parts = response.content.split("|", 2)

    score = float(parts[0]) if len(parts) > 0 else 0.5
    approved = parts[1].strip().upper() == "APPROVED" if len(parts) > 1 else False
    feedback = parts[2] if len(parts) > 2 else response.content

    return {{
        **state,
        "critique_feedback": feedback,
        "quality_score": score,
        "approved": approved,
        "previous_quality_score": previous_quality_score,
        "messages": [HumanMessage(content=f"Critique: {{feedback}}")],
    }}
'''
        )

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
        return textwrap.dedent(
            f'''from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


def revise_node(state: WorkflowState) -> dict:
    """Revise the draft using critique feedback."""
    llm = {llm_init}
    current_draft = state.get("current_draft", "")
    critique_feedback = state.get("critique_feedback", "")
    quality_score = state.get("quality_score", 0.0)
    revision_count = state.get("revision_count", 0)

    response = llm.invoke(
        [
            SystemMessage(
                content="""You are revising a draft after receiving critique feedback.
Address the critique directly while preserving good parts of the draft."""
            ),
            HumanMessage(
                content=f"Current draft:\\n\\n{{current_draft}}\\n\\nCritique feedback:\\n\\n{{critique_feedback}}"
            ),
        ]
    )

    return {{
        "draft_history": (
            [{{"content": current_draft, "quality_score": quality_score}}]
            if current_draft
            else []
        ),
        "current_draft": response.content,
        "revision_count": revision_count + 1,
        "revision_history": [response.content],
        "messages": [AIMessage(content=f"Revision {{revision_count + 1}} complete.")],
    }}
'''
        )

    @staticmethod
    def generate_conditional_edge_code(
        max_revisions: int = 5,
        min_quality_score: float = 0.8,
        failure_conditions: Optional[dict[str, Any]] = None,
    ) -> str:
        """Generate conditional edge routing code."""
        failure_conditions = failure_conditions or {}
        fail_on_max_revisions = bool(
            failure_conditions.get("fail_on_max_revisions", False)
        )
        fail_on_no_improvement = bool(
            failure_conditions.get("fail_on_no_improvement", False)
        )
        min_quality_improvement = CritiqueLoopPattern._coerce_float_setting(
            failure_conditions.get("min_quality_improvement", 0.0),
            "min_quality_improvement",
        )
        fail_on_missing_feedback = bool(
            failure_conditions.get("fail_on_missing_feedback", False)
        )

        return textwrap.dedent(
            f'''def should_continue(state: WorkflowState) -> str:
    """Determine if we should continue revising or finish."""
    approved = state.get("approved", False)
    revision_count = state.get("revision_count", 0)
    quality_score = state.get("quality_score", 0.0)
    previous_quality_score = state.get("previous_quality_score", 0.0)
    critique_feedback = state.get("critique_feedback", "")
    quality_delta = quality_score - previous_quality_score

    if {fail_on_missing_feedback} and not critique_feedback.strip():
        return "missing_feedback"
    if approved:
        return "finish"
    if quality_score >= {min_quality_score}:
        return "finish"
    if (
        {fail_on_no_improvement}
        and revision_count > 0
        and quality_delta <= {min_quality_improvement}
    ):
        return "no_improvement"
    if revision_count >= {max_revisions}:
        return "max_revisions_failed" if {fail_on_max_revisions} else "max_revisions_reached"
    return "revise"
'''
        )

    @staticmethod
    def generate_graph_code(
        max_revisions: int = 5,
        min_quality_score: float = 0.8,
        failure_conditions: Optional[dict[str, Any]] = None,
    ) -> str:
        """Generate the graph wiring for the critique loop."""
        conditional_helper = CritiqueLoopPattern.generate_conditional_edge_code(
            max_revisions=max_revisions,
            min_quality_score=min_quality_score,
            failure_conditions=failure_conditions,
        )
        return textwrap.dedent(
            f'''from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


{conditional_helper}


def finalize_node(state: WorkflowState) -> dict:
    """Finalize the best available draft."""
    current_draft = state.get("current_draft", "")
    quality_score = state.get("quality_score", 0.0)
    revision_count = state.get("revision_count", 0)
    draft_history = list(state.get("draft_history", []))

    if current_draft:
        draft_history.append(
            {{
                "content": current_draft,
                "quality_score": quality_score,
            }}
        )

    final_output = current_draft
    if revision_count >= {max_revisions} and draft_history:
        ranked_drafts = max(
            enumerate(draft_history),
            key=lambda item: (
                float(item[1].get("quality_score", 0.0)),
                item[0],
            ),
        )
        best_draft = ranked_drafts[1]
        final_output = best_draft.get("content", current_draft)

    return {{
        "final_output": final_output,
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
workflow.add_conditional_edges(
    "critique",
    should_continue,
    {{
        "finish": "finalize",
        "missing_feedback": END,
        "no_improvement": END,
        "max_revisions_failed": END,
        "max_revisions_reached": "finalize",
        "revise": "revise",
    }},
)
workflow.add_edge("revise", "critique")
workflow.add_edge("finalize", END)

graph = workflow.compile(checkpointer=checkpointer)
'''
        )

    @staticmethod
    def generate_complete_example(
        task_description: str = "Create a polished response for the user request.",
        criteria: Optional[List[str]] = None,
        max_revisions: int = 5,
        min_quality_score: float = 0.8,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
        feedback_source: str = "automated",
        failure_conditions: Optional[dict[str, Any]] = None,
    ) -> str:
        """Generate a complete, runnable critique-revise loop example."""
        if criteria is None:
            criteria = [
                "Accuracy and correctness",
                "Clarity and readability",
                "Completeness",
                "Structure and organization",
            ]

        task_description_literal = CritiqueLoopPattern._quote_string(task_description)
        criteria_literal = CritiqueLoopPattern._quote_string_list(criteria)
        include_human_feedback = feedback_source == "human"

        state_code = CritiqueLoopPattern.generate_state_code(
            include_human_feedback=include_human_feedback,
            include_failure_tracking=bool(failure_conditions),
        )
        generate_code = CritiqueLoopPattern.generate_generation_node_code(
            task_description=task_description,
            model_config=model_config,
        )
        critique_code = CritiqueLoopPattern.generate_critique_node_code(
            criteria=criteria,
            model_config=model_config,
            use_structured_output=use_structured_output,
            feedback_source=feedback_source,
        )
        revise_code = CritiqueLoopPattern.generate_revise_node_code(
            model_config=model_config,
        )
        graph_code = CritiqueLoopPattern.generate_graph_code(
            max_revisions=max_revisions,
            min_quality_score=min_quality_score,
            failure_conditions=failure_conditions,
        )

        human_feedback_example = ""
        human_state_fields = ""
        if feedback_source == "human":
            human_feedback_example = '''
def collect_human_feedback(
    draft: str,
    criteria: List[str],
    revision_count: int,
    previous_feedback: str,
) -> dict:
    """Example human feedback hook for plug-and-play workflows."""
    return {
        "quality_score": 0.65 if revision_count == 0 else 0.9,
        "approved": revision_count >= 1,
        "feedback": (
            "Tighten the introduction, clarify the example, and improve the ending."
        ),
    }
'''
            human_state_fields = '\n        "human_feedback_handler": collect_human_feedback,'

        failure_state_fields = ""
        if failure_conditions:
            failure_state_fields = '\n        "previous_quality_score": 0.0,'

        return textwrap.dedent(
            f'''"""
Critique-Revise Loop Pattern Example
Generated by LangGraph System Generator
"""

from __future__ import annotations

import argparse
import asyncio

from langchain_core.messages import HumanMessage

{state_code}

{generate_code}

{critique_code}

{revise_code}

{human_feedback_example}

{graph_code}


def build_initial_state(user_request: str) -> WorkflowState:
    """Create an initial workflow state for the demo."""
    return {{
        "messages": [HumanMessage(content=user_request)],
        "current_draft": "",
        "critique_feedback": "",
        "revision_count": 0,
        "quality_score": 0.0,
        "approved": False,
        "criteria": {criteria_literal},
        "draft_history": [],
        "revision_history": [],
        "final_output": "",{failure_state_fields}{human_state_fields}
    }}


async def run_example(user_request: str) -> WorkflowState:
    """Run the critique loop and return the final state."""
    config = {{"configurable": {{"thread_id": "example-thread"}}}}
    return await graph.ainvoke(build_initial_state(user_request), config=config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the critique-revise pattern example.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default={task_description_literal},
    )
    args = parser.parse_args()

    result = asyncio.run(run_example(args.prompt))
    print("Quality Score:", result.get("quality_score"))
    print("Revision Count:", result.get("revision_count"))
    print("Final Output:")
    print(result.get("final_output", ""))


if __name__ == "__main__":
    main()
'''
        )
