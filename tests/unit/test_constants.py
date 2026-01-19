import importlib
import sys


def test_output_base_not_created_on_import(monkeypatch, tmp_path):
    module_name = "langgraph_system_generator.constants"
    base = tmp_path / "lnf_output"

    monkeypatch.setenv("LNF_OUTPUT_BASE", str(base))
    sys.modules.pop(module_name, None)  # force fresh import with patched env

    constants = importlib.import_module(module_name)

    try:
        assert constants.OUTPUT_BASE == base.resolve()
        assert not base.exists()
        assert constants.is_relative_to_base(base / "child", constants.OUTPUT_BASE)
        assert not constants.is_relative_to_base(tmp_path / "other", constants.OUTPUT_BASE)
    finally:
        sys.modules.pop(module_name, None)  # clean up for later imports
