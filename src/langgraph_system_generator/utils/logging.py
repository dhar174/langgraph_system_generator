"""Shared logging configuration utilities."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

TRACE_LEVEL_NUM = 5
LOG_LEVEL_CHOICES = (
    "TRACE",
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
)
_VALID_LEVEL_NAMES = set(LOG_LEVEL_CHOICES)


def _ensure_trace_level() -> None:
    """Register a TRACE level and logger convenience method once."""
    if logging.getLevelName(TRACE_LEVEL_NUM) != "TRACE":
        logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")

    if not hasattr(logging.Logger, "trace"):
        def trace(
            self,
            message: str,
            *args: object,
            **kwargs: object,
        ) -> None:
            self.log(TRACE_LEVEL_NUM, message, *args, **kwargs)

        logging.Logger.trace = trace  # type: ignore[attr-defined]


def _resolve_level_name(level: str | None) -> str:
    """Resolve an effective log level from explicit value or environment."""
    candidate = (
        level
        or os.getenv("LNF_LOG_LEVEL")
        or os.getenv("LOG_LEVEL")
        or "INFO"
    )
    normalized = str(candidate).strip().upper()

    if normalized in _VALID_LEVEL_NAMES:
        return normalized

    logger.warning(
        "Unsupported log level %r; falling back to INFO.",
        candidate,
    )
    return "INFO"


def configure_logging(level: str | None = None, *, force: bool = False) -> str:
    """Configure application logging and return the effective level name."""
    level_name = _resolve_level_name(level)
    _ensure_trace_level()

    numeric_level = TRACE_LEVEL_NUM if level_name == "TRACE" else getattr(
        logging, level_name, logging.INFO
    )
    root_logger = logging.getLogger()

    if force:
        root_logger.handlers.clear()

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
            )
        )
        root_logger.addHandler(handler)

    root_logger.setLevel(numeric_level)
    for handler in root_logger.handlers:
        handler.setLevel(numeric_level)

    return level_name
