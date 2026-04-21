"""Unit tests for shared logging configuration."""

from __future__ import annotations

import logging

import pytest

from langgraph_system_generator.utils.logging import (
    TRACE_LEVEL_NUM,
    configure_logging,
)


def test_configure_logging_prefers_explicit_level_over_env(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LNF_LOG_LEVEL", "ERROR")

    resolved = configure_logging("DEBUG", force=True)

    assert resolved == "DEBUG"
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_supports_trace_level(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LNF_LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    resolved = configure_logging("TRACE", force=True)

    assert resolved == "TRACE"
    assert logging.getLogger().level == TRACE_LEVEL_NUM


def test_configure_logging_invalid_level_falls_back_to_info(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.WARNING, logger="langgraph_system_generator.utils.logging")

    resolved = configure_logging("NOT_A_LEVEL", force=True)

    assert resolved == "INFO"
    assert logging.getLogger().level == logging.INFO
    assert any(
        "Unsupported log level" in record.message
        for record in caplog.records
    )
