"""QA and repair tooling for notebook validation and fixing."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "NotebookRepairAgent",
    "NotebookValidator",
    "QARepairRegistry",
    "RepairRoutineRegistration",
    "get_qa_repair_registry",
]

_EXPORT_MODULES = {
    "NotebookValidator": "langgraph_system_generator.qa.validators",
    "NotebookRepairAgent": "langgraph_system_generator.qa.repair",
    "QARepairRegistry": "langgraph_system_generator.qa.registry",
    "RepairRoutineRegistration": "langgraph_system_generator.qa.registry",
    "get_qa_repair_registry": "langgraph_system_generator.qa.registry",
}


def __getattr__(name: str):
    """Lazily expose QA helpers so core imports do not require notebook extras."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_name), name)
