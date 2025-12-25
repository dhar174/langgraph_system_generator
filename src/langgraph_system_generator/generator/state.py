"""Generator state schema with typed/Pydantic models for Phase 3."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class Constraint(BaseModel):
    """User constraint specification."""

    type: str = Field(
        description="Constraint type: 'goal', 'tone', 'length', 'structure', 'runtime', 'environment'"
    )
    value: str = Field(description="Constraint value or description")
    priority: int = Field(default=1, description="Priority level (1=low, 5=high)")


class DocSnippet(BaseModel):
    """Retrieved documentation snippet."""

    content: str = Field(description="Documentation content text")
    source: str = Field(description="Source URL or identifier")
    relevance_score: float = Field(
        default=0.0, description="Relevance score from retrieval"
    )
    heading: Optional[str] = Field(
        default=None, description="Section heading if available"
    )


class NotebookPlan(BaseModel):
    """Plan for notebook structure."""

    title: str = Field(description="Notebook title")
    sections: List[str] = Field(default_factory=list, description="Major section names")
    cell_count_estimate: int = Field(default=0, description="Estimated number of cells")
    patterns_used: List[str] = Field(
        default_factory=list, description="LangGraph patterns to be used"
    )
    architecture_type: str = Field(
        default="", description="Selected architecture: router, subagents, or hybrid"
    )


class CellSpec(BaseModel):
    """Specification for a notebook cell."""

    cell_type: str = Field(description="Cell type: 'markdown' or 'code'")
    content: str = Field(description="Cell content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Cell metadata")
    section: Optional[str] = Field(
        default=None, description="Section this cell belongs to"
    )


class QAReport(BaseModel):
    """Quality assurance report."""

    check_name: str = Field(description="Name of the QA check")
    passed: bool = Field(description="Whether the check passed")
    message: str = Field(description="Report message or error details")
    suggestions: List[str] = Field(default_factory=list, description="Suggested fixes")


class GeneratorState(TypedDict):
    """State for the outer generator graph."""

    # Input
    user_prompt: str
    uploaded_files: Optional[List[str]]

    # Extracted requirements
    constraints: Annotated[List[Constraint], operator.add]
    selected_patterns: Dict[str, Any]

    # RAG context
    docs_context: Annotated[List[DocSnippet], operator.add]

    # Planning
    notebook_plan: Optional[NotebookPlan]
    architecture_justification: str
    architecture_type: Optional[str]

    # Workflow design (added for graph designer)
    workflow_design: Optional[Dict[str, Any]]
    tools_plan: Optional[List[Dict[str, Any]]]

    # Generation
    generated_cells: Annotated[List[CellSpec], operator.add]

    # QA & Repair
    qa_reports: List[QAReport]
    repair_attempts: int

    # Output
    artifacts_manifest: Dict[str, str]
    generation_complete: bool
    error_message: Optional[str]
