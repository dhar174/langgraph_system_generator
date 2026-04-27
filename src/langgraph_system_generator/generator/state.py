"""Generator state schema with typed/Pydantic models for Phase 3."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
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


ArchitectureType = Literal["router", "subagents", "hybrid", "autoagent", "deepagents"]


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


class GraphNodeSpec(BaseModel):
    """Normalized graph node specification."""

    name: str = Field(description="Stable node identifier used in graph wiring.")
    purpose: str = Field(description="Human-readable purpose for the node.")


class GraphEdgeSpec(BaseModel):
    """Normalized directed edge between two workflow nodes."""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(alias="from", description="Source node identifier.")
    target: str = Field(alias="to", description="Target node identifier.")


class GraphConditionalEdgeSpec(BaseModel):
    """Normalized conditional edge specification."""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(
        alias="from",
        description="Node identifier that owns the conditional routing logic.",
    )
    condition: str = Field(description="Human-readable routing condition description.")
    branches: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from branch labels to target node identifiers or END.",
    )


class GraphValidationIssue(BaseModel):
    """Structured graph validation issue surfaced during design."""

    code: str = Field(description="Stable validation issue code.")
    message: str = Field(description="Human-readable validation issue description.")
    severity: Literal["error", "warning"] = Field(
        default="error",
        description="Whether the issue is blocking or advisory.",
    )
    nodes: List[str] = Field(
        default_factory=list,
        description="Node identifiers associated with the issue, when applicable.",
    )


class GraphExportBundle(BaseModel):
    """Serializable graph-design export surfaces."""

    model_config = ConfigDict(populate_by_name=True)

    mermaid: str = Field(
        default="",
        description="Mermaid flowchart representation of the normalized graph.",
    )
    schema_payload: Dict[str, Any] = Field(
        default_factory=dict,
        alias="schema",
        description="JSON-serializable workflow schema and validation summary.",
    )

    @property
    def schema(self) -> Dict[str, Any]:
        """Return the serialized graph schema payload."""

        return self.schema_payload


class GraphDesignFeedback(BaseModel):
    """Advisory feedback captured during graph design."""

    fallback_used: bool = Field(
        default=False,
        description="Whether the designer had to use a deterministic fallback graph.",
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Reason fallback mode was used, when applicable.",
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Blocking validation errors encountered during live graph design.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Advisory warnings captured during graph design.",
    )
    validation_issues: List[GraphValidationIssue] = Field(
        default_factory=list,
        description="Structured validation issues captured during graph design.",
    )
    composition_strategy: Optional[str] = Field(
        default=None,
        description="Composition strategy used to normalize or build the graph.",
    )


class GraphDesignResult(BaseModel):
    """Structured graph-design output consumed by downstream stages."""

    architecture_type: str = Field(description="Normalized architecture identifier.")
    state_schema: Dict[str, str] = Field(
        default_factory=dict,
        description="Normalized workflow state schema mapping.",
    )
    nodes: List[GraphNodeSpec] = Field(
        default_factory=list,
        description="Normalized workflow node specifications.",
    )
    edges: List[GraphEdgeSpec] = Field(
        default_factory=list,
        description="Normalized direct graph edges.",
    )
    conditional_edges: List[GraphConditionalEdgeSpec] = Field(
        default_factory=list,
        description="Normalized conditional graph edges.",
    )
    entry_point: str = Field(description="Entry point node identifier.")
    checkpointing: bool = Field(
        default=False,
        description="Whether the generated workflow should enable checkpointing.",
    )
    feedback: GraphDesignFeedback = Field(
        default_factory=GraphDesignFeedback,
        description="Advisory graph-design feedback.",
    )
    exports: GraphExportBundle = Field(
        default_factory=GraphExportBundle,
        description="Serializable graph exports for manifests and notebooks.",
    )

    def to_workflow_design_payload(self) -> Dict[str, Any]:
        """Return the backward-compatible workflow_design payload."""

        return {
            "architecture_type": self.architecture_type,
            "state_schema": dict(self.state_schema),
            "nodes": [node.model_dump() for node in self.nodes],
            "edges": [edge.model_dump(by_alias=True) for edge in self.edges],
            "conditional_edges": [
                edge.model_dump(by_alias=True) for edge in self.conditional_edges
            ],
            "entry_point": self.entry_point,
            "checkpointing": self.checkpointing,
            "graph_exports": self.exports.model_dump(by_alias=True),
        }


ToolStatus = Literal["ready", "fallback", "unsupported"]
QASeverity = Literal["info", "warning", "error"]


class ToolSpec(BaseModel):
    """Normalized tool specification for workflow planning."""

    tool_id: str = Field(description="Canonical tool identifier.")
    name: str = Field(description="Human-readable display name for the tool.")
    category: str = Field(description="Normalized tool category.")
    purpose: str = Field(description="Why the workflow needs this tool.")
    configuration: Dict[str, Any] = Field(
        default_factory=dict,
        description="Normalized tool configuration payload.",
    )
    packages: List[str] = Field(
        default_factory=list,
        description="Packages required to support this tool in generated notebooks.",
    )
    provider_env_vars: List[str] = Field(
        default_factory=list,
        description="Provider credential environment variables needed by this tool.",
    )
    status: ToolStatus = Field(
        default="ready",
        description="Planning status: ready, fallback, or unsupported.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Tool-specific planning or validation warnings.",
    )


class ToolPlanningFeedback(BaseModel):
    """Advisory feedback captured during tool planning."""

    fallback_used: bool = Field(
        default=False,
        description="Whether the planner had to fall back to heuristic tool inference.",
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Reason fallback mode was used, when applicable.",
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Validation issues found in LLM-produced tool suggestions.",
    )
    unresolved_tools: List[str] = Field(
        default_factory=list,
        description="Suggested tools that could not be resolved to a canonical registry entry.",
    )
    environment_notes: List[str] = Field(
        default_factory=list,
        description="Environment-compatibility notes gathered during planning.",
    )
    dependency_conflicts: List[str] = Field(
        default_factory=list,
        description="Dependency conflicts or gaps discovered during planning.",
    )
    available_tool_ids: List[str] = Field(
        default_factory=list,
        description="Canonical tool identifiers available to the planner.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="High-level planning warnings for manifests and notebook surfaces.",
    )


class ToolPlanningResult(BaseModel):
    """Structured tool-planning output consumed by downstream stages."""

    tools: List[ToolSpec] = Field(
        default_factory=list,
        description="Normalized planned tools for the workflow.",
    )
    feedback: ToolPlanningFeedback = Field(
        default_factory=ToolPlanningFeedback,
        description="Advisory tool-planning metadata.",
    )

    def to_tools_plan_payload(self) -> List[Dict[str, Any]]:
        """Return the backward-compatible tools_plan payload."""

        return [tool.model_dump() for tool in self.tools]


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
        description="Selected architecture: router, subagents, hybrid, autoagent, or deepagents",
    )


class NotebookDependencyPlan(BaseModel):
    """Normalized dependency and install plan for a generated notebook."""

    packages: List[str] = Field(
        default_factory=list,
        description="Ordered, de-duplicated packages required by the notebook.",
    )
    install_commands: List[str] = Field(
        default_factory=list,
        description="Install commands emitted or recommended for the notebook runtime.",
    )
    runtime_notes: List[str] = Field(
        default_factory=list,
        description="Environment assumptions or install notes shown to notebook users.",
    )
    conflicts_resolved: List[str] = Field(
        default_factory=list,
        description="Dependency family conflicts resolved during planning.",
    )
    provider_env_vars: List[str] = Field(
        default_factory=list,
        description="Credential environment variables referenced by notebook config.",
    )


class NotebookFallbackEvent(BaseModel):
    """Structured record of a notebook-composition fallback."""

    kind: str = Field(description="Notebook component that used a fallback path.")
    item_name: Optional[str] = Field(
        default=None,
        description="Tool or node name associated with the fallback, when applicable.",
    )
    reason: str = Field(description="Reason the fallback path was used.")
    warning: str = Field(
        description="Visible notebook-facing warning emitted for this fallback."
    )


class NotebookCompositionFeedback(BaseModel):
    """Advisory feedback captured during notebook composition."""

    fallback_used: bool = Field(
        default=False,
        description="Whether notebook composition used one or more deterministic fallbacks.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Advisory composition warnings surfaced to manifests and callers.",
    )
    fallback_events: List[NotebookFallbackEvent] = Field(
        default_factory=list,
        description="Structured fallback events captured during notebook composition.",
    )
    resolved_model: Optional[str] = Field(
        default=None,
        description="Resolved model identifier embedded in notebook config cells.",
    )
    resolved_api_base: Optional[str] = Field(
        default=None,
        description="Resolved OpenAI-compatible base URL embedded in config cells.",
    )
    resolved_max_iterations: Optional[int] = Field(
        default=None,
        ge=1,
        description="Resolved iteration limit embedded in notebook cells.",
    )
    sections_built: List[str] = Field(
        default_factory=list,
        description="Ordered internal section builders used to assemble the notebook.",
    )


class CellSpec(BaseModel):
    """Specification for a notebook cell."""

    cell_type: str = Field(description="Cell type: 'markdown' or 'code'")
    content: str = Field(description="Cell content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Cell metadata")
    section: Optional[str] = Field(
        default=None, description="Section this cell belongs to"
    )


class NotebookCompositionResult(BaseModel):
    """Structured notebook composition output consumed by downstream stages."""

    cells: List[CellSpec] = Field(
        default_factory=list,
        description="Generated notebook cells in final execution order.",
    )
    dependency_plan: NotebookDependencyPlan = Field(
        default_factory=NotebookDependencyPlan,
        description="Resolved dependency and install metadata for the notebook.",
    )
    feedback: NotebookCompositionFeedback = Field(
        default_factory=NotebookCompositionFeedback,
        description="Advisory notebook-composition metadata.",
    )


class QAReport(BaseModel):
    """Quality assurance report."""

    check_name: str = Field(description="Name of the QA check")
    passed: bool = Field(description="Whether the check passed")
    message: str = Field(description="Report message or error details")
    rule_id: str = Field(
        default="qa_report",
        description="Stable identifier for the QA rule that emitted this report.",
    )
    severity: QASeverity = Field(
        default="info",
        description="Severity for failed checks: info, warning, or error.",
    )
    category: str = Field(
        default="general",
        description="High-level QA category such as syntax, imports, or graph_structure.",
    )
    repairable: bool = Field(
        default=False,
        description="Whether the failure is expected to be safely repairable.",
    )
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


class QARepairFeedback(BaseModel):
    """Advisory QA/repair summary surfaced to manifests and callers."""

    repair_attempts: int = Field(
        default=0,
        ge=0,
        description="Number of repair attempts made so far for the current run.",
    )
    rollback_used: bool = Field(
        default=False,
        description="Whether a repair attempt had to roll back to the prior notebook snapshot.",
    )
    unrepaired_failures: List[str] = Field(
        default_factory=list,
        description="Blocking QA failures that remain unresolved after validation or repair.",
    )
    next_steps: List[str] = Field(
        default_factory=list,
        description="Actionable next steps for resolving unresolved QA failures.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="High-level QA/repair warnings for manifests and notebook-facing surfaces.",
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
    graph_design_feedback: GraphDesignFeedback
    graph_exports: GraphExportBundle
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
    tool_planning_feedback: ToolPlanningFeedback
    notebook_composition_feedback: NotebookCompositionFeedback
    notebook_dependency_plan: NotebookDependencyPlan

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
    qa_repair_feedback: QARepairFeedback

    # Output
    artifacts_manifest: Dict[str, Any]
    generation_complete: bool
    error_message: Optional[str]
