import importlib
import sys


def test_output_base_not_created_on_import(monkeypatch, tmp_path):
    module_name = "langgraph_system_generator.constants"
    base = tmp_path / "lnf_output"

    monkeypatch.setenv("LNF_OUTPUT_BASE", str(base))
    monkeypatch.setenv("HOME", str(tmp_path))  # keep expansion within tmp
    sys.modules.pop(module_name, None)  # force fresh import with patched env

    constants = importlib.import_module(module_name)

    try:
        assert constants.OUTPUT_BASE == base.resolve()
        assert not base.exists()
        assert constants.is_relative_to_base((base / "child").resolve(), constants.OUTPUT_BASE)
        assert not constants.is_relative_to_base((tmp_path / "other").resolve(), constants.OUTPUT_BASE)
    finally:
        sys.modules.pop(module_name, None)  # clean up for later imports


def test_output_base_default(monkeypatch):
    module_name = "langgraph_system_generator.constants"
    monkeypatch.delenv("LNF_OUTPUT_BASE", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    sys.modules.pop(module_name, None)

    constants = importlib.import_module(module_name)
    try:
        assert constants.OUTPUT_BASE == constants.DEFAULT_OUTPUT_BASE.resolve()
        assert not constants.OUTPUT_BASE.exists()
    finally:
        sys.modules.pop(module_name, None)


def test_expanduser(monkeypatch, tmp_path):
    module_name = "langgraph_system_generator.constants"
    home_override = tmp_path / "home"
    home_override.mkdir()
    monkeypatch.setenv("HOME", str(home_override))
    tilde_path = "~/custom_output"
    monkeypatch.setenv("LNF_OUTPUT_BASE", tilde_path)
    sys.modules.pop(module_name, None)

    constants = importlib.import_module(module_name)
    try:
        expected = (home_override / "custom_output").resolve()
        assert constants.OUTPUT_BASE == expected
        assert not expected.exists()
    finally:
        sys.modules.pop(module_name, None)
