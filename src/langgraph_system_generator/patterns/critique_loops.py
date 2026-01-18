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

from typing import Dict, List, Optional, Union

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
    """

    @staticmethod
    def generate_state_code(additional_fields: Optional[Dict[str, str]] = None) -> str:
        """Generate state schema code for critique-revise pattern.

        Args:
            additional_fields: Optional dict mapping field names to descriptions

        Returns:
            Python code string defining the WorkflowState class
        """
        additional = ""
        if additional_fields:
            for field_name, description in additional_fields.items():
                additional += f"    {field_name}: str  # {description}\n"

        return f'''from typing import Annotated, List
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
{additional}'''

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
        
        llm_init = build_llm_init(llm_model, temperature, api_base, max_tokens)
        
        return f'''def generate_node(state: WorkflowState) -> WorkflowState:
    """Generate initial output or first draft.
    
    Task: {task_description}
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    
    messages = state["messages"]
    revision_count = state.get("revision_count", 0)
    
    # Initialize LLM
    llm = {llm_init}
    
    # Generation prompt
    system_prompt = SystemMessage(content="""You are an expert content generator.
{task_description}

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
    ) -> str:
        """Generate code for critique/review node.

        Args:
            criteria: Optional list of quality criteria to evaluate
            model_config: ModelConfig instance or dict with model settings
            use_structured_output: Whether to use structured output

        Returns:
            Python code string implementing the critique node
        """
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

        criteria_str = "\\n".join([f"- {c}" for c in criteria])

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
    criteria = state.get("criteria", [])
    
    # Initialize LLM with structured output
    llm = {llm_init}
    structured_llm = llm.with_structured_output(CritiqueAssessment)
    
    # Critique prompt
    system_prompt = """You are an expert critic and reviewer.
Evaluate the output against these quality criteria:
{criteria_str}

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
        "messages": messages + [HumanMessage(content=f"Critique: {{feedback}}")],
    }}'''
        else:
            return f'''from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def critique_node(state: WorkflowState) -> WorkflowState:
    """Critique the current draft and provide feedback."""
    current_draft = state.get("current_draft", "")
    messages = state["messages"]
    
    llm = {llm_init}
    
    # Critique prompt
    system_prompt = SystemMessage(content=f"""You are an expert critic.
Evaluate against: {criteria_str}

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
        max_revisions: int = 3, min_quality_score: float = 0.8
    ) -> str:
        """Generate conditional edge routing code.

        Args:
            max_revisions: Maximum number of revision cycles
            min_quality_score: Minimum quality score to approve

        Returns:
            Python code string for conditional routing logic
        """
        return f'''def should_continue(state: WorkflowState) -> str:
    """Determine if we should continue revising or finish.
    
    Decision criteria:
    - If approved: finish
    - If max revisions reached: finish (even if not perfect)
    - Otherwise: continue revising
    """
    approved = state.get("approved", False)
    revision_count = state.get("revision_count", 0)
    quality_score = state.get("quality_score", 0.0)
    
    # Check approval status
    if approved:
        return "finish"
    
    # Check max revisions
    if revision_count >= {max_revisions}:
        return "max_revisions_reached"
    
    # Check quality threshold
    if quality_score >= {min_quality_score}:
        return "finish"
    
    # Continue revising
    return "revise"'''

    @staticmethod
    def generate_graph_code(
        max_revisions: int = 3, min_quality_score: float = 0.8
    ) -> str:
        """Generate complete critique-revise graph construction code.

        Args:
            max_revisions: Maximum revision cycles
            min_quality_score: Minimum quality score to approve

        Returns:
            Python code string for building the complete graph
        """
        return f"""from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver


{CritiqueLoopPattern.generate_conditional_edge_code(max_revisions, min_quality_score)}


# Create graph
workflow = StateGraph(WorkflowState)
memory = MemorySaver()

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
        "max_revisions_reached": END,
        "revise": "revise"
    }}
)

# Revision goes back to critique
workflow.add_edge("revise", "critique")

# Compile graph
graph = workflow.compile(checkpointer=memory)"""

    @staticmethod
    def generate_complete_example(
        task_description: str = "Write a technical article",
        criteria: Optional[List[str]] = None,
        max_revisions: int = 3,
        model_config: Optional[Union[ModelConfig, dict]] = None,
    ) -> str:
        """Generate a complete, runnable critique-revise loop example.

        Args:
            task_description: Description of generation task
            criteria: Optional list of quality criteria
            max_revisions: Maximum revision cycles
            model_config: ModelConfig instance or dict with model settings

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

        # Generate all components
        state_code = CritiqueLoopPattern.generate_state_code()
        generate_code = CritiqueLoopPattern.generate_generation_node_code(
            task_description, model_config=model_config
        )
        critique_code = CritiqueLoopPattern.generate_critique_node_code(criteria, model_config=model_config)
        revise_code = CritiqueLoopPattern.generate_revise_node_code(model_config=model_config)
        graph_code = CritiqueLoopPattern.generate_graph_code(max_revisions)

        return f'''"""
Critique-Revise Loop Pattern Example
Generated by LangGraph System Generator

This example demonstrates an iterative refinement workflow where:
- Initial content is generated
- A critic evaluates the quality
- Revisions are made based on feedback
- The cycle repeats until approval or max iterations

Quality Criteria:
{chr(10).join([f"- {c}" for c in criteria])}
"""

{state_code}


{generate_code}


{critique_code}


{revise_code}


{graph_code}


# Example usage
if __name__ == "__main__":
    import asyncio
    from langchain_core.messages import HumanMessage
    
    async def run_example():
        # Initialize state
        initial_state = {{
            "messages": [HumanMessage(content="{task_description}")],
            "current_draft": "",
            "critique_feedback": "",
            "revision_count": 0,
            "quality_score": 0.0,
            "approved": False,
            "criteria": {criteria},
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
