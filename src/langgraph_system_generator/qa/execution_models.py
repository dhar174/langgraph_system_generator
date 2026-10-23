"""Separate, versioned trusted-fixture receipts; never production outcomes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class EvidenceCaptureLimitError(RuntimeError):
    """The evaluator exhausted its evidence budget, not a graph assertion."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Invocation(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    text: str
    thread_id: str
    expected_nodes: list[str] = Field(min_length=1)
    expected_state: dict[str, Any] = Field(default_factory=dict)
    expected_tool_calls: int = Field(default=0, ge=0)
    retained_text: str | None = None
    absent_text: str | None = None
    expected_error: str | None = None
    terminal: bool = True


class ExecutionCase(StrictModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    prompt: str = Field(min_length=1)
    architecture: Literal["router", "subagents"]
    generator_mode: Literal["stub", "live"] = "live"
    fixture: Literal["support-router-v1", "supervisor-v1", "chatbot-tool-v1"]
    tool_fixture: Literal["none", "calculator-v1"] = "none"
    dependencies: list[str] = Field(min_length=1)
    invocations: list[Invocation] = Field(min_length=1)
    max_steps: int = Field(default=12, ge=2, le=100)
    cell_timeout: int = Field(default=20, ge=1, le=120)
    total_timeout: int = Field(default=180, ge=10, le=600)
    memory_mb: int = Field(default=2048, ge=512, le=8192)
    cpu_seconds: int = Field(default=90, ge=5, le=600)
    capture_bytes: int = Field(default=65536, ge=4096, le=1048576)
    untested: list[str] = Field(min_length=1)


class ExecutionDataset(StrictModel):
    schema_version: Literal[1] = 1
    cases: list[ExecutionCase] = Field(min_length=3)

    @model_validator(mode="after")
    def unique_cases(self) -> ExecutionDataset:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Case IDs must be unique")
        if {case.fixture for case in self.cases} != {
            "support-router-v1",
            "supervisor-v1",
            "chatbot-tool-v1",
        }:
            raise ValueError("All three required fixture families must be present")
        if not any(case.generator_mode == "live" for case in self.cases):
            raise ValueError("Normal composition coverage is required")
        return self


class AssertionResult(StrictModel):
    name: str
    passed: bool
    detail: str = ""


class ExecutionResult(StrictModel):
    _supervision: Any = PrivateAttr(default=None)
    schema_version: Literal[1] = 1
    case_id: str
    case_version: Literal[1] = 1
    fixture: str
    mutation: str | None = None
    mutation_applied: bool = False
    mutated_notebook_path: str | None = None
    generator_revision: str
    source_dirty: bool
    source_diff_sha256: str
    source_tree_sha256: str = ""
    source_files_sha256: dict[str, str] = Field(default_factory=dict)
    notebook_path: str | None = None
    notebook_sha256: str | None = None
    candidate_algorithm: Literal["notebook-cells-v1"] = "notebook-cells-v1"
    candidate_sha256: str | None = None
    original_candidate_sha256: str | None = None
    derived_notebook_path: str | None = None
    derived_sha256: str | None = None
    serialized_cell_count: int = 0
    environment: dict[str, Any] = Field(default_factory=dict)
    isolation: dict[str, Any] = Field(default_factory=dict)
    attempted_cells: list[int] = Field(default_factory=list)
    completed_cells: list[int] = Field(default_factory=list)
    excluded_cells: dict[str, str] = Field(default_factory=dict)
    mocked: list[str] = Field(default_factory=list)
    executed: list[str] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    assertions: list[AssertionResult] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    timed_out: bool = False
    resource_limit_hit: bool = False
    resource_limit_outcome: Literal["not_observed", "hit", "unknown"] = "not_observed"
    cleanup_verified: bool = False
    runtime_seconds: float = 0
    status: Literal["passed", "failed", "incomplete"] = "incomplete"
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_execution_for_pass(self) -> ExecutionResult:
        if self.status == "passed" and (
            not any(item.get("nodes") for item in self.observations)
            or not self.assertions
            or not all(item.passed for item in self.assertions)
            or self.errors
            or self.timed_out
            or self.resource_limit_hit
            or self.resource_limit_outcome != "not_observed"
            or not self.cleanup_verified
            or not self.candidate_sha256
            or not self.notebook_path
            or not self.notebook_sha256
            or not self.original_candidate_sha256
            or not self.source_tree_sha256
            or not self.source_files_sha256
            or "LangGraph" not in self.executed
        ):
            raise ValueError(
                "A pass requires observed graph execution and complete evidence"
            )
        return self
