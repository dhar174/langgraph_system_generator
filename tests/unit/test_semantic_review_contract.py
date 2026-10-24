"""Offline semantic context/admission contracts; no model judgment claims."""

import hashlib
import json

import pytest

from langgraph_system_generator.generator.state import CellSpec
from langgraph_system_generator.qa.specialist_models import ModelReviewResponse
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
                "references": [
                    {
                        "source_id": req.source_id,
                        "start": 0,
                        "end": 5,
                        "quote": req.text[:5],
                    },
                    {
                        "source_id": cell.source_id,
                        "start": 0,
                        "end": 6,
                        "quote": cell.text[:6],
                    },
                ],
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


@pytest.mark.parametrize("defect", ["source_id", "quote", "start", "end"])
def test_rejects_fabricated_or_invalid_references(defect):
    ctx = context()
    data = response(ctx).model_dump(mode="json")
    data["findings"][0]["references"][0][defect] = {
        "source_id": "invented",
        "quote": "fake",
        "start": 999,
        "end": 999,
    }[defect]
    with pytest.raises(ValueError):
        admit_findings(ctx, ModelReviewResponse.model_validate_json(json.dumps(data)))


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
    data["findings"][0]["references"].append(
        {"source_id": doc.source_id, "start": 0, "end": 3, "quote": "Use"}
    )
    accepted = admit_findings(
        ctx, ModelReviewResponse.model_validate_json(json.dumps(data))
    )
    saved = accepted[0].references[-1]
    assert saved.location == "fixture:docs-api" and saved.version == "fixture-v1"
    assert "quote" not in accepted[0].model_dump_json()
