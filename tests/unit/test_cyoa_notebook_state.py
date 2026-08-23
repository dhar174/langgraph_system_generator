"""Regression tests for the checked-in CYOA sample notebook."""

from __future__ import annotations

import ast
import json
import os
import re
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List


NOTEBOOK_PATH = (
    Path(__file__).resolve().parents[2]
    / "sample_outputs"
    / "cyoa_c_notebook_fixed.ipynb"
)


def _cell_source(marker: str) -> str:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        source = "".join(cell.get("source", []))
        if marker in source:
            return source
    raise AssertionError(f"Notebook cell containing {marker!r} was not found")


def _definition(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function {name!r} was not found")


def _method_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith(f"    def {name}(")
    )
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("    def ")
            or (lines[index] and not lines[index].startswith((" ", "\t")))
        ),
        len(lines),
    )
    return textwrap.dedent("\n".join(lines[start:end]))


def _load_function(source: str, name: str, namespace: dict[str, Any]):
    node = _definition(source, name)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, str(NOTEBOOK_PATH), "exec"), namespace)
    return namespace[name]


def test_story_generation_uses_canonical_config_and_preserves_turn() -> None:
    captured: dict[str, Any] = {}

    class FakeAIMessage:
        def __init__(self, content: str):
            self.content = content

    def story_writer(**kwargs):
        captured.update(kwargs)
        return "A draft segment"

    namespace = {
        "AIMessage": FakeAIMessage,
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "LLM_ChoiceArchitect": lambda **_kwargs: ["One", "Two", "Three"],
        "LLM_Lorekeeper": lambda **_kwargs: {
            "memory_summary": "memory",
            "facts": {"clue": "found"},
        },
        "LLM_StoryWriter": story_writer,
        "WorkflowState": dict,
        "llm_continuity_editor": lambda segment, **_kwargs: segment,
        "llm_safety_guard": lambda segment, **_kwargs: segment,
        "os": os,
        "re": re,
        "time": time,
    }
    story_gen_node = _load_function(
        _cell_source("def story_gen_node"), "story_gen_node", namespace
    )

    state = {
        "user_name": "Alex",
        "user_age": 30,
        "user_pronouns": "xe/xem",
        "story_genre": "mystery",
        "story_setting": "a lunar archive",
        "story_theme": "trust",
        "turn_index": 0,
        "max_turns": 1,
    }
    result = story_gen_node(state)

    assert "mystery" in captured["user_info"]
    assert "a lunar archive" in captured["user_info"]
    assert "trust" in captured["user_info"]
    assert "they" in captured["user_info"]
    assert result["turn_index"] == 0
    assert result["run_status"] == "waiting_for_human"

    state["user_pronouns"] = "she/her"
    story_gen_node(state)
    assert "she is 30 years old" in captured["user_info"]


def test_ui_initial_state_keeps_canonical_story_keys() -> None:
    workflow_state = next(
        node
        for node in ast.parse(_cell_source("class WorkflowState")).body
        if isinstance(node, ast.ClassDef) and node.name == "WorkflowState"
    )
    state_fields = {
        node.target.id
        for node in workflow_state.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert {"story_genre", "story_setting", "story_theme"} <= state_fields

    initial_state = _load_function(
        _method_source(_cell_source("class AdventureUI"), "_initial_state"),
        "_initial_state",
        {},
    )

    state = initial_state(
        None,
        {
            "user_name": "Alex",
            "user_age": "30",
            "user_pronouns": "she/her",
            "story_genre": "mystery",
            "story_setting": "a lunar archive",
            "story_theme": "trust",
        },
    )

    assert state["story_genre"] == "mystery"
    assert state["story_setting"] == "a lunar archive"
    assert state["story_theme"] == "trust"


def test_choice_application_owns_turn_increment_and_max_turn_end() -> None:
    source = _cell_source("def apply_choice_node")
    advance_turn = _load_function(source, "_advance_turn_after_choice", {})

    assert advance_turn(0, 3) == {
        "turn_index": 1,
        "run_status": "running",
        "end_reason": None,
    }
    assert advance_turn(2, 3) == {
        "turn_index": 3,
        "run_status": "ended",
        "end_reason": "Reached max_turns",
    }

    apply_choice = _definition(source, "apply_choice_node")
    called_helpers = {
        call.func.id
        for call in ast.walk(apply_choice)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }
    assert "_advance_turn_after_choice" in called_helpers
