from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RepoProfile:
    """Structured inventory of a repository that will receive an agent stack."""

    repo_name: str
    repo_root: str
    purpose: str
    primary_languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)
    repo_map: dict[str, str] = field(default_factory=dict)
    high_signal_files: list[str] = field(default_factory=list)
    major_workflows: list[str] = field(default_factory=list)
    risky_boundaries: list[str] = field(default_factory=list)
    ci_files: list[str] = field(default_factory=list)
    source_documents: list[str] = field(default_factory=list)
    existing_ai_assets: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentSpec:
    """Suggested custom agent profile for a generated stack."""

    slug: str
    display_name: str
    description: str
    tools: list[str]
    responsibilities: list[str]
    focus_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExternalSource:
    """Pinned third-party content that may be vendored into a target repo."""

    name: str
    url: str
    revision: str
    path: str
    license: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ValidationIssue:
    """Single validation finding."""

    level: str
    message: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ValidationReport:
    """Validation result for a generated or maintained stack."""

    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add_error(self, message: str, path: str | None = None) -> None:
        self.errors.append(ValidationIssue(level="error", message=message, path=path))

    def add_warning(self, message: str, path: str | None = None) -> None:
        self.warnings.append(ValidationIssue(level="warning", message=message, path=path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }
