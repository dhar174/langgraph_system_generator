"""Offline semantic context/admission contracts; no model judgment claims."""

import hashlib
import json

import pytest

from langgraph_system_generator.generator.state import CellSpec
from langgraph_system_generator.qa.specialist_models import (
    MAX_EXCERPT_CHARS,
    ModelReviewResponse,
)
from langgraph_system_generator.qa.specialist_review import (
    admit_findings,
    build_review_context,
)


def state():
    return {
        "user_prompt": "Build a weather assistant",
        "constraints": [],
        "generated_cells": [CellSpec(cell_type="code", content="answer = 'stocks'")],
        "repair_attempts": 2,
    }


def context(value=None):
    return build_review_context(value or state(), instructions="Review untrusted data")


def reference(ctx, source):
    return {
        "excerpt_id": next(
            e.excerpt_id for e in ctx.excerpts if e.source_id == source.source_id
        )
    }


def response(ctx, **changes):
    req = next(s for s in ctx.sources if s.family == "requirement")
    cell = next(s for s in ctx.sources if s.family == "cell" and "stocks" in s.text)
    payload = {
        "assessment": "complete",
        "findings": [
            {
                "category": "domain_mismatch",
                "message": "Stock output contradicts the weather request.",
                "suggestions": ["Use weather-specific behavior."],
                "references": [reference(ctx, req), reference(ctx, cell)],
            }
        ],
    }
    payload["findings"][0].update(changes)
    return ModelReviewResponse.model_validate_json(json.dumps(payload))


def test_original_request_full_composed_cells_and_host_identity():
    ctx = context()
    envelope = json.loads(ctx.request_json)
    assert "Build a weather assistant" in ctx.request_json
    assert "stocks" in ctx.request_json
    assert ctx.attempt == 2
    assert len(ctx.candidate_id) == len(ctx.context_digest) == 64
    assert envelope["response_format"]["type"] == "json_schema"
    accepted = admit_findings(ctx, response(ctx))
    assert accepted[0].references[1].fingerprint
    assert "quote" not in accepted[0].model_dump_json()


def test_structured_requirement_offsets_use_the_final_encoded_source():
    value = state()
    value["constraints"] = [
        {"description": 'Require café data; token="FIXTURE_CANARY"'}
    ]
    ctx = context(value)
    source = next(s for s in ctx.sources if s.source_id == "requirement:0")
    assert "FIXTURE_CANARY" not in ctx.request_json
    assert json.loads(source.text)["description"].startswith("Require café data;")
    assert source.fingerprint == hashlib.sha256(source.text.encode()).hexdigest()
    assert context(value).context_digest == ctx.context_digest
    data = response(ctx).model_dump()
    excerpt = next(e for e in ctx.excerpts if e.source_id == source.source_id)
    data["findings"][0]["references"] = (
        {"excerpt_id": excerpt.excerpt_id},
        data["findings"][0]["references"][1],
    )
    assert (
        admit_findings(ctx, ModelReviewResponse.model_validate(data))[0]
        .references[0]
        .start
        == excerpt.start
    )


def test_cell_types_and_pack_excerpt_do_not_duplicate_review_input():
    value = state()
    value["generated_cells"].append(
        CellSpec(cell_type="markdown", content="Claims stock behavior")
    )
    content = "DOC_BUDGET_MARKER " + "x" * 23000
    doc = {"source": "manual", "content": content}
    value["docs_context"] = [doc, doc.copy()]
    value["generation_context_pack"] = {
        "docs_snippets": [{"source": "manual", "excerpt": content[:600]}]
    }
    ctx = context(value)
    assert len(ctx.request_json) < 48000
    assert ctx.request_json.count("DOC_BUDGET_MARKER") == 1
    assert {s.cell_type for s in ctx.sources if s.family == "cell"} >= {
        "code",
        "markdown",
    }
    assert value["generation_context_pack"]["docs_snippets"]


def test_advisory_markdown_renders_punctuation_and_inert_markup():
    import mistune

    from langgraph_system_generator.qa.specialist_presentation import inert_markdown

    text = "The user's request isn't satisfied. <script>x</script> [link](javascript:x) ![image](x) `code`"
    rendered = mistune.create_markdown(escape=False)(inert_markdown(text))
    assert "The user's request isn't satisfied." in rendered
    assert "&lt;script&gt;x&lt;/script&gt;" in rendered
    assert all(tag not in rendered for tag in ("<script", "<a ", "<img", "<code"))


