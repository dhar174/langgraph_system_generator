"""Structured error types for generation surfaces."""

from __future__ import annotations

from typing import Any, Dict

from langgraph_system_generator.utils.credential_redaction import (
    _sanitize_text_credentials,
    sanitize_generation_payload,
)


def safe_exception_summary(exc: Exception) -> str:
    """Classify provider failures without reflecting untrusted exception bodies."""
    summary = type(exc).__name__
    # Fixed validation categories preserve useful feedback without echoing model
    # payloads, exception input values, provider bodies, or credentials.
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        for category in (
            "must include a non-empty type",
            "Unsupported constraint type",
            "Unsupported architecture_type",
            "non-empty justification",
            "primary pattern did not match architecture_type",
            "unsupported primary",
            "malformed patterns",
        ):
            if category in str(exc):
                return summary + ": " + category
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        summary += f" (HTTP {status})"
    if isinstance(exc, GenerationError):
        summary += f": {exc.code}"
    return summary


class GenerationError(RuntimeError):
    """A normalized error that can be surfaced consistently across CLI/API/UI."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "generation_error",
        phase: str | None = None,
        hint: str | None = None,
        details: Dict[str, Any] | None = None,
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.hint = hint
        self.details = details or {}
        self.status_code = status_code

    def to_payload(self) -> Dict[str, Any]:
        """Serialize this error into an API-safe payload."""

        payload: Dict[str, Any] = {
            "code": self.code,
            "message": _sanitize_text_credentials(str(self)),
            "status_code": self.status_code,
        }
        if self.phase:
            payload["phase"] = self.phase
        if self.hint:
            payload["hint"] = _sanitize_text_credentials(self.hint)
        if self.details:
            payload["details"] = self.details
        return sanitize_generation_payload(payload)
