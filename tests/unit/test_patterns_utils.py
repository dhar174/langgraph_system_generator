"""Tests for pattern utility helpers."""

from __future__ import annotations

from langgraph_system_generator.patterns.utils import build_llm_init


def test_build_llm_init_excludes_optional_params_when_missing():
    """Ensure optional parameters are omitted when not provided."""
    result = build_llm_init("gpt-5-mini", 0.3)

    assert "base_url" not in result
    assert "max_tokens" not in result


def test_build_llm_init_includes_base_url_only_when_passed():
    """Ensure base_url appears only when provided."""
    result = build_llm_init("gpt-5-mini", 0.3, api_base="https://example.com")

    assert 'base_url="https://example.com"' in result
    assert "max_tokens" not in result


def test_build_llm_init_includes_max_tokens_only_when_passed():
    """Ensure max_tokens appears only when provided."""
    result = build_llm_init("gpt-5-mini", 0.3, max_tokens=1200)

    assert "base_url" not in result
    assert "max_tokens=1200" in result