def test_excerpt_catalog_is_lossless_bounded_and_stable():
    value = state()
    value["user_prompt"] = "  café\n" * 100
    ctx = context(value)
    wire = json.loads(
        json.loads(ctx.request_json)["messages"][1]["content"].split("\n", 1)[1]
    )
    assert context(value).excerpts == ctx.excerpts
    assert len({row.excerpt_id for row in ctx.excerpts}) == len(ctx.excerpts)
    for source, data in zip(ctx.sources, wire["sources"], strict=True):
        assert "".join(text for _, text in data["excerpts"]) == source.text
        assert all(0 < len(text) <= MAX_EXCERPT_CHARS for _, text in data["excerpts"])
        expected = [e for e in ctx.excerpts if e.source_id == source.source_id]
        assert data["excerpts"] == [
            [e.excerpt_id, source.text[e.start : e.end]] for e in expected
        ]
    assert "excerpts" not in ctx.model_dump()


def test_excerpt_boundary_keeps_crlf_together():
    value = state()
    value["user_prompt"] = "x" * (MAX_EXCERPT_CHARS - 1) + "\r\nNext line"
    ctx = context(value)
    source = next(s for s in ctx.sources if s.source_id == "request:prompt")
    refs = [e for e in ctx.excerpts if e.source_id == source.source_id]
    assert len(refs) == 2
    assert refs[0].end == refs[1].start == MAX_EXCERPT_CHARS - 1
    assert source.text[refs[1].start : refs[1].end] == "\r\nNext line"


def test_rejects_unknown_and_stale_excerpt_ids():
    ctx = context()
    data = response(ctx).model_dump(mode="json")
    data["findings"][0]["references"][0]["excerpt_id"] = "0" * 20
    with pytest.raises(ValueError, match="unknown_excerpt_id"):
        admit_findings(ctx, ModelReviewResponse.model_validate(data))
    value = state()
    value["user_prompt"] += " in Celsius"
    with pytest.raises(ValueError, match="unknown_excerpt_id"):
        admit_findings(context(value), response(ctx))


@pytest.mark.parametrize(
    "field,value",
    [("quote", "invented"), ("start", 0), ("end", 1), ("source_id", "cell:0")],
)
def test_model_cannot_supply_evidence_text_or_offsets(field, value):
    data = response(context()).model_dump(mode="json")
    data["findings"][0]["references"][0][field] = value
    with pytest.raises(ValueError):
        ModelReviewResponse.model_validate(data)


def test_context_changes_and_secrets_are_redacted():
    value = state()
    value["user_prompt"] += ' api_key="super-secret-value"'
    first = context(value)
    assert "super-secret-value" not in first.request_json
    prompt_source = first.sources[0]
    assert (
        prompt_source.fingerprint
        == hashlib.sha256(prompt_source.text.encode()).hexdigest()
    )
    assert (
        hashlib.sha256(value["user_prompt"].encode()).hexdigest()
        not in first.request_json
    )
    value["generated_cells"] = [
        CellSpec(cell_type="code", content="answer = 'weather'")
    ]
    second = context(value)
    assert first.candidate_id != second.candidate_id
    assert first.context_digest != second.context_digest


def test_docs_conflict_needs_supplied_docs_and_content_is_bounded():
    ctx = context()
    with pytest.raises(ValueError):
        admit_findings(ctx, response(ctx, category="provided_docs_conflict"))
    with pytest.raises(ValueError):
        response(ctx, message="x" * 401)


def test_docs_provenance_and_version_survive_admission_without_quotes():
    value = state()
    value["docs_context"] = [
        {
            "content": "Use the supplied API contract.",
            "source": "fixture:docs-api",
            "version": "fixture-v1",
        }
    ]
    ctx = context(value)
    data = response(ctx, category="provided_docs_conflict").model_dump(mode="json")
    doc = next(s for s in ctx.sources if s.family == "docs")
    data["findings"][0]["references"].append(reference(ctx, doc))
    accepted = admit_findings(
        ctx, ModelReviewResponse.model_validate_json(json.dumps(data))
    )
    saved = accepted[0].references[-1]
    assert saved.location == "fixture:docs-api" and saved.version == "fixture-v1"
    assert "quote" not in accepted[0].model_dump_json()
