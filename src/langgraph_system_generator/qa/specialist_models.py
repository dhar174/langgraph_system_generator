"""Immutable semantic-review contracts, independent of model/cloud SDKs."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REVIEWER_ID = "requirements_domain_fidelity"
REVIEWER_VERSION = "1"
MAX_INPUT_CHARS = 48_000
MAX_RESPONSE_CHARS = 16_384
MAX_OUTPUT_TOKENS = 2048
REVIEW_TIMEOUT_SECONDS = 30.0

ReviewStatus = Literal[
    "disabled", "skipped", "reviewed", "unavailable", "invalid_response", "incomplete"
]
ReviewReason = Literal[
    "off",
    "stub",
    "no_cells",
    "blocking_qa",
    "runtime_unavailable",
    "complete",
    "provider_unavailable",
    "unsupported_response",
    "timeout",
    "invalid_response",
    "invalid_reference",
    "refused",
    "empty_response",
    "input_limit",
    "output_limit",
    "insufficient_context",
    "stale_context",
    "reviewer_unavailable",
]
FindingCategory = Literal[
    "requirements_gap",
    "contradiction",
    "domain_mismatch",
    "unsupported_capability_claim",
    "provided_docs_conflict",
]
SourceFamily = Literal["requirement", "cell", "docs"]


class ReviewRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SemanticReviewPolicy(ReviewRecord):
    mode: Literal["off", "advisory"] = "off"
    plugin_modules: tuple[str, ...] = ()


class ReviewSource(ReviewRecord):
    source_id: str
    family: SourceFamily
    fingerprint: str
    text: str = Field(repr=False)
    location: str
    version: str | None = None
    cell_index: int | None = None


class SemanticReviewContext(ReviewRecord):
    candidate_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    context_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt: int = Field(ge=0)
    docs_available: bool
    # Transient only: never returned in graph state, artifacts, logs or feedback.
    request_json: str = Field(exclude=True, repr=False)
    sources: tuple[ReviewSource, ...] = Field(exclude=True, repr=False)


class ModelReference(ReviewRecord):
    source_id: str = Field(min_length=1, max_length=100)
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    quote: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def valid_range(self) -> ModelReference:
        if not 0 < self.end - self.start <= 2000:
            raise ValueError("Invalid evidence range")
        return self


class ModelFinding(ReviewRecord):
    category: FindingCategory
    message: str = Field(min_length=1, max_length=400)
    suggestions: tuple[Annotated[str, Field(min_length=1, max_length=240)], ...] = (
        Field(max_length=2)
    )
    references: tuple[ModelReference, ...] = Field(min_length=1, max_length=6)


class ModelReviewResponse(ReviewRecord):
    assessment: Literal["complete", "insufficient_context"]
    findings: tuple[ModelFinding, ...] = Field(max_length=8)


class EvidenceLocation(ReviewRecord):
    source_id: str
    family: SourceFamily
    fingerprint: str
    start: int
    end: int
    cell_index: int | None
    version: str | None = Field(max_length=128)
    location: str = Field(max_length=512)


class SemanticFinding(ReviewRecord):
    finding_id: str
    rule_id: str
    category: FindingCategory
    message: str = Field(max_length=400)
    suggestions: tuple[Annotated[str, Field(max_length=240)], ...] = Field(max_length=2)
    references: tuple[EvidenceLocation, ...] = Field(max_length=6)


class SemanticReviewResult(ReviewRecord):
    """Transient specialist return; the host admits and stamps findings."""

    status: ReviewStatus
    reason_code: ReviewReason
    candidate_id: str
    context_digest: str
    model_invocations: int = Field(default=0, ge=0, le=1)
    response: ModelReviewResponse | None = Field(default=None, exclude=True, repr=False)


class SemanticReviewFeedback(ReviewRecord):
    effective_mode: Literal["off", "advisory"]
    reviewer_id: str = Field(default=REVIEWER_ID, min_length=1, max_length=100)
    reviewer_version: str = Field(
        default=REVIEWER_VERSION, min_length=1, max_length=100
    )
    status: ReviewStatus
    reason_code: ReviewReason
    candidate_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    context_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    attempt: int = Field(default=0, ge=0)
    model_invocations: int = Field(default=0, ge=0, le=1)
    docs_alignment: Literal["provided_docs_only", "not_assessed"] = "not_assessed"
    findings: tuple[SemanticFinding, ...] = Field(default=(), max_length=8)


def review_response_format() -> dict[str, Any]:
    """Native strict schema; local validation additionally enforces all bounds."""
    schema = ModelReviewResponse.model_json_schema()

    def provider_schema(item: Any) -> Any:
        if isinstance(item, dict):
            # Provider schema subsets vary. Bounds stay mandatory in host models.
            return {
                key: provider_schema(value)
                for key, value in item.items()
                if key
                not in {
                    "title",
                    "minLength",
                    "maxLength",
                    "minItems",
                    "maxItems",
                    "minimum",
                    "maximum",
                    "exclusiveMinimum",
                    "exclusiveMaximum",
                }
            }
        if isinstance(item, list):
            return [provider_schema(value) for value in item]
        return item

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "requirements_domain_review",
            "strict": True,
            "schema": provider_schema(schema),
        },
    }
