"""Tests for the internal QA/repair registry and plugin loader."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory

from langgraph_system_generator.generator.state import CellSpec, QAReport
from langgraph_system_generator.notebook.composer import (
    NotebookComposer as NotebookFileComposer,
)
from langgraph_system_generator.qa.registry import (
    QARepairRegistry,
    RepairRoutineRegistration,
    get_qa_repair_registry,
)
from langgraph_system_generator.qa.repair import NotebookRepairAgent
from langgraph_system_generator.qa.validators import (
    NotebookValidationContext,
    NotebookValidator,
    QAValidationRule,
)


class CustomMarkerRule(QAValidationRule):
    """Fail when a synthetic marker remains in notebook content."""

    rule_id = "custom_marker"
    check_name = "Custom Marker"
    category = "custom"
    failure_severity = "error"
    repairable = True

    def validate(self, context: NotebookValidationContext) -> QAReport:
        content = "\n".join(str(cell.source or "") for cell in context.notebook.cells)
        if "BROKEN_PLUGIN_MARKER" in content:
            return self.failed_report(
                "Custom marker was not repaired.",
                evidence={"marker": "BROKEN_PLUGIN_MARKER"},
            )
        return self.passed_report("Custom marker is absent.")


def _valid_graph_cells(*, execution_content: str | None = None) -> list[CellSpec]:
    """Return a minimal valid notebook cell set for registry tests."""

    return [
        CellSpec(
            cell_type="code",
            content="from langgraph.graph import END, START, StateGraph\nfrom typing import TypedDict",
            metadata={"section": "setup"},
            section="setup",
        ),
        CellSpec(
            cell_type="code",
            content='config = {"configurable": {"thread_id": "demo"}, "recursion_limit": 25}',
            metadata={"section": "config"},
            section="config",
        ),
        CellSpec(
            cell_type="code",
            content=(
                "class WorkflowState(TypedDict, total=False):\n"
                "    messages: list\n\n"
                "workflow = StateGraph(WorkflowState)\n\n"
                "def start_node(state: WorkflowState):\n"
                "    return {}\n\n"
                "workflow.add_node('start', start_node)\n"
                "workflow.add_edge(START, 'start')\n"
                "workflow.add_edge('start', END)\n"
                "graph = workflow.compile()"
            ),
            metadata={"section": "graph"},
            section="graph",
        ),
        CellSpec(
            cell_type="code",
            content=execution_content
            or (
                'initial_state = {"messages": []}\n'
                "result = graph.invoke(initial_state, config)\nprint(result)"
            ),
            metadata={"section": "execution"},
            section="execution",
        ),
    ]


def _validate_cells(cells: list[CellSpec], validator: NotebookValidator) -> list[QAReport]:
    """Validate cells through the notebook file path used by production nodes."""

    builder = NotebookFileComposer()
    with TemporaryDirectory() as temp_dir:
        notebook = builder.build_notebook(cells)
        notebook_path = Path(temp_dir) / "generated.ipynb"
        builder.write(notebook, notebook_path)
        return validator.validate_all(notebook_path)


def _custom_repair_handler(_agent, notebook, _report) -> list[str]:
    """Replace a synthetic marker in code cells."""

    fixes: list[str] = []
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = str(cell.source or "")
        updated = source.replace("BROKEN_PLUGIN_MARKER", "REPAIRED_PLUGIN_MARKER")
        if updated != source:
            cell.source = updated
            fixes.append("Repaired custom plugin marker.")
    return fixes


def _install_plugin_module(name: str, register_func) -> None:
    """Install an in-memory plugin module for loader tests."""

    module = types.ModuleType(name)
    module.register_qa_repair_plugins = register_func
    sys.modules[name] = module


def test_default_registry_contains_builtin_validators_and_repairs():
    registry = get_qa_repair_registry(plugin_modules=())

    assert registry.registered_validator_ids() == [
        "placeholder_content",
        "required_sections",
        "required_import_symbols",
        "python_syntax",
        "undefined_names",
        "graph_structure",
        "canonical_section_order",
        "langgraph_topology",
        "canonical_graph_contract",
        "state_reducer_semantics",
        "tool_reachability",
        "chatbot_notebook_contract",
        "domain_architecture_alignment",
        "generated_llm_config",
        "invocation_config",
    ]
    assert registry.registered_repair_routine_ids() == [
        "placeholder_cleanup",
        "required_sections",
        "required_import_symbols",
        "undefined_name_typo",
        "bounded_syntax",
        "graph_scaffold",
    ]


def test_explicit_empty_repair_routines_are_preserved():
    registry = QARepairRegistry(repair_routines=())
    clone = registry.clone()
    agent = NotebookRepairAgent(registry=registry)

    assert registry.registered_repair_routine_ids() == []
    assert clone.registered_repair_routine_ids() == []
    assert agent.registry.registered_repair_routine_ids() == []


def test_custom_validator_injection_works():
    registry = get_qa_repair_registry(plugin_modules=())
    registry.register_validator(CustomMarkerRule())
    validator = NotebookValidator(registry=registry)
    cells = _valid_graph_cells(
        execution_content='marker = "BROKEN_PLUGIN_MARKER"\nprint(marker)'
    )

    reports = _validate_cells(cells, validator)

    assert any(
        report.rule_id == "custom_marker" and not report.passed
        for report in reports
    )


def test_disabling_validator_removes_it_from_validate_all():
    registry = get_qa_repair_registry(plugin_modules=())
    assert registry.disable_validator("placeholder_content") is True
    validator = NotebookValidator(registry=registry)
    cells = _valid_graph_cells(execution_content="# TODO: normally flagged\nprint('ok')")

    reports = _validate_cells(cells, validator)

    assert "placeholder_content" not in {report.rule_id for report in reports}


def test_custom_repair_routine_injection_works():
    registry = get_qa_repair_registry(plugin_modules=())
    registry.register_validator(CustomMarkerRule())
    registry.register_repair_routine(
        RepairRoutineRegistration(
            routine_id="custom_marker_repair",
            handled_rule_ids=("custom_marker",),
            handler=_custom_repair_handler,
        )
    )
    agent = NotebookRepairAgent(registry=registry)
    cells = _valid_graph_cells(
        execution_content='marker = "BROKEN_PLUGIN_MARKER"\nprint(marker)'
    )
    reports = _validate_cells(cells, agent.validator)

    outcome = agent.repair_cells(cells, reports)

    assert outcome.success is True
    assert "Repaired custom plugin marker." in outcome.attempted_fixes
    assert "BROKEN_PLUGIN_MARKER" not in "\n".join(cell.content for cell in outcome.cells)
    assert any(report.rule_id == "custom_marker" and report.passed for report in outcome.qa_reports)


def test_plugin_module_loading_registers_custom_extensions(monkeypatch):
    module_name = "test_qa_repair_plugin"

    def register(registry: QARepairRegistry) -> None:
        registry.register_validator(CustomMarkerRule())
        registry.register_repair_routine(
            RepairRoutineRegistration(
                routine_id="plugin_marker_repair",
                handled_rule_ids=("custom_marker",),
                handler=_custom_repair_handler,
            )
        )

    _install_plugin_module(module_name, register)
    monkeypatch.setattr(
        "langgraph_system_generator.qa.registry.settings.qa_repair_plugin_modules",
        [module_name],
    )

    registry = get_qa_repair_registry()

    assert "custom_marker" in registry.registered_validator_ids()
    assert "plugin_marker_repair" in registry.registered_repair_routine_ids()


def test_plugin_module_loading_accepts_comma_separated_module_strings():
    module_one = "test_qa_repair_plugin_one"
    module_two = "test_qa_repair_plugin_two"

    def register_one(registry: QARepairRegistry) -> None:
        registry.register_validator(CustomMarkerRule())

    def register_two(registry: QARepairRegistry) -> None:
        registry.register_repair_routine(
            RepairRoutineRegistration(
                routine_id="plugin_marker_repair",
                handled_rule_ids=("custom_marker",),
                handler=_custom_repair_handler,
            )
        )

    _install_plugin_module(module_one, register_one)
    _install_plugin_module(module_two, register_two)

    registry = get_qa_repair_registry(
        plugin_modules=f"{module_one}, {module_two}"
    )

    assert "custom_marker" in registry.registered_validator_ids()
    assert "plugin_marker_repair" in registry.registered_repair_routine_ids()


def test_plugin_module_without_entrypoint_raises_actionable_value_error(monkeypatch):
    module_name = "test_qa_repair_plugin_without_entrypoint"
    sys.modules[module_name] = types.ModuleType(module_name)

    try:
        get_qa_repair_registry(plugin_modules=(module_name,))
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("Expected plugin loader to reject missing entrypoint.")

    assert module_name in message
    assert "register_qa_repair_plugins" in message


def test_plugin_module_hook_failure_raises_actionable_value_error():
    module_name = "test_qa_repair_plugin_hook_failure"

    def register(_registry: QARepairRegistry) -> None:
        raise RuntimeError("boom")

    _install_plugin_module(module_name, register)

    try:
        get_qa_repair_registry(plugin_modules=(module_name,))
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("Expected plugin loader to wrap hook failures.")

    assert module_name in message
    assert "boom" in message
    assert "register_qa_repair_plugins" in message


def test_missing_plugin_module_raises_actionable_value_error():
    module_name = "test_qa_repair_plugin_does_not_exist"

    try:
        get_qa_repair_registry(plugin_modules=(module_name,))
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("Expected plugin loader to wrap import failures.")

    assert module_name in message
    assert "Failed to import QA/repair plugin module" in message
