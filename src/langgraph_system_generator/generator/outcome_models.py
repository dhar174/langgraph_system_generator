"""Dependency-light, versioned generation outcome wire models."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OutcomeRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ArtifactOutcome(OutcomeRecord):
    scope: Literal["generated_output_set"] = "generated_output_set"
    presence: Literal["present", "missing", "unknown"] = "unknown"
    availability: Literal["available", "not_available", "unknown"] = "unknown"


class EnvironmentSmokeOutcome(OutcomeRecord):
    scope: Literal["trusted_smoke_test"] = "trusted_smoke_test"
    result: Literal["passed", "failed", "unavailable", "not_run"] = "not_run"


class GeneratedExecutionOutcome(OutcomeRecord):
    scope: Literal["generated_notebook"] = "generated_notebook"
    result: Literal["not_run"] = "not_run"


class CandidateEvidence(OutcomeRecord):
    algorithm: Literal["notebook-cells-v1"] = "notebook-cells-v1"
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    matched_reports: int = 0
    missing_reports: int = 0
    stale_reports: int = 0
    legacy_limited: bool = False


class RepairEvidence(OutcomeRecord):
    attempts: int = Field(default=0, ge=0)
    limit: int = Field(default=0, ge=0)
    budget_exhausted: bool = False
    rollback_used: bool = False


class OutcomeDimensions(OutcomeRecord):
    """Qualification, independently of durable job completion/publication."""

    status: Literal["completed", "advisories", "blocked", "unverified", "failed"]
    pipeline: Literal["completed", "failed", "unknown"]
    artifacts: ArtifactOutcome = Field(default_factory=ArtifactOutcome)
    static_qa: Literal["passed", "failed", "not_run"] = "not_run"
    environment_smoke: EnvironmentSmokeOutcome = Field(
        default_factory=EnvironmentSmokeOutcome
    )
    usability: Literal["blocked", "no_known_blockers", "unknown"]
    blocking_count: int = 0
    advisory_count: int = 0
    checks: list[str] = Field(default_factory=list)
    candidate: CandidateEvidence = Field(default_factory=CandidateEvidence)
    repair: RepairEvidence = Field(default_factory=RepairEvidence)


class GenerationOutcome(OutcomeDimensions):
    """Historical v1 writer; its execution meaning must never change."""

    schema_version: Literal[1] = 1
    generated_execution: GeneratedExecutionOutcome = Field(
        default_factory=GeneratedExecutionOutcome
    )


class EvaluatedExecutionOutcome(OutcomeRecord):
    scope: Literal["generated_notebook"] = "generated_notebook"
    result: Literal["not_run", "passed", "failed", "unavailable", "incomplete"]
    evidence_level: Literal["controlled_fixture_behavior"] = (
        "controlled_fixture_behavior"
    )
    candidate_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    executed_notebook_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    generator_revision: str | None = None
    evaluator_version: str
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str
    case_version: int = Field(ge=1)
    environment: dict[str, str] = Field(default_factory=dict)
    dependencies: dict[str, str] = Field(default_factory=dict)
    isolation: list[str] = Field(default_factory=list)
    mocked: list[str] = Field(default_factory=list)
    executed: list[str] = Field(default_factory=list)
    untested: list[str] = Field(default_factory=list)
    assertions_passed: int = Field(default=0, ge=0)
    assertions_required: int = Field(default=0, ge=0)
    failed_assertions: list[str] = Field(default_factory=list)
    receipt_reference: str | None = None
    receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    failure_classification: Literal[
        "none",
        "generated_behavior",
        "environment",
        "evidence_integrity",
        "partial_execution",
    ]
    limitations: list[str] = Field(default_factory=list)
    requirements_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def require_qualified_pass(self) -> "EvaluatedExecutionOutcome":
        allowed = {
            "not_run": {"none"},
            "passed": {"none"},
            "failed": {"generated_behavior"},
            "unavailable": {"environment"},
            "incomplete": {"evidence_integrity", "partial_execution"},
        }
        if self.failure_classification not in allowed[self.result]:
            raise ValueError("Execution result and failure classification disagree")
        if self.result == "passed" and (
            self.failure_classification != "none"
            or not self.candidate_sha256
            or not self.executed_notebook_sha256
            or not self.generator_revision
            or not self.receipt_reference
            or not self.receipt_sha256
            or not self.assertions_required
            or self.assertions_required != self.assertions_passed
            or self.failed_assertions
            or not self.executed
            or not self.isolation
            or not self.untested
        ):
            raise ValueError("Execution pass requires complete scoped evidence")
        return self


class GenerationOutcomeV2(OutcomeDimensions):
    schema_version: Literal[2] = 2
    generated_execution: EvaluatedExecutionOutcome

    @model_validator(mode="after")
    def require_matching_candidate(self) -> "GenerationOutcomeV2":
        execution = self.generated_execution
        if (
            execution.result in {"passed", "failed", "unavailable"}
            and execution.candidate_sha256 != self.candidate.sha256
        ):
            raise ValueError("Execution evidence belongs to another candidate")
        if execution.result == "failed" and (
            self.usability != "blocked"
            or self.status not in {"blocked", "failed"}
            or self.blocking_count < 1
        ):
            raise ValueError("Failed execution must remain blocking")
        if execution.result in {"unavailable", "incomplete"} and (
            self.usability == "no_known_blockers"
            or self.status in {"completed", "advisories"}
        ):
            raise ValueError(
                "Missing execution qualification cannot imply usable output"
            )
        return self


SupportedGenerationOutcome = Annotated[
    GenerationOutcome | GenerationOutcomeV2, Field(discriminator="schema_version")
]
