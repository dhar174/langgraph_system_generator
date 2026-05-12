"""Tests for generator graph routing helpers."""

import pytest

from langgraph_system_generator.generator.graph import (
    should_repair,
    should_retry_after_repair,
)
from langgraph_system_generator.generator.state import CellSpec, QAReport
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
        severity="error",
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


def test_should_repair_empty_reports():
    """Empty QA reports list should package."""
    state = build_state(qa_reports=[], repair_attempts=0)

    assert should_repair(state) == "package"


def test_should_repair_mixed_reports(passing_report, failing_report):
    """Mixed passing and failing reports should repair when failures exist."""
    state = build_state(
        qa_reports=[passing_report, failing_report, passing_report],
        repair_attempts=0,
    )

    assert should_repair(state) == "repair"


def test_should_repair_advisory_only_reports_package(passing_report):
    """Warning/info QA findings should be packaged as advisories."""

    warning_report = QAReport(
        check_name="Undefined Names",
        passed=False,
        message="Define or import 'app' before it is used.",
        rule_id="undefined_names",
        severity="warning",
        suggestions=["Check graph object naming."],
    )
    state = build_state(
        qa_reports=[passing_report, warning_report],
        repair_attempts=0,
    )

    assert should_repair(state) == "package"


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


def test_should_repair_runtime_unavailable_live_fails_fast():
    """Live runtime unavailability should fail instead of entering repair."""
    runtime_report = QAReport(
        check_name="Runtime Check",
        passed=False,
        message="Runtime validation unavailable: kernel 'python3' is not registered.",
        severity="error",
        stage="runtime",
        evidence={"failure_kind": "runtime_unavailable", "generation_mode": "live"},
    )
    state = build_state(qa_reports=[runtime_report], repair_attempts=0)

    assert should_repair(state) == "fail"


@pytest.mark.skipif(settings.max_repair_attempts < 2, reason="Requires max_repair_attempts >= 2")
def test_should_retry_after_repair_attempts_remaining():
    """Post-repair with attempts remaining should retry QA."""
    state = build_state(repair_attempts=settings.max_repair_attempts - 1)

    assert should_retry_after_repair(state) == "retry_qa"


def test_should_retry_after_repair_attempts_exhausted_with_cells():
    """Post-repair with attempts exhausted and cells should succeed."""
    cell = CellSpec(cell_type="code", content="print('ok')", metadata={})
    state = build_state(
        repair_attempts=settings.max_repair_attempts,
        generated_cells=[cell],
    )

    assert should_retry_after_repair(state) == "success"


def test_should_retry_after_repair_attempts_exhausted_no_cells():
    """Post-repair with attempts exhausted and no cells should fail."""
    state = build_state(
        repair_attempts=settings.max_repair_attempts,
        generated_cells=[],
    )

    assert should_retry_after_repair(state) == "fail"
