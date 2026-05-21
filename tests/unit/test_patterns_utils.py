"""Tests for pattern utility helpers."""

from __future__ import annotations

from langgraph_system_generator.patterns.utils import build_llm_init


def test_build_llm_init_excludes_optional_params_when_missing():
    """Ensure the self-contained LLM init includes the base model."""
    result = build_llm_init("gpt-5-mini", 0.3)

    assert result == "ChatOpenAI(model='gpt-5-mini', temperature=0.3)"
    assert "base_url" not in result
    assert "max_tokens" not in result


def test_build_llm_init_includes_base_url_only_when_passed():
    """Standalone pattern output embeds the custom endpoint explicitly."""
    result = build_llm_init("gpt-5-mini", 0.3, api_base="https://example.com")

    assert result == (
        "ChatOpenAI(model='gpt-5-mini', temperature=0.3, "
        "base_url='https://example.com')"
    )
    assert "max_tokens" not in result


def test_build_llm_init_includes_max_tokens_only_when_passed():
    """Ensure max_tokens appears only when provided."""
    result = build_llm_init("gpt-5-mini", 0.3, max_tokens=1200)

    assert result == "ChatOpenAI(model='gpt-5-mini', temperature=0.3, max_tokens=1200)"
    assert "base_url" not in result


def test_build_llm_init_handles_special_chars_in_params():
    """Model names stay explicit in generated pattern snippets."""
    model_with_quote = 'model-with"quote'
    result = build_llm_init(model_with_quote, 0.3)
    assert result == 'ChatOpenAI(model=\'model-with"quote\', temperature=0.3)'


def test_build_llm_init_notebook_helper_uses_make_llm():
    """Notebook-composed output delegates model and endpoint config to make_llm."""
    result = build_llm_init(
        "gpt-5-mini",
        0.3,
        api_base="https://example.com",
        max_tokens=1200,
        use_notebook_helper=True,
    )

    assert result == "make_llm(temperature=0.3, max_tokens=1200)"
    assert "ChatOpenAI(" not in result
    assert "base_url" not in result
