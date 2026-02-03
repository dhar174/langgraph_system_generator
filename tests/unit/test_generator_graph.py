"""Tests for generator graph routing helpers."""

import pytest

from langgraph_system_generator.generator.graph import (
    should_repair,
    should_retry_after_repair,
)
from langgraph_system_generator.generator.state import QAReport
from langgraph_system_generator.utils.config import settings


@pytest.fixture
def passing_report() -> QAReport:
    """Return a passing QA report."""
    return QAReport(
        check_name="No Placeholders",
        passed=True,
        message="OK",
        suggestions=[],
    )


@pytest.fixture
def failing_report() -> QAReport:
    """Return a failing QA report."""
    return QAReport(
        check_name="Graph Compilation",
        passed=False,
        message="Compilation failed",
        suggestions=["Fix graph"],
    )


def build_state(**overrides):
    """Create a minimal generator state for routing helpers."""
    base_state = {
        "qa_reports": [],
        "repair_attempts": 0,
        "generated_cells": [],
    }
    base_state.update(overrides)
    return base_state


def test_should_repair_all_passing(passing_report):
    """All QA reports passing should package."""
    state = build_state(qa_reports=[passing_report], repair_attempts=0)

    assert should_repair(state) == "package"


def test_should_repair_mixed_reports(passing_report, failing_report):
    """Mixed passing and failing reports should repair when failures exist."""
    state = build_state(
        qa_reports=[passing_report, failing_report, passing_report],
        repair_attempts=0,
    )

    assert should_repair(state) == "repair"


@pytest.mark.skipif(settings.max_repair_attempts < 2, reason="Requires max_repair_attempts >= 2")
def test_should_repair_attempts_remaining(failing_report):
    """Failures with attempts remaining should repair."""
    state = build_state(
        qa_reports=[failing_report],
        repair_attempts=settings.max_repair_attempts - 1,
    )

    assert should_repair(state) == "repair"


def test_should_repair_attempts_exhausted(failing_report):
    """Failures with attempts exhausted should fail."""
    state = build_state(
        qa_reports=[failing_report],
        repair_attempts=settings.max_repair_attempts,
    )

    assert should_repair(state) == "fail"


@pytest.mark.skipif(settings.max_repair_attempts < 2, reason="Requires max_repair_attempts >= 2")
def test_should_retry_after_repair_attempts_remaining():
    """Post-repair with attempts remaining should retry QA."""
    state = build_state(repair_attempts=settings.max_repair_attempts - 1)

    assert should_retry_after_repair(state) == "retry_qa"


def test_should_retry_after_repair_attempts_exhausted_with_cells():
    """Post-repair with attempts exhausted and cells should succeed."""
    state = build_state(
        repair_attempts=settings.max_repair_attempts,
        generated_cells=[{"cell_type": "code", "content": "print('ok')", "metadata": {}}],
    )

    assert should_retry_after_repair(state) == "success"


def test_should_retry_after_repair_attempts_exhausted_no_cells():
    """Post-repair with attempts exhausted and no cells should fail."""
    state = build_state(
        repair_attempts=settings.max_repair_attempts,
        generated_cells=[],
    )

    assert should_retry_after_repair(state) == "fail"
