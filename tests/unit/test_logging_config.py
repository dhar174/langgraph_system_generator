"""Unit tests for shared logging configuration."""

from __future__ import annotations

import logging

import pytest

from langgraph_system_generator.utils.logging_utils import (
    TRACE_LEVEL_NUM,
    configure_logging,
)


@pytest.fixture(autouse=True)
def _reset_logging_configuration():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_configure_logging_prefers_explicit_level_over_env(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LNF_LOG_LEVEL", "ERROR")

    configure_logging("DEBUG")

    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_supports_trace_level(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LNF_LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    configure_logging("TRACE")

    assert logging.getLogger().level == TRACE_LEVEL_NUM


def test_configure_logging_invalid_level_falls_back_to_info(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.WARNING, logger="langgraph_system_generator.utils.logging_utils")

    configure_logging("NOT_A_LEVEL")

    assert logging.getLogger().level == logging.INFO
    assert any(
        "Unsupported log level" in record.message
        for record in caplog.records
    )
