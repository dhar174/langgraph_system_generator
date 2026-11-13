"""Integrity checks for the fixed v1 reviewer study inputs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import nbformat

from langgraph_system_generator.generator.agents.requirements_reviewer import (
    REVIEW_INSTRUCTIONS,
)
from langgraph_system_generator.qa.outcomes import notebook_candidate_id
from langgraph_system_generator.qa.specialist_models import (
    MAX_INPUT_CHARS,
    review_response_format,
)
from langgraph_system_generator.qa.specialist_review import build_review_context
from langgraph_system_generator.utils.config import GenerationConfig
from scripts.evaluate_semantic_review import build_typed_state

ROOT = Path(__file__).resolve().parents[1] / "evaluation/semantic_quality_v1"


def _load(filename: str):
    return json.loads((ROOT / filename).read_text(encoding="utf-8"))


def _hash(filename: str) -> str:
    return hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()


def test_quality_corpus_frozen_assets_match_manifest():
    manifest = _load("fixture_manifest.json")
    assert manifest["dataset_sha256"] == _hash("cases.json")
    assert manifest["labels_sha256"] == _hash("reference_labels.json")
    assert manifest["annotations_sha256"] == _hash("annotations.json")
    assert manifest["fixture_recipe_sha256"] == _hash("build_fixtures.py")
    assert (
        manifest["reviewer_prompt_sha256"]
        == hashlib.sha256(REVIEW_INSTRUCTIONS.encode("utf-8")).hexdigest()
    )
    schema = json.dumps(
        review_response_format(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert manifest["response_schema_sha256"] == hashlib.sha256(schema).hexdigest()
    for snapshot in manifest["snapshots"]:
        assert snapshot["bytes_sha256"] == _hash(snapshot["path"])


def test_quality_corpus_preserves_pair_and_context_integrity():
    cases = _load("cases.json")["cases"]
    labels = {row["case_id"]: row for row in _load("reference_labels.json")["cases"]}
    snapshots = {
        row["path"]: row["bytes_sha256"]
        for row in _load("fixture_manifest.json")["snapshots"]
    }
    assert len(cases) == len(labels) == 20
    assert {case["case_id"] for case in cases} == set(labels)
    assert Counter(case["split"] for case in cases) == {
        "development": 8,
        "holdout": 8,
        "guardrail": 4,
    }
    pairs = defaultdict(list)
    context_sizes = []
    config = GenerationConfig(model="gpt-6-luna")
    for case in cases:
        candidate = case["candidate"]
        state = build_typed_state(candidate["model_state"], config)
        context = build_review_context(state, instructions=REVIEW_INSTRUCTIONS)
        provenance = candidate["provenance"]
        assert snapshots[candidate["candidate_ref"]] == (
            provenance["altered_bytes_sha256"] or provenance["original_bytes_sha256"]
        )
        notebook = nbformat.read(ROOT / candidate["candidate_ref"], as_version=4)
        assert notebook_candidate_id(notebook) == provenance["candidate_identity"]
        assert context.candidate_id == provenance["candidate_identity"]
        assert context.context_digest == provenance["context_digest"]
        assert state["qa_reports"]
        assert case["case_id"] not in context.request_json
        for defect in labels[case["case_id"]]["defects"]:
            assert defect["defect_id"] not in context.request_json
            assert defect["rationale"] not in context.request_json
        if case["pair_id"]:
            assert len(context.request_json) <= MAX_INPUT_CHARS
            pairs[case["pair_id"]].append((case, context))
        else:
            context_sizes.append(len(context.request_json))
    assert len(pairs) == 8
    for pair in pairs.values():
        assert len(pair) == 2
        (left, left_context), (right, right_context) = pair
        assert left["split"] == right["split"]
        assert left["domain"] == right["domain"]
        assert left_context.candidate_id != right_context.candidate_id
        assert sorted(len(labels[row["case_id"]]["defects"]) for row, _ in pair) == [
            0,
            1,
        ]
    assert sum(size > MAX_INPUT_CHARS for size in context_sizes) == 1
    assert sum(46_000 <= size <= MAX_INPUT_CHARS for size in context_sizes) == 1


def test_corrected_snapshot_routes_match_workflow_schema_and_executable_graph():
    cases = {case["case_id"]: case for case in _load("cases.json")["cases"]}
    for case_id, label, destination in (
        ("c-8r4q", "billing", "technical"),
        ("c-3q6z", "instructor_review", "award_credit"),
    ):
        candidate = cases[case_id]["candidate"]
        state = candidate["model_state"]
        content = state["generated_cells"][2]["content"]
        schema = json.loads(
            content.split("### Workflow Schema\n\n```json\n", 1)[1].split("\n```", 1)[0]
        )
        rendered = schema["conditional_edges"]
        canonical = state["graph_exports"]["schema"]["conditional_edges"]
        assert rendered == canonical
        assert any(edge["branches"].get(label) == destination for edge in rendered)
        notebook = _load(candidate["candidate_ref"])
        assert content in [
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "markdown"
        ]
        assert any(
            f'"{label}": "{destination}"' in cell["content"]
            for cell in state["generated_cells"]
            if cell["cell_type"] == "code"
        )
