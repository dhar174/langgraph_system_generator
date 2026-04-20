"""Generator state schema with typed/Pydantic models for Phase 3."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from langgraph_system_generator.utils.config import GenerationConfig

DEFAULT_REQUIREMENTS_CONSTRAINT_TYPES = (
    "goal",
    "tone",
    "length",
    "structure",
    "runtime",
    "environment",
)


def normalize_constraint_type(value: str) -> str:
    """Return a normalized constraint type token."""

    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def build_constraint_type_registry(extra_types: Optional[List[str]] = None) -> List[str]:
    """Build the ordered, de-duplicated registry of supported constraint types."""

    registry: List[str] = []
    for raw_type in [
        *DEFAULT_REQUIREMENTS_CONSTRAINT_TYPES,
        *(extra_types or []),
    ]:
        normalized = normalize_constraint_type(raw_type)
        if normalized and normalized not in registry:
            registry.append(normalized)
    return registry


class Constraint(BaseModel):
    """User constraint specification."""

    type: str = Field(
        description=(
            "Constraint type from the current intake registry, such as "
            "'goal', 'tone', 'length', 'structure', 'runtime', "
            "'environment', or configured extras."
        )
    )
    value: str = Field(description="Constraint value or description")
    priority: int = Field(default=1, description="Priority level (1=low, 5=high)")
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence score for the extracted constraint.",
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Optional human-readable explanation for why the constraint was extracted.",
    )


class RequirementsFeedback(BaseModel):
    """Advisory feedback captured during requirements extraction."""

    fallback_used: bool = Field(
        default=False,
        description="Whether the analyst had to fall back to a synthetic goal constraint.",
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Reason fallback mode was used, when applicable.",
    )
    missing_inputs: List[str] = Field(
        default_factory=list,
        description="Core requirement categories that were missing from the prompt.",
    )
    conflicts: List[str] = Field(
        default_factory=list,
        description="Conflicting requirement interpretations detected during extraction.",
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="Actionable follow-up suggestions for improving requirement quality.",
    )
    available_constraint_types: List[str] = Field(
        default_factory=list,
        description="Constraint types available to the analyst for the current request.",
    )


class RequirementsAnalysis(BaseModel):
    """Structured single-turn requirements analysis output."""

    constraints: List[Constraint] = Field(
        default_factory=list,
        description="Constraints extracted from the user's prompt.",
    )
    feedback: RequirementsFeedback = Field(
        default_factory=RequirementsFeedback,
        description="Advisory feedback captured during requirements extraction.",
    )


ArchitectureType = Literal["router", "subagents", "hybrid", "autoagent"]


class ArchitectureAlternative(BaseModel):
    """Advisory alternative architecture considered during selection."""

    architecture_type: ArchitectureType = Field(
        description="Alternative architecture option considered during selection."
    )
    score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional relative score for this alternative.",
    )
    rationale: Optional[str] = Field(
        default=None,
        description="Short rationale for why this alternative ranked below the winner.",
    )


class ArchitecturePatternSelection(BaseModel):
    """Normalized selected-pattern payload for architecture selection."""

    primary: ArchitectureType = Field(
        description="Primary architecture pattern selected for the workflow."
    )
    secondary: List[ArchitectureType] = Field(
        default_factory=list,
        description="Secondary patterns that complement the primary architecture.",
    )


class ArchitectureFeedback(BaseModel):
    """Advisory feedback captured during architecture selection."""

    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence score for the selected architecture.",
    )
    alternatives: List[ArchitectureAlternative] = Field(
        default_factory=list,
        description="Alternative architectures considered during selection.",
    )
    tradeoffs: List[str] = Field(
        default_factory=list,
        description="Short tradeoffs associated with the selected architecture.",
    )
    fallback_used: bool = Field(
        default=False,
        description="Whether the selector fell back to a default architecture.",
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Reason fallback mode was used, when applicable.",
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Validation or normalization issues detected in selector output.",
    )
    docs_considered: List[str] = Field(
        default_factory=list,
        description="Documentation snippets or pattern docs considered during selection.",
    )


class ArchitectureSelectionResult(BaseModel):
    """Structured architecture-selection output."""

    architecture_type: ArchitectureType = Field(
        description="Final selected architecture type."
    )
    patterns: ArchitecturePatternSelection = Field(
        description="Normalized selected pattern payload."
    )
    justification: str = Field(
        description="Human-readable explanation for why this architecture was chosen."
    )
    feedback: ArchitectureFeedback = Field(
        default_factory=ArchitectureFeedback,
        description="Advisory architecture-selection metadata.",
    )


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
        default="",
        description="Selected architecture: router, subagents, hybrid, or autoagent",
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
    stage: Optional[str] = Field(
        default=None,
        description="Optional workflow stage for this report (e.g. static, runtime, repair).",
    )
    attempt: Optional[int] = Field(
        default=None,
        description="Optional repair/QA attempt number associated with this report.",
    )
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured evidence captured during QA or repair.",
    )


class GeneratorState(TypedDict):
    """State for the outer generator graph."""

    # Input
    user_prompt: str
    uploaded_files: Optional[List[str]]

    # Extracted requirements
    constraints: Annotated[List[Constraint], operator.add]
    requirements_feedback: RequirementsFeedback
    architecture_feedback: ArchitectureFeedback
    selected_patterns: Dict[str, Any]

    # RAG context
    docs_context: Annotated[List[DocSnippet], operator.add]

    # Planning
    notebook_plan: Optional[NotebookPlan]
    architecture_justification: str
    architecture_type: Optional[str]
    generation_config: Optional[GenerationConfig]
    generation_mode: Literal["stub", "live"]

    # Workflow design (added for graph designer)
    workflow_design: Optional[Dict[str, Any]]
    tools_plan: Optional[List[Dict[str, Any]]]

    # Generation
    # NOTE: `generated_cells` is intentionally *not* annotated with `operator.add`.
    # When multiple nodes set this field, the last value will replace any previous ones
    # instead of being concatenated. This differs from earlier behavior where
    # `generated_cells` updates were accumulated, and it is relied on by the repair loop
    # semantics (e.g., retry flows) to treat each iteration's cells as authoritative.
    generated_cells: List[CellSpec]

    # QA & Repair
    qa_reports: List[QAReport]
    qa_history: List[QAReport]
    repair_attempts: int

    # Output
    artifacts_manifest: Dict[str, Any]
    generation_complete: bool
    error_message: Optional[str]
