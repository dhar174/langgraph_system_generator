"""Tests for safe path handling in the pipeline template skill script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_pipeline_template_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = (
        repo_root
        / ".github/skills/project-development/scripts/pipeline_template.py"
    )
    spec = importlib.util.spec_from_file_location("pipeline_template_skill", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pipeline_template_rejects_batch_path_traversal():
    module = _load_pipeline_template_module()

    with pytest.raises(ValueError, match="batch_id"):
        module.get_batch_dir("../escape")


def test_pipeline_template_rejects_item_path_traversal():
    module = _load_pipeline_template_module()

    with pytest.raises(ValueError, match="item_id"):
        module.get_item_dir("2025-01-15", "../escape")


def test_pipeline_template_allows_safe_identifiers():
    module = _load_pipeline_template_module()

    batch_dir = module.get_batch_dir("2025-01-15")
    item_dir = module.get_item_dir("2025-01-15", "item-0001")
    output_dir = module.get_output_dir("2025-01-15")

    assert batch_dir == module.DATA_DIR.resolve() / "2025-01-15"
    assert item_dir == module.DATA_DIR.resolve() / "2025-01-15" / "item-0001"
    assert output_dir == module.OUTPUT_DIR.resolve() / "2025-01-15"
