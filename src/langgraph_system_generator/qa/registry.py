"""Internal registry for QA validation rules and deterministic repair routines."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable, Iterable, List, Protocol, Sequence

from nbformat import NotebookNode

from langgraph_system_generator.generator.state import QAReport
from langgraph_system_generator.qa.validators import (
    CanonicalGraphContractRule,
    CanonicalSectionOrderRule,
    ChatbotNotebookContractRule,
    DomainArchitectureAlignmentRule,
    GeneratedLLMConfigRule,
    GraphStructureRule,
    InvocationConfigRule,
    LangGraphTopologyRule,
    PlaceholderRule,
    PythonSyntaxRule,
    QAValidationRule,
    RequiredImportsRule,
    RequiredSectionsRule,
    StateReducerSemanticsRule,
    ToolReachabilityRule,
    UndefinedNameRule,
    ValidatorRegistry,
)
from langgraph_system_generator.utils.config import settings


class SupportsRepairRoutineHandler(Protocol):
    """Structural typing contract for deterministic repair handlers."""

    def _repair_placeholders(self, notebook: NotebookNode) -> List[str]: ...

    def _repair_sections(
        self,
        notebook: NotebookNode,
        report: QAReport,
    ) -> List[str]: ...

    def _repair_imports(
        self,
        notebook: NotebookNode,
        report: QAReport,
    ) -> List[str]: ...

    def _repair_undefined_names(
        self,
        notebook: NotebookNode,
        report: QAReport,
    ) -> List[str]: ...

    def _repair_syntax(
        self,
        notebook: NotebookNode,
        report: QAReport,
    ) -> List[str]: ...

    def _repair_graph_scaffold(
        self,
        notebook: NotebookNode,
        report: QAReport,
    ) -> List[str]: ...


RepairRoutineCallable = Callable[
    [SupportsRepairRoutineHandler, NotebookNode, QAReport],
    List[str],
]


@dataclass(frozen=True)
class RepairRoutineRegistration:
    """Registered deterministic repair routine metadata."""

    routine_id: str
    handled_rule_ids: Sequence[str]
    handler: RepairRoutineCallable
    description: str = ""
    handled_check_names: Sequence[str] = ()

    def normalized(self) -> "RepairRoutineRegistration":
        """Return a normalized registration with validated identifiers."""

        routine_id = self.routine_id.strip()
        handled_rule_ids = tuple(
            dict.fromkeys(rule_id.strip() for rule_id in self.handled_rule_ids if rule_id.strip())
        )
        handled_check_names = tuple(
            dict.fromkeys(
                check_name.strip()
                for check_name in self.handled_check_names
                if check_name.strip()
            )
        )
        if not routine_id:
            raise ValueError("Repair routine registrations require a non-empty routine_id.")
        if not handled_rule_ids and not handled_check_names:
            raise ValueError(
                f"Repair routine '{routine_id}' must handle at least one rule id or check name."
            )
        if not callable(self.handler):
            raise ValueError(f"Repair routine '{routine_id}' handler must be callable.")
        return RepairRoutineRegistration(
            routine_id=routine_id,
            handled_rule_ids=handled_rule_ids,
            handler=self.handler,
            description=self.description.strip(),
            handled_check_names=handled_check_names,
        )


class QARepairRegistry:
    """Registry for internal QA validation rules and repair routines."""

    def __init__(
        self,
        *,
        validator_registry: ValidatorRegistry | None = None,
        repair_routines: Iterable[RepairRoutineRegistration] | None = None,
    ):
        self._validator_registry = (
            validator_registry.clone()
            if validator_registry is not None
            else build_default_validator_registry()
        )
        self._repair_routines: dict[str, RepairRoutineRegistration] = {}
        routines = (
            build_default_repair_routines()
            if repair_routines is None
            else repair_routines
        )
        for routine in routines:
            self.register_repair_routine(routine)

    def clone(self) -> "QARepairRegistry":
        """Return a shallow clone that preserves rule/routine state."""

        return QARepairRegistry(
            validator_registry=self._validator_registry,
            repair_routines=list(self._repair_routines.values()),
        )

    def validator_registry(self) -> ValidatorRegistry:
        """Return a clone of the validator-rule registry."""

        return self._validator_registry.clone()

    def register_validator(self, rule: QAValidationRule) -> QAValidationRule:
        """Register or replace a validator rule."""

        self._validator_registry.register(rule)
        return rule

    def disable_validator(self, rule_id: str) -> bool:
        """Disable a validator rule by id, returning whether a rule was removed."""

        return self._validator_registry.disable(rule_id)

    def registered_validator_ids(self) -> List[str]:
        """Return registered validator rule ids in execution order."""

        return self._validator_registry.rule_ids()

    def register_repair_routine(
        self,
        registration: RepairRoutineRegistration,
    ) -> RepairRoutineRegistration:
        """Register or replace a deterministic repair routine."""

        normalized = registration.normalized()
        self._repair_routines[normalized.routine_id] = normalized
        return normalized

    def disable_repair_routine(self, routine_id: str) -> bool:
        """Disable a repair routine by id, returning whether one was removed."""

        return self._repair_routines.pop(routine_id.strip(), None) is not None

    def registered_repair_routine_ids(self) -> List[str]:
        """Return registered repair routine ids in dispatch order."""

        return list(self._repair_routines)

    def repair_routines_for(self, report: QAReport) -> List[RepairRoutineRegistration]:
        """Return repair routines that can handle the supplied QA report."""

        matches: List[RepairRoutineRegistration] = []
        for routine in self._repair_routines.values():
            if report.rule_id in routine.handled_rule_ids:
                matches.append(routine)
                continue
            if report.check_name in routine.handled_check_names:
                matches.append(routine)
        return matches


def build_default_validator_registry() -> ValidatorRegistry:
    """Create the default ordered validation registry."""

    return ValidatorRegistry(
        [
            PlaceholderRule(
                [
                    "TODO",
                    "FIXME",
                    "PLACEHOLDER",
                    "...",
                    "# Your code here",
                    "pass  # implement",
                ]
            ),
            RequiredSectionsRule(["setup", "config", "graph", "execution"]),
            RequiredImportsRule(["langgraph", "StateGraph", "END"]),
            PythonSyntaxRule(),
            UndefinedNameRule(),
            GraphStructureRule(),
            CanonicalSectionOrderRule(),
            LangGraphTopologyRule(),
            CanonicalGraphContractRule(),
            StateReducerSemanticsRule(),
            ToolReachabilityRule(),
            ChatbotNotebookContractRule(),
            DomainArchitectureAlignmentRule(),
            GeneratedLLMConfigRule(),
            InvocationConfigRule(),
        ]
    )


def build_default_repair_routines() -> List[RepairRoutineRegistration]:
    """Create the default repair routine registrations."""

    return [
        RepairRoutineRegistration(
            routine_id="placeholder_cleanup",
            handled_rule_ids=("placeholder_content",),
            handled_check_names=("No Placeholders",),
            handler=lambda agent, notebook, _report: agent._repair_placeholders(notebook),
            description="Remove deterministic placeholder markers from code cells.",
        ),
        RepairRoutineRegistration(
            routine_id="required_sections",
            handled_rule_ids=("required_sections",),
            handled_check_names=("Required Sections",),
            handler=lambda agent, notebook, report: agent._repair_sections(notebook, report),
            description="Add deterministic fallback cells for missing required sections.",
        ),
        RepairRoutineRegistration(
            routine_id="required_import_symbols",
            handled_rule_ids=("required_import_symbols",),
            handled_check_names=("Required Imports",),
            handler=lambda agent, notebook, report: agent._repair_imports(notebook, report),
            description="Merge missing LangGraph imports into the setup section.",
        ),
        RepairRoutineRegistration(
            routine_id="undefined_name_typo",
            handled_rule_ids=("undefined_names",),
            handler=lambda agent, notebook, report: agent._repair_undefined_names(notebook, report),
            description="Apply validator-provided close-match symbol replacements.",
        ),
        RepairRoutineRegistration(
            routine_id="bounded_syntax",
            handled_rule_ids=("python_syntax",),
            handler=lambda agent, notebook, report: agent._repair_syntax(notebook, report),
            description="Apply bounded deterministic syntax fixes.",
        ),
        RepairRoutineRegistration(
            routine_id="graph_scaffold",
            handled_rule_ids=("graph_structure",),
            handled_check_names=("Graph Compilation",),
            handler=lambda agent, notebook, report: agent._repair_graph_scaffold(notebook, report),
            description="Append deterministic LangGraph scaffold when graph wiring is incomplete.",
        ),
    ]


def get_qa_repair_registry(
    plugin_modules: Sequence[str] | str | None = None,
) -> QARepairRegistry:
    """Build the QA/repair registry and load configured internal plugins."""

    registry = QARepairRegistry()
    _load_plugin_modules(
        registry,
        settings.qa_repair_plugin_modules if plugin_modules is None else plugin_modules,
    )
    return registry


def _load_plugin_modules(
    registry: QARepairRegistry,
    plugin_modules: Sequence[str] | str | None,
) -> None:
    """Load QA/repair plugin modules into the registry."""

    for module_name in _normalize_plugin_modules(plugin_modules):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - exercised by plugin tests
            raise ValueError(
                f"Failed to import QA/repair plugin module '{module_name}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        entrypoint = getattr(module, "register_qa_repair_plugins", None)
        if not callable(entrypoint):
            raise ValueError(
                f"QA/repair plugin module '{module_name}' must define "
                "register_qa_repair_plugins(registry)."
            )

        try:
            entrypoint(registry)
        except Exception as exc:
            raise ValueError(
                f"QA/repair plugin module '{module_name}' failed while running "
                "register_qa_repair_plugins(registry): "
                f"{type(exc).__name__}: {exc}"
            ) from exc


def _normalize_plugin_modules(
    plugin_modules: Sequence[str] | str | None,
) -> List[str]:
    """Return de-duplicated plugin module names."""

    if isinstance(plugin_modules, str):
        plugin_modules = [plugin_modules]
    normalized: List[str] = []
    for raw_item in plugin_modules or []:
        for raw_module in str(raw_item).split(","):
            module_name = raw_module.strip()
            if module_name and module_name not in normalized:
                normalized.append(module_name)
    return normalized
