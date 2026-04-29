"""Centralized logging configuration helpers for CLI/API surfaces."""

from __future__ import annotations

import logging
import os
import time

DEFAULT_LOG_FORMAT = "%(asctime)sZ %(levelname)s [%(name)s] %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
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


def _parse_level(level: str | int | None) -> int:
    """Return a numeric logging level from string/int input."""

    if isinstance(level, int):
        return level

    if isinstance(level, str):
        normalized = level.strip().upper()
        if normalized == "TRACE":
            return TRACE_LEVEL_NUM
        if normalized in _VALID_LEVEL_NAMES:
            resolved_level = getattr(logging, normalized, logging.INFO)
            return resolved_level if isinstance(resolved_level, int) else logging.INFO
        logging.getLogger(__name__).warning(
            "Unsupported log level %r; falling back to INFO.",
            level,
        )

    return logging.INFO


def configure_logging(level: str | int = "INFO", *, fmt: str = DEFAULT_LOG_FORMAT) -> None:
    """Configure root logging with a consistent format and level.

    The function is idempotent: it reuses existing handlers instead of adding
    duplicates, and updates the root/handler levels when called again.
    """

    _ensure_trace_level()
    numeric_level = _parse_level(level)
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        default_handler = logging.StreamHandler()
        default_handler.setLevel(numeric_level)
        default_handler.setFormatter(
            logging.Formatter(fmt=fmt, datefmt=DEFAULT_DATE_FORMAT)
        )
        # Use UTC timestamps and suffix logs with "Z"
        default_handler.formatter.converter = time.gmtime if default_handler.formatter else None  # type: ignore[assignment]
        root_logger.addHandler(default_handler)
    else:
        for handler in root_logger.handlers:
            handler.setLevel(numeric_level)
            if handler.formatter is None:
                formatter = logging.Formatter(
                    fmt=fmt, datefmt=DEFAULT_DATE_FORMAT
                )
                formatter.converter = time.gmtime  # type: ignore[assignment]
                handler.setFormatter(formatter)
            else:
                # Replace the existing formatter entirely to avoid touching
                # private logging internals (_style._fmt etc.).
                replacement = logging.Formatter(fmt=fmt, datefmt=DEFAULT_DATE_FORMAT)
                replacement.converter = time.gmtime  # type: ignore[assignment]
                handler.setFormatter(replacement)

    non_capture_handlers = [
        handler
        for handler in root_logger.handlers
        if handler.__class__.__name__ != "LogCaptureHandler"
    ]
    if not non_capture_handlers:
        default_handler = logging.StreamHandler()
        default_handler.setLevel(numeric_level)
        default_handler.setFormatter(
            logging.Formatter(fmt=fmt, datefmt=DEFAULT_DATE_FORMAT)
        )
        default_handler.formatter.converter = time.gmtime if default_handler.formatter else None  # type: ignore[assignment]
        root_logger.addHandler(default_handler)

    root_logger.setLevel(numeric_level)
    logging.captureWarnings(True)


def configure_logging_from_env(
    env_var: str = "LNF_LOG_LEVEL", *, default: str | int = "INFO"
) -> None:
    """Configure logging from an environment variable fallback."""

    configure_logging(os.getenv(env_var) or os.getenv("LOG_LEVEL") or default)
