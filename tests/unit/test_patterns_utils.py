"""Tests for pattern utility helpers."""

from __future__ import annotations

from langgraph_system_generator.patterns.utils import build_llm_init


def test_build_llm_init_excludes_optional_params_when_missing():
    """Ensure optional parameters are omitted when not provided."""
    result = build_llm_init("gpt-5-mini", 0.3)

    assert "base_url" not in result
    assert "max_tokens" not in result
    assert result == "make_llm(temperature=0.3)"


def test_build_llm_init_includes_base_url_only_when_passed():
    """API base stays centralized in make_llm rather than per-node calls."""
    result = build_llm_init("gpt-5-mini", 0.3, api_base="https://example.com")

    assert "base_url" not in result
    assert "max_tokens" not in result
    assert result == "make_llm(temperature=0.3)"


def test_build_llm_init_includes_max_tokens_only_when_passed():
    """Ensure max_tokens appears only when provided."""
    result = build_llm_init("gpt-5-mini", 0.3, max_tokens=1200)

    assert "base_url" not in result
    assert "max_tokens=1200" in result


def test_build_llm_init_handles_special_chars_in_params():
    """Model names stay centralized in the generated config cell."""
    model_with_quote = 'model-with"quote'
    result = build_llm_init(model_with_quote, 0.3)
    assert "model=" not in result
    assert result == "make_llm(temperature=0.3)"
