"""QA and repair tooling for notebook validation and fixing."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph_system_generator.qa.registry import (
        QARepairRegistry,
        RepairRoutineRegistration,
        get_qa_repair_registry,
    )
    from langgraph_system_generator.qa.repair import NotebookRepairAgent
    from langgraph_system_generator.qa.validators import NotebookValidator

__all__ = [
    "NotebookValidator",
    "NotebookRepairAgent",
    "QARepairRegistry",
    "RepairRoutineRegistration",
    "get_qa_repair_registry",
]


def __getattr__(name: str) -> Any:
    """Keep typed QA contracts importable without validator/notebook SDKs."""
    if name not in __all__:
        raise AttributeError(name)
    module = (
        "validators"
        if name == "NotebookValidator"
        else "repair" if name == "NotebookRepairAgent" else "registry"
    )
    return getattr(import_module(f"{__name__}.{module}"), name)

