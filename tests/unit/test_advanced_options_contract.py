"""Contract regression tests for supported vs. roadmap advanced options."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from langgraph_system_generator.api.server import app
from langgraph_system_generator.cli import generate_artifacts

SUPPORTED_ADVANCED_FIELDS = {
    "model",
    "temperature",
    "max_tokens",
    "agent_type",
    "custom_endpoint",
}

REMOVED_ADVANCED_FIELDS = {
    "preset",
    "memory_config",
    "graph_style",
    "retriever_type",
    "document_loader",
}


def test_generation_request_openapi_exposes_only_supported_advanced_fields():
    properties = app.openapi()["components"]["schemas"]["GenerationRequest"]["properties"]

    for field_name in SUPPORTED_ADVANCED_FIELDS:
        assert field_name in properties

    for field_name in REMOVED_ADVANCED_FIELDS:
        assert field_name not in properties


def test_generate_artifacts_signature_excludes_removed_advanced_kwargs():
    parameters = inspect.signature(generate_artifacts).parameters

    for field_name in SUPPORTED_ADVANCED_FIELDS:
        assert field_name in parameters

    for field_name in REMOVED_ADVANCED_FIELDS:
        assert field_name not in parameters


def test_generate_artifacts_rejects_removed_advanced_kwargs():
    signature = inspect.signature(generate_artifacts)

    with pytest.raises(TypeError):
        signature.bind(
            "prompt",
            output_dir="output/test",
            mode="stub",
            memory_config="short",
        )


def test_generation_request_docs_snapshots_omit_removed_fields():
    repo_root = Path(__file__).resolve().parent.parent.parent
    class_block_pattern = re.compile(
        r"class GenerationRequest \{(?P<body>.*?)^\s*\}",
        re.MULTILINE | re.DOTALL,
    )
    dot_block_pattern = re.compile(
        r'GenerationRequest".*?label=<\{GenerationRequest\|(?P<body>.*?)\|}>',
        re.DOTALL,
    )

    text_snapshot_paths = [
        repo_root / "README.md",
        repo_root / "classes.mmd",
        repo_root / "classes.html",
    ]
    for path in text_snapshot_paths:
        match = class_block_pattern.search(path.read_text(encoding="utf-8"))
        assert match is not None, f"Could not find GenerationRequest block in {path.name}"
        body = match.group("body")

        for field_name in SUPPORTED_ADVANCED_FIELDS:
            assert field_name in body
        for field_name in REMOVED_ADVANCED_FIELDS:
            assert field_name not in body

    dot_path = repo_root / "classes.dot"
    dot_match = dot_block_pattern.search(dot_path.read_text(encoding="utf-8"))
    assert dot_match is not None, "Could not find GenerationRequest block in classes.dot"
    dot_body = dot_match.group("body")

    for field_name in SUPPORTED_ADVANCED_FIELDS:
        assert field_name in dot_body
    for field_name in REMOVED_ADVANCED_FIELDS:
        assert field_name not in dot_body
