"""Dependency-light, versioned generation outcome wire models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class GenerationOutcome(OutcomeRecord):
    """Qualification, independently of durable job completion/publication."""

    schema_version: Literal[1] = 1
    status: Literal["completed", "advisories", "blocked", "unverified", "failed"]
    pipeline: Literal["completed", "failed", "unknown"]
    artifacts: ArtifactOutcome = Field(default_factory=ArtifactOutcome)
    static_qa: Literal["passed", "failed", "not_run"] = "not_run"
    environment_smoke: EnvironmentSmokeOutcome = Field(
        default_factory=EnvironmentSmokeOutcome
    )
    generated_execution: GeneratedExecutionOutcome = Field(
        default_factory=GeneratedExecutionOutcome
    )
    usability: Literal["blocked", "no_known_blockers", "unknown"]
    blocking_count: int = 0
    advisory_count: int = 0
    checks: list[str] = Field(default_factory=list)
    candidate: CandidateEvidence = Field(default_factory=CandidateEvidence)
    repair: RepairEvidence = Field(default_factory=RepairEvidence)
