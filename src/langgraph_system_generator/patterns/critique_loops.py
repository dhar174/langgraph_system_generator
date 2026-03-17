"""Critique-revise loop pattern for iterative refinement workflows.

This module provides templates and code generators for implementing
critique-revise loop LangGraph architectures where output is iteratively
improved through cycles of generation, critique, and revision.

Example Usage:
    >>> from langgraph_system_generator.patterns.critique_loops import CritiqueLoopPattern
    >>>
    >>> # Generate state code
    >>> state_code = CritiqueLoopPattern.generate_state_code()
    >>>
    >>> # Generate critique node
    >>> critique_code = CritiqueLoopPattern.generate_critique_node_code()
    >>>
    >>> # Generate complete graph code
    >>> graph_code = CritiqueLoopPattern.generate_graph_code(max_revisions=3)
"""

import keyword
from typing import Any, Dict, List, Optional, Union

from langgraph_system_generator.patterns.utils import build_llm_init
from langgraph_system_generator.utils.config import ModelConfig


class CritiqueLoopPattern:
    """Template generator for critique-revise loop patterns.

    The critique-revise pattern is ideal for workflows where:
    - Output quality needs iterative refinement
    - Expert critique guides improvements
    - Multiple revision cycles are acceptable
    - Quality standards must be met before completion

        Architecture:
            START -> generate -> critique -> [revise -> critique] -> END
            (loops until approval or max iterations)

    The generated critique node can be configured for:
    - Automated LLM-based critique
    - Human feedback injected through a callback in workflow state
    - Custom failure conditions for stalled or incomplete revisions
    """

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
        additional_fields: Optional[Dict[str, str]] = None,
        include_human_feedback: bool = False,
        include_failure_tracking: bool = False,
    ) -> str:
        """Generate state schema code for critique-revise pattern.

        Args:
            additional_fields: Optional dict mapping field names to descriptions
            include_human_feedback: Whether to include state for human-review hooks
            include_failure_tracking: Whether to include failure-tracking fields

        Returns:
            Python code string defining the WorkflowState class
        """
        built_in = ""
        if include_human_feedback:
            built_in += (
                "    human_feedback_handler: Callable[..., Dict[str, Any]]  # Trusted callback returning quality_score, approved, and feedback\n"
            )
        if include_failure_tracking:
            built_in += (
                "    previous_quality_score: float  # Previous critique score for improvement checks\n"
            )

        additional = ""
        if additional_fields:
            for field_name, description in additional_fields.items():
                safe_name = CritiqueLoopPattern._validate_field_name(field_name)
                safe_description = str(description).replace("\n", " ").replace("\r", " ")
                additional += f"    {safe_name}: str  # {safe_description}\n"

        return f'''from typing import Annotated, Any, Callable, Dict, List
from langgraph.graph import MessagesState


class WorkflowState(MessagesState):
    """State schema for critique-revise loop workflow.
    
    Inherits from MessagesState to maintain conversation history.
    Additional fields track the revision process and quality assessment.
    """
    current_draft: str  # Current version of the output being refined
    critique_feedback: str  # Latest critique and suggestions
    revision_count: int  # Number of revisions completed
    quality_score: float  # Quality assessment score (0-1)
    approved: bool  # Whether output meets quality standards
    criteria: List[str]  # Quality criteria to evaluate
{built_in}{additional}'''

    @staticmethod
    def generate_generation_node_code(
        task_description: str = "Generate initial output",
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate code for initial generation node.

        Args:
            task_description: Description of what to generate
            model_config: ModelConfig instance or dict with model settings

        Returns:
            Python code string implementing the generation node
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
        safe_task_description = CritiqueLoopPattern._quote_string(task_description)
        
        llm_init = build_llm_init(llm_model, temperature, api_base, max_tokens)
        
        return f'''def generate_node(state: WorkflowState) -> WorkflowState:
    """Generate initial output or first draft for the configured task."""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    
    messages = state["messages"]
    revision_count = state.get("revision_count", 0)
    task_description = {safe_task_description}
    
    # Initialize LLM
    llm = {llm_init}
    
    # Generation prompt
    system_prompt = SystemMessage(content=f"""You are an expert content generator.
{{task_description}}

Create high-quality output that is clear, accurate, and well-structured.""")
    
    user_request = messages[-1].content if messages else "Generate output"
    user_prompt = HumanMessage(content=f"Request: {{user_request}}")
    
    # Generate content
    response = llm.invoke([system_prompt, user_prompt])
    
    return {{
        **state,
        "current_draft": response.content,
        "revision_count": revision_count,
        "messages": messages + [response],
    }}'''

    @staticmethod
    def generate_critique_node_code(
        criteria: Optional[List[str]] = None,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
        feedback_source: str = "automated",
    ) -> str:
        """Generate code for critique/review node.

        Args:
            criteria: Optional list of quality criteria to evaluate
            model_config: ModelConfig instance or dict with model settings
            use_structured_output: Whether to use structured output
            feedback_source: Either "automated" for LLM critique or "human"
                for callback-driven feedback collection

        Returns:
            Python code string implementing the critique node
        """
        if feedback_source not in {"automated", "human"}:
            raise ValueError(
                "feedback_source must be either 'automated' or 'human'"
            )

        # Handle model_config parameter
        if model_config is None:
            config = ModelConfig()
        elif isinstance(model_config, dict):
            config = ModelConfig.from_dict(model_config)
        else:
            config = model_config
        
        llm_model = config.model
        # Critique uses temperature=0 for consistent, deterministic evaluation
        api_base = config.api_base
        max_tokens = config.max_tokens
        
        llm_init = build_llm_init(llm_model, 0, api_base, max_tokens)
        
        if criteria is None:
            criteria = [
                "Accuracy and correctness",
                "Clarity and readability",
                "Completeness",
                "Structure and organization",
            ]

        criteria_literal = CritiqueLoopPattern._quote_string_list(criteria)

        if feedback_source == "human":
            return '''import math

from langchain_core.messages import HumanMessage


def critique_node(state: WorkflowState) -> WorkflowState:
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
        "messages": messages + [
            HumanMessage(content=f"Human critique: {normalized_feedback}")
        ],
    }'''

        if use_structured_output:
            return f'''from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import List


class CritiqueAssessment(BaseModel):
    """Structured output for critique assessment."""
    quality_score: float = Field(
        description="Overall quality score from 0.0 to 1.0",
        ge=0.0,
        le=1.0
    )
    approved: bool = Field(
        description="Whether the output meets quality standards"
    )
    strengths: List[str] = Field(
        description="Positive aspects of the output"
    )
    weaknesses: List[str] = Field(
        description="Areas that need improvement"
    )
    suggestions: str = Field(
        description="Specific suggestions for revision"
    )


def critique_node(state: WorkflowState) -> WorkflowState:
    """Critique the current draft and provide feedback.
    
    Evaluates output against quality criteria and provides
    constructive feedback for improvement.
    """
    current_draft = state.get("current_draft", "")
    messages = state["messages"]
    criteria = state.get("criteria", []) or {criteria_literal}
    previous_quality_score = state.get("quality_score", 0.0)
    criteria_summary = chr(10).join([f"- {{criterion}}" for criterion in criteria])
    
    # Initialize LLM with structured output
    llm = {llm_init}
    structured_llm = llm.with_structured_output(CritiqueAssessment)
    
    # Critique prompt
    system_prompt = f"""You are an expert critic and reviewer.
Evaluate the output against these quality criteria:
{{criteria_summary}}
 
Provide honest, constructive feedback that will help improve the output.
Be specific about what needs to change."""
    
    user_prompt = f"""Review this output:

{{current_draft}}

Provide your assessment."""
    
    # Get critique
    assessment = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ])
    
    # Format feedback
    feedback = f"""Quality Score: {{assessment.quality_score}}
Status: {{"APPROVED" if assessment.approved else "NEEDS REVISION"}}

Strengths:
{{chr(10).join([f"- {{s}}" for s in assessment.strengths])}}

Weaknesses:
{{chr(10).join([f"- {{w}}" for w in assessment.weaknesses])}}

Suggestions for improvement:
{{assessment.suggestions}}"""
    
    return {{
        **state,
        "critique_feedback": feedback,
        "quality_score": assessment.quality_score,
        "approved": assessment.approved,
        "previous_quality_score": previous_quality_score,
        "messages": messages + [HumanMessage(content=f"Critique: {{feedback}}")],
    }}'''
        else:
            return f'''from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def critique_node(state: WorkflowState) -> WorkflowState:
    """Critique the current draft and provide feedback."""
    current_draft = state.get("current_draft", "")
    messages = state["messages"]
    criteria = state.get("criteria", []) or {criteria_literal}
    previous_quality_score = state.get("quality_score", 0.0)
    criteria_summary = chr(10).join([f"- {{criterion}}" for criterion in criteria])
    
    llm = {llm_init}
    
    # Critique prompt
    system_prompt = SystemMessage(content=f"""You are an expert critic.
Evaluate against:
{{criteria_summary}}
 
Format: SCORE|APPROVED or NEEDS_REVISION|feedback""")
    
    user_prompt = HumanMessage(content=f"Review:\\n{{current_draft}}")
    
    # Get critique
    response = llm.invoke([system_prompt, user_prompt])
    parts = response.content.split("|", 2)
    
    score = float(parts[0]) if len(parts) > 0 else 0.5
    approved = parts[1].strip() == "APPROVED" if len(parts) > 1 else False
    feedback = parts[2] if len(parts) > 2 else response.content
    
    return {{
        **state,
        "critique_feedback": feedback,
        "quality_score": score,
        "approved": approved,
        "previous_quality_score": previous_quality_score,
        "messages": messages + [HumanMessage(content=f"Critique: {{feedback}}")],
    }}'''

    @staticmethod
    def generate_revise_node_code(model_config: Optional[Union[ModelConfig, dict]] = None) -> str:
        """Generate code for revision node.

        Args:
            model_config: ModelConfig instance or dict with model settings

        Returns:
            Python code string implementing the revision node
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
        
        llm_init = build_llm_init(llm_model, temperature, api_base, max_tokens)
        
        return f'''def revise_node(state: WorkflowState) -> WorkflowState:
    """Revise the draft based on critique feedback.
    
    Takes the critique and applies suggested improvements to create
    a better version of the output.
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    
    current_draft = state.get("current_draft", "")
    critique_feedback = state.get("critique_feedback", "")
    revision_count = state.get("revision_count", 0)
    messages = state["messages"]
    
    # Initialize LLM
    llm = {llm_init}
    
    # Revision prompt
    system_prompt = SystemMessage(content="""You are an expert editor and reviser.
Your job is to improve the draft based on the critique feedback.

Guidelines:
- Address all weaknesses mentioned in the feedback
- Preserve strengths from the original
- Make specific, targeted improvements
- Maintain the overall intent and structure""")
    
    user_prompt = HumanMessage(content=f"""Current draft:
{{current_draft}}

Critique feedback:
{{critique_feedback}}

Revise the draft to address the feedback.""")
    
    # Generate revision
    response = llm.invoke([system_prompt, user_prompt])
    
    return {{
        **state,
        "current_draft": response.content,
        "revision_count": revision_count + 1,
        "messages": messages + [HumanMessage(content=f"Revision {{revision_count + 1}}: {{response.content}}")],
    }}'''

    @staticmethod
    def generate_conditional_edge_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
        failure_conditions: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate conditional edge routing code.

        Args:
            max_revisions: Maximum number of revision cycles
            min_quality_score: Minimum quality score to approve
            failure_conditions: Optional failure controls. Supported keys:
                fail_on_max_revisions, fail_on_no_improvement,
                min_quality_improvement, fail_on_missing_feedback

        Returns:
            Python code string for conditional routing logic
        """
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

        return f'''def should_continue(state: WorkflowState) -> str:
    """Determine if we should continue revising or finish.
    
    Decision criteria:
    - If approved: finish
    - If critique feedback is missing and required: terminate early
    - If max revisions reached: finish (even if not perfect)
    - If quality stagnates and improvement is required: terminate early
    - Otherwise: continue revising
    """
    approved = state.get("approved", False)
    revision_count = state.get("revision_count", 0)
    quality_score = state.get("quality_score", 0.0)
    previous_quality_score = state.get("previous_quality_score", 0.0)
    critique_feedback = state.get("critique_feedback", "")
    quality_delta = quality_score - previous_quality_score

    if {fail_on_missing_feedback} and not critique_feedback.strip():
        return "missing_feedback"
    
    # Check approval status
    if approved:
        return "finish"

    # Check quality threshold
    if quality_score >= {min_quality_score}:
        return "finish"

    if (
        {fail_on_no_improvement}
        and revision_count > 0
        and quality_delta <= {min_quality_improvement}
    ):
        return "no_improvement"

    # Check max revisions
    if revision_count >= {max_revisions}:
        return "max_revisions_failed" if {fail_on_max_revisions} else "max_revisions_reached"
    
    # Continue revising
    return "revise"'''

    @staticmethod
    def generate_graph_code(
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
        failure_conditions: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate complete critique-revise graph construction code.

        Args:
            max_revisions: Maximum revision cycles
            min_quality_score: Minimum quality score to approve
            failure_conditions: Optional failure controls passed to the router

        Returns:
            Python code string for building the complete graph
        """
        return f"""from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import InMemorySaver


{CritiqueLoopPattern.generate_conditional_edge_code(max_revisions, min_quality_score, failure_conditions)}


# Create graph
workflow = StateGraph(WorkflowState)
checkpointer = InMemorySaver()

# Add nodes
workflow.add_node("generate", generate_node)
workflow.add_node("critique", critique_node)
workflow.add_node("revise", revise_node)

# Connect start to generation
workflow.add_edge(START, "generate")

# Generation always goes to critique
workflow.add_edge("generate", "critique")

# Conditional edge from critique
workflow.add_conditional_edges(
    "critique",
    should_continue,
    {{
        "finish": END,
        "missing_feedback": END,
        "no_improvement": END,
        "max_revisions_failed": END,
        "max_revisions_reached": END,
        "revise": "revise"
    }}
)

# Revision goes back to critique
workflow.add_edge("revise", "critique")

# Compile graph
graph = workflow.compile(checkpointer=checkpointer)"""

    @staticmethod
    def generate_complete_example(
        task_description: str = "Write a technical article",
        criteria: Optional[List[str]] = None,
        max_revisions: int = 3,
        min_quality_score: float = 0.8,
        model_config: Optional[Union[ModelConfig, dict]] = None,
        use_structured_output: bool = True,
        feedback_source: str = "automated",
        failure_conditions: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a complete, runnable critique-revise loop example.

        Args:
            task_description: Description of generation task
            criteria: Optional list of quality criteria
            max_revisions: Maximum revision cycles
            min_quality_score: Minimum score required for automatic approval
            model_config: ModelConfig instance or dict with model settings
            use_structured_output: Whether automated critique uses a Pydantic schema
            feedback_source: Either "automated" or "human"
            failure_conditions: Optional failure controls passed to graph routing

        Returns:
            Complete Python code for a critique-revise workflow
        """
        if criteria is None:
            criteria = [
                "Accuracy and correctness",
                "Clarity and readability",
                "Completeness",
                "Structure and organization",
            ]
        task_description_literal = CritiqueLoopPattern._quote_string(task_description)
        criteria_literal = CritiqueLoopPattern._quote_string_list(criteria)

        # Generate all components
        include_human_feedback = feedback_source == "human"
        state_code = CritiqueLoopPattern.generate_state_code(
            include_human_feedback=include_human_feedback,
            include_failure_tracking=bool(failure_conditions),
        )
        generate_code = CritiqueLoopPattern.generate_generation_node_code(
            task_description, model_config=model_config
        )
        critique_code = CritiqueLoopPattern.generate_critique_node_code(
            criteria,
            model_config=model_config,
            use_structured_output=use_structured_output,
            feedback_source=feedback_source,
        )
        revise_code = CritiqueLoopPattern.generate_revise_node_code(model_config=model_config)
        graph_code = CritiqueLoopPattern.generate_graph_code(
            max_revisions,
            min_quality_score,
            failure_conditions=failure_conditions,
        )

        human_feedback_example = ""
        if feedback_source == "human":
            human_feedback_example = '''
def collect_human_feedback(
    draft: str,
    criteria: List[str],
    revision_count: int,
    previous_feedback: str,
) -> dict:
    """Example human feedback hook for plug-and-play workflows.

    Replace this with UI review, a moderation queue, or API-driven approval.
    """
    return {
        "quality_score": 0.65 if revision_count == 0 else 0.9,
        "approved": revision_count >= 1,
        "feedback": (
            "Tighten the introduction, clarify the example, and improve the ending."
        ),
    }
'''

        human_state_fields = ""
        if feedback_source == "human":
            human_state_fields = '\n            "human_feedback_handler": collect_human_feedback,'

        failure_state_fields = ""
        if failure_conditions:
            failure_state_fields = """
            "previous_quality_score": 0.0, """

        return f'''"""
Critique-Revise Loop Pattern Example
Generated by LangGraph System Generator

This example demonstrates an iterative refinement workflow where:
- Initial content is generated
- A critic evaluates the quality (via automated or human feedback)
- Revisions are made based on feedback
- The cycle repeats until approval or max iterations
"""

{state_code}


{generate_code}


{critique_code}


{revise_code}


{graph_code}
{human_feedback_example}


# Example usage
if __name__ == "__main__":
    import asyncio
    from langchain_core.messages import HumanMessage
    
    async def run_example():
        # Initialize state
        initial_state = {{
            "messages": [HumanMessage(content={task_description_literal})],
            "current_draft": "",
            "critique_feedback": "",
            "revision_count": 0,
            "quality_score": 0.0,
            "approved": False,
            "criteria": {criteria_literal},
{failure_state_fields}{human_state_fields}
        }}
        
        # Run workflow
        config = {{"configurable": {{"thread_id": "example-thread"}}}}
        result = await graph.ainvoke(initial_state, config)
        
        print("Final Draft:", result.get("current_draft"))
        print("Revisions Made:", result.get("revision_count"))
        print("Quality Score:", result.get("quality_score"))
        print("Approved:", result.get("approved"))
    
    asyncio.run(run_example())
'''
