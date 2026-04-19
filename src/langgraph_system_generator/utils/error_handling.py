"""Structured error types for generation surfaces."""

from __future__ import annotations

from typing import Any, Dict


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
            "message": str(self),
            "status_code": self.status_code,
        }
        if self.phase:
            payload["phase"] = self.phase
        if self.hint:
            payload["hint"] = self.hint
        if self.details:
            payload["details"] = self.details
        return payload
