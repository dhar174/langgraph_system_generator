from langchain_core.messages import AIMessage

from langgraph_system_generator.generator.utils import get_message_text
from langgraph_system_generator.patterns.utils import build_llm_init
from langgraph_system_generator.utils.model_compatibility import (
    DEFAULT_MODEL,
    LUNA_MODEL,
    chat_openai_compatibility_kwargs,
)


def test_default_model_is_luna():
    assert DEFAULT_MODEL == LUNA_MODEL == "gpt-6-luna"


def test_luna_uses_responses_api_only_on_official_endpoint():
    expected = {
        "use_responses_api": True,
        "reasoning": {"effort": "low"},
        "output_version": "responses/v1",
    }
    assert chat_openai_compatibility_kwargs(LUNA_MODEL) == expected
    assert (
        chat_openai_compatibility_kwargs(
            LUNA_MODEL, api_base="https://api.openai.com/v1"
        )
        == expected
    )
    assert (
        chat_openai_compatibility_kwargs(
            LUNA_MODEL, api_base="https://api.openai.com/v1/"
        )
        == expected
    )
    assert chat_openai_compatibility_kwargs("gpt-5-mini") == {}
    assert (
        chat_openai_compatibility_kwargs(
            LUNA_MODEL, api_base="http://localhost:1234/v1"
        )
        == {}
    )


def test_pattern_emitters_omit_temperature_for_official_luna():
    direct = build_llm_init(LUNA_MODEL, 0.7)
    assert "temperature" not in direct
    assert "use_responses_api=True" in direct
    assert "reasoning={'effort': 'low'}" in direct
    assert "output_version='responses/v1'" in direct

    notebook = build_llm_init(LUNA_MODEL, 0.7, use_notebook_helper=True)
    assert notebook == "make_llm()"
    custom = build_llm_init(
        LUNA_MODEL, 0.7, api_base="http://localhost:1234/v1"
    )
    assert "temperature=0.7" in custom
    assert "use_responses_api" not in custom


def test_message_text_ignores_nontext_responses_blocks():
    message = AIMessage(
        content=[
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "private"}]},
            {"type": "text", "text": "review JSON"},
            {"type": "refusal", "refusal": "private refusal"},
        ]
    )
    assert get_message_text(message) == "review JSON"
    assert get_message_text("plain response") == "plain response"
    assert get_message_text(object()) == ""
