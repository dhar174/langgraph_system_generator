"""Tests for safe, independently annotated semantic-review score reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.semantic_review_scoring import (
    ScoringError,
    reviewer_disabled_baseline,
    score_files,
    score_receipt,
    sha256_json,
)


def _fixtures(evidence_kind: str = "synthetic-contract"):
    dataset = {
        "schema_version": 1,
        "dataset_id": "semantic_quality_v1",
        "cases": [
            {"case_id": "clean-a", "prompt": "Do the safe task.", "docs": []},
            {"case_id": "defect-a", "prompt": "Meet this requirement.", "docs": []},
            {"case_id": "guard-a", "prompt": "Use supplied docs.", "docs": []},
        ],
    }
    labels = {
        "schema_version": 1,
        "dataset_id": "semantic_quality_v1",
        "label_origin": "AI-generated provisional; pending independent review",
        "cases": [
            {
                "case_id": "clean-a",
                "pair_id": "pair-clean-a",
                "split": "development",
                "domain": "support",
                "eligibility": "eligible",
                "expectation": {
                    "kind": "clean",
                    "categories": [],
                    "docs_available": False,
                },
                "defects": [],
            },
            {
                "case_id": "defect-a",
                "pair_id": "pair-defect-a",
                "split": "holdout",
                "domain": "logistics",
                "eligibility": "eligible",
                "expectation": {"kind": "defect", "categories": ["requirements_gap"]},
                "defects": [
                    {
                        "defect_id": "defect-a-required-handling",
                        "requirement": "Retain handling condition Z.",
                        "source_locations": [
                            {
                                "source_family": "requirement",
                                "source_id": "request:prompt",
                            }
                        ],
                        "expected_categories": ["requirements_gap"],
                        "rationale": "The candidate omits the requested condition.",
                        "ambiguity_policy": "Only report if the omission changes behavior.",
                        "baseline_detected": False,
                    }
                ],
            },
            {
                "case_id": "guard-a",
                "pair_id": None,
                "split": "development",
                "domain": "research",
                "eligibility": "guardrail",
                "expectation": {
                    "kind": "guardrail",
                    "categories": [],
                    "docs_available": False,
                    "missing_docs_expectation": "abstain",
                    "expected_status": "insufficient_context",
                },
                "defects": [],
            },
        ],
    }
    clean_findings = [
        {
            "finding_id": "finding-clean-fp",
            "category": "domain_mismatch",
            "message": "Synthetic safe finding for a clean fixture.",
            "references": [],
        }
    ]
    defect_findings = [
        {
            "finding_id": "finding-defect-1",
            "category": "requirements_gap",
            "message": "Synthetic safe finding about the omitted condition.",
            "references": [],
        },
        {
            "finding_id": "finding-defect-2",
            "category": "requirements_gap",
            "message": "Synthetic duplicate concern about the same omission.",
            "references": [],
        },
    ]
    receipt = {
        "schema_version": "semantic-review-receipt-v1",
        "run_id": "run-test",
        "evidence_kind": evidence_kind,
        "plan_sha256": "a" * 64,
        "dataset": {"id": "semantic_quality_v1", "sha256": sha256_json(dataset)},
        "labels_sha256": sha256_json(labels),
        "sources": {
            "source_revision": "b" * 40,
            "source_sha256": "b" * 64,
            "reviewer_prompt_sha256": "c" * 64,
        },
        "effective_config": {
            "model": "fixture-model",
            "temperature": 0.0,
            "response_api": "chat_completions",
            "reasoning_profile": None,
            "output_version": None,
            "requested_endpoint_policy": "fixture-policy",
            "effective_endpoint_policy": "fixture-policy",
            "provider_id": "fixture-provider",
            "endpoint_sha256": "9" * 64,
            "requested_output_cap": 2048,
            "effective_output_cap": 2048,
            "input_limit_chars": 48000,
            "timeout_seconds": 30.0,
            "max_retries": 0,
            "concurrency": 1,
            "repetitions": 2,
        },
        "selected_cases": [
            {"case_id": "clean-a", "repetition": 1},
            {"case_id": "clean-a", "repetition": 2},
            {"case_id": "defect-a", "repetition": 1},
            {"case_id": "defect-a", "repetition": 2},
            {"case_id": "guard-a", "repetition": 1},
            {"case_id": "guard-a", "repetition": 2},
        ],
        "attempts_reserved": 5,
        "records": [
            {
                "case_id": "clean-a",
                "repetition": 1,
                "split": "development",
                "domain": "support",
                "case_status": "reviewed",
                "reason_code": "complete",
                "model_invocations": 1,
                "candidate_sha256": "d" * 64,
                "context_sha256": "e" * 64,
                "latency_ms": 11,
                "requested_model": "fixture-model",
                "reported_model": "semantic-review-synthetic-contract",
                "provenance": evidence_kind,
                "baseline": {"eligible": True, "blocking_rules": []},
                "safe_findings": clean_findings,
                "annotation_refs": [],
            },
            {
                "case_id": "clean-a",
                "repetition": 2,
                "split": "development",
                "domain": "support",
                "case_status": "reviewed",
                "reason_code": "complete",
                "model_invocations": 1,
                "candidate_sha256": "d" * 64,
                "context_sha256": "e" * 64,
                "latency_ms": 13,
                "requested_model": "fixture-model",
                "reported_model": "semantic-review-synthetic-contract",
                "provenance": evidence_kind,
                "baseline": {"eligible": True, "blocking_rules": []},
                "safe_findings": [],
                "annotation_refs": [],
            },
            {
                "case_id": "defect-a",
                "repetition": 1,
                "split": "holdout",
                "domain": "logistics",
                "case_status": "reviewed",
                "reason_code": "complete",
                "model_invocations": 1,
                "candidate_sha256": "f" * 64,
                "context_sha256": "1" * 64,
                "latency_ms": 21,
                "requested_model": "fixture-model",
                "reported_model": "semantic-review-synthetic-contract",
                "provenance": evidence_kind,
                "baseline": {"eligible": True, "blocking_rules": []},
                "safe_findings": defect_findings,
                "annotation_refs": [],
            },
            {
                "case_id": "defect-a",
                "repetition": 2,
                "split": "holdout",
                "domain": "logistics",
                "case_status": "invalid_response",
                "reason_code": "invalid_response",
                "model_invocations": 1,
                "candidate_sha256": "f" * 64,
                "context_sha256": "1" * 64,
                "latency_ms": 18,
                "requested_model": "fixture-model",
                "reported_model": "semantic-review-synthetic-contract",
                "provenance": evidence_kind,
                "baseline": {"eligible": True, "blocking_rules": []},
                "safe_findings": [],
                "annotation_refs": [],
            },
            {
                "case_id": "guard-a",
                "repetition": 1,
                "split": "development",
                "domain": "research",
                "case_status": "input_limit",
                "reason_code": "input_limit",
                "model_invocations": 0,
                "candidate_sha256": "2" * 64,
                "context_sha256": "3" * 64,
                "latency_ms": None,
                "requested_model": "fixture-model",
                "reported_model": None,
                "provenance": evidence_kind,
                "baseline": {"eligible": True, "blocking_rules": []},
                "safe_findings": [],
                "annotation_refs": [],
            },
            {
                "case_id": "guard-a",
                "repetition": 2,
                "split": "development",
                "domain": "research",
                "case_status": "insufficient_context",
                "reason_code": "insufficient_context",
                "model_invocations": 1,
                "candidate_sha256": "2" * 64,
                "context_sha256": "3" * 64,
                "latency_ms": 25,
                "requested_model": "fixture-model",
                "reported_model": "semantic-review-synthetic-contract",
                "provenance": evidence_kind,
                "baseline": {"eligible": True, "blocking_rules": []},
                "safe_findings": [],
                "annotation_refs": [],
            },
        ],
    }
    for record in receipt["records"]:
        record["evidence_kind"] = evidence_kind
        if evidence_kind == "live" and record["reported_model"] is not None:
            record["reported_model"] = "configured-provider-model"
        record["provenance"] = {"candidate_origin": "repository-fixture"}
        record["context_chars"] = 512
        record["docs_available"] = False
        record["attempt_reserved"] = record["model_invocations"] == 1
        record["provider_dispatch_uncertain"] = False
        record["http_request_count"] = record["model_invocations"] or 0
    annotations = {
        "schema_version": 1,
        "annotation_version": "adjudication-v1",
        "dataset_sha256": sha256_json(dataset),
        "labels_sha256": sha256_json(labels),
        "annotations": [
            {
                "annotation_id": "ann-clean-fp",
                "case_id": "clean-a",
                "repetition": 1,
                "finding_id": "finding-clean-fp",
                "matched_defect_id": None,
                "verdict": "unsupported",
                "rationale": "This reviewed clean candidate satisfies its requirement.",
                "reviewer_identity": "reviewer-1",
                "reviewer_type": "independent_human",
                "annotation_version": "adjudication-v1",
            },
            {
                "annotation_id": "ann-defect-1",
                "case_id": "defect-a",
                "repetition": 1,
                "finding_id": "finding-defect-1",
                "matched_defect_id": "defect-a-required-handling",
                "verdict": "supported",
                "rationale": "The concern matches the independently identified omission.",
                "reviewer_identity": "reviewer-1",
                "reviewer_type": "independent_human",
                "annotation_version": "adjudication-v1",
            },
            {
                "annotation_id": "ann-defect-2",
                "case_id": "defect-a",
                "repetition": 1,
                "finding_id": "finding-defect-2",
                "matched_defect_id": "defect-a-required-handling",
                "verdict": "supported",
                "rationale": "This repeats the same omission.",
                "reviewer_identity": "reviewer-1",
                "reviewer_type": "independent_human",
                "annotation_version": "adjudication-v1",
            },
        ],
    }
    return dataset, labels, receipt, annotations


def _bind_hashes(dataset, labels, receipt, annotations=None):
    receipt["dataset"]["sha256"] = sha256_json(dataset)
    receipt["labels_sha256"] = sha256_json(labels)
    if annotations is not None:
        annotations["dataset_sha256"] = sha256_json(dataset)
        annotations["labels_sha256"] = sha256_json(labels)


def test_scoring_is_one_to_one_and_adjudication_gated():
    dataset, labels, receipt, annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt, annotations)

    report = score_receipt(receipt, dataset, labels, annotations)

    assert report["evidence_kind"] == "synthetic-contract"
    assert report["accuracy_claim_allowed"] is False
    assert report["valid_review_coverage"]["reviewed_eligible_quality_trials"] == 3
    assert report["valid_review_coverage"]["eligible_quality_trial_denominator"] == 4
    assert report["clean_case_false_positive_rate"]["value"] == 0.5
    assert report["defect_detection_recall"]["confirmed_one_to_one_defect_hits"] == 1
    assert report["defect_detection_recall"]["eligible_defect_trial_denominator"] == 2
    assert (
        report["defect_detection_recall"][
            "undetected_including_abstentions_and_invalid_reviews"
        ]
        == 1
    )
    assert report["finding_precision"]["value"] == pytest.approx(2 / 3)
    assert report["finding_adjudication"]["duplicates_after_one_to_one_matching"] == 1
    assert report["additional_confirmed_concerns_beyond_deterministic_baseline"][
        "additional_reference_defect_ids"
    ] == [{"case_id": "defect-a", "defect_id": "defect-a-required-handling"}]
    assert report["latency"]["overall"]["sample_count"] == 5
    assert report["status_counts"]["input_limit"] == 1
    assert report["status_counts"]["invalid_response"] == 1
    assert report["status_counts"]["insufficient_context"] == 1
    assert report["guardrail_expectation_agreement"]["matching_trials"] == 1
    assert report["guardrail_expectation_agreement"]["expected_trial_denominator"] == 2
    assert report["review_outcomes"]["reviewed_no_findings"] == 1
    assert report["review_outcomes"]["reviewed_with_findings"] == 2
    assert report["missing_docs_behavior"]["records_with_docs_unavailable"] == 6
    assert report["missing_docs_behavior"]["explicit_expectation_compliance"] == 0.5
    assert report["finding_adjudication"]["category_overlap_is_candidate_only"] is True


def test_pending_and_disagreement_are_preserved_not_scored_as_precision():
    dataset, labels, receipt, annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt, annotations)
    annotations["annotations"].append(
        {
            "annotation_id": "ann-disagree",
            "case_id": "defect-a",
            "repetition": 1,
            "finding_id": "finding-defect-1",
            "matched_defect_id": None,
            "verdict": "unsupported",
            "rationale": "A second reviewer disagrees.",
            "reviewer_identity": "reviewer-2",
            "reviewer_type": "independent_human",
            "annotation_version": "adjudication-v1",
        }
    )
    annotations["annotations"].append(
        {
            "annotation_id": "ann-explicit-pending",
            "case_id": "clean-a",
            "repetition": 1,
            "finding_id": "finding-clean-pending",
            "matched_defect_id": None,
            "verdict": "pending",
            "rationale": "Awaiting adjudication.",
            "reviewer_identity": "reviewer-3",
            "reviewer_type": "independent_human",
            "annotation_version": "adjudication-v1",
        }
    )
    receipt["records"][0]["safe_findings"].append(
        {
            "finding_id": "finding-clean-pending",
            "category": "requirements_gap",
            "message": "A pending synthetic opinion.",
            "references": [],
        }
    )

    report = score_receipt(receipt, dataset, labels, annotations)

    assert report["finding_precision"]["value"] == pytest.approx(1 / 2)
    assert report["finding_precision"]["unresolved_by_status"]["disagreement"] == 1
    assert report["finding_precision"]["unresolved_by_status"]["pending"] == 1
    assert report["finding_precision"]["pending_or_ambiguous_findings"] == 2
    assert report["clean_case_false_positive_rate"]["value"] == 0.0
    assert report["clean_case_false_positive_rate"]["unresolved_clean_trials"] == 1
    assert (
        report["clean_case_false_positive_rate"][
            "confirmed_false_positive_lower_bound_trials"
        ]
        == 1
    )
    assert (
        report["clean_case_false_positive_rate"][
            "confirmed_lower_bound_over_reviewed_clean_trials"
        ]
        == 0.5
    )
    assert (
        report["clean_case_false_positive_rate"][
            "confirmed_lower_bound_over_eligible_clean_trials"
        ]
        == 0.5
    )


def test_human_adjudication_can_resolve_preserved_conflicting_votes():
    dataset, labels, receipt, annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt, annotations)
    annotations["annotations"].extend(
        [
            {
                "annotation_id": "ann-defect-disagree",
                "case_id": "defect-a",
                "repetition": 1,
                "finding_id": "finding-defect-1",
                "matched_defect_id": None,
                "verdict": "unsupported",
                "rationale": "An independent reviewer disagreed.",
                "reviewer_identity": "reviewer-2",
                "reviewer_type": "independent_human",
                "annotation_version": "adjudication-v1",
            },
            {
                "annotation_id": "ann-defect-resolution",
                "case_id": "defect-a",
                "repetition": 1,
                "finding_id": "finding-defect-1",
                "matched_defect_id": "defect-a-required-handling",
                "verdict": "supported",
                "resolution": True,
                "resolves_annotation_ids": ["ann-defect-1", "ann-defect-disagree"],
                "rationale": "The adjudicator reviewed both votes and resolved the finding.",
                "reviewer_identity": "adjudicator-1",
                "reviewer_type": "human_adjudicator",
                "annotation_version": "adjudication-v1",
            },
        ]
    )

    report = score_receipt(receipt, dataset, labels, annotations)

    adjudications = report["records"][2]["finding_adjudications"]
    assert adjudications[0]["adjudication_status"] == "resolved_after_disagreement"
    assert "disagreement" not in report["finding_precision"]["unresolved_by_status"]
    assert report["finding_precision"]["value"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("case_id, index", [("defect-a", 2), ("clean-a", 0)])
def test_additional_concern_ids_can_be_adjudicated_without_changing_reference_recall(
    case_id, index
):
    dataset, labels, receipt, annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt, annotations)
    extra_id = "additional:extra-opaque-1"
    annotations["additional_concerns"] = [
        {
            "case_id": case_id,
            "defect_id": extra_id,
            "requirement": "Preserve the separate hand-off notification.",
            "source_locations": [{"source_family": "cell", "source_id": "cell:2"}],
            "expected_categories": ["unsupported_capability_claim"],
            "rationale": "The model report identifies a distinct claim unsupported by execution.",
            "ambiguity_policy": "Count only if the claim is not implemented by another path.",
            "baseline_detected": False,
        }
    ]
    receipt["records"][index]["safe_findings"].append(
        {
            "finding_id": "finding-additional-1",
            "category": "unsupported_capability_claim",
            "message": "This message is retained in the receipt, not the score summary.",
            "references": [],
        }
    )
    annotations["annotations"].append(
        {
            "annotation_id": "ann-additional-1",
            "case_id": case_id,
            "repetition": 1,
            "finding_id": "finding-additional-1",
            "matched_defect_id": extra_id,
            "verdict": "supported",
            "rationale": "This is a separate independently confirmed concern.",
            "reviewer_identity": "reviewer-1",
            "reviewer_type": "human_maintainer",
            "annotation_version": "adjudication-v1",
        }
    )

    report = score_receipt(receipt, dataset, labels, annotations)
    report_text = json.dumps(report)

    assert report["defect_detection_recall"]["eligible_defect_trial_denominator"] == 2
    assert report["additional_confirmed_concerns_beyond_deterministic_baseline"][
        "additional_concern_ids"
    ] == [{"case_id": case_id, "defect_id": extra_id}]
    if case_id == "clean-a":
        clean = report["clean_case_false_positive_rate"]
        assert clean["value"] == 0.5
        assert clean["excluded_clean_trials_with_confirmed_concerns"] == 0
    assert "This message is retained" not in report_text
    assert "separate independently confirmed concern" not in report_text
    assert "rationale" not in report_text


def test_category_overlap_alone_never_confirms_detection():
    dataset, labels, receipt, _annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt, None)
    report = score_receipt(receipt, dataset, labels)

    assert report["defect_detection_recall"]["confirmed_one_to_one_defect_hits"] == 0
    assert report["finding_precision"]["value"] is None
    assert report["finding_precision"]["pending_or_ambiguous_findings"] == 3


def test_repeated_identical_finding_ids_are_scored_as_duplicates_not_rejected():
    dataset, labels, receipt, annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt, annotations)
    duplicate = dict(receipt["records"][2]["safe_findings"][0])
    receipt["records"][2]["safe_findings"].append(duplicate)

    report = score_receipt(receipt, dataset, labels, annotations)

    assert report["defect_detection_recall"]["confirmed_one_to_one_defect_hits"] == 1
    assert report["finding_adjudication"]["duplicates_after_one_to_one_matching"] == 2
    assert report["finding_adjudication"]["confirmed_duplicate_defect_findings"] == 2


def test_invalid_reference_and_uncertain_cancellation_are_recorded_separately():
    dataset, labels, receipt, _annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt)
    receipt["records"][3]["case_status"] = "invalid_reference"
    receipt["records"][3]["reason_code"] = "invalid_reference"
    report = score_receipt(receipt, dataset, labels)
    assert report["evidence_admission"]["invalid_reference_trials"] == 1
    assert report["evidence_admission"]["invoked_trial_denominator"] == 5
    assert report["evidence_admission"]["failure_rate"] == 0.2

    dataset, labels, receipt, _annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt)
    cancelled = receipt["records"][5]
    cancelled.update(
        {
            "case_status": "cancellation",
            "reason_code": "cancelled_request_outcome_uncertain",
            "model_invocations": None,
            "provider_dispatch_uncertain": True,
            "attempt_reserved": True,
            "http_request_count": 0,
            "safe_findings": [],
        }
    )
    report = score_receipt(receipt, dataset, labels)
    assert report["status_counts"]["cancellation"] == 1
    assert report["attempts_reserved"] == 5
    assert report["attempts_observed"]["model_invocations_uncertain"] == 1
    assert report["attempts_observed"]["http_requests_observed"] == 4


def test_clean_lower_bound_denominator_includes_unreviewed_clean_trials():
    dataset, labels, receipt, annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt, annotations)
    clean_unavailable = receipt["records"][1]
    clean_unavailable.update(
        {
            "case_status": "unavailable",
            "reason_code": "provider_unavailable",
            "safe_findings": [],
        }
    )

    report = score_receipt(receipt, dataset, labels, annotations)

    metric = report["clean_case_false_positive_rate"]
    assert metric["confirmed_false_positive_clean_trials"] == 1
    assert metric["resolved_reviewed_clean_trial_denominator"] == 1
    assert metric["unresolved_clean_trials"] == 1
    assert metric["value"] == 1.0
    assert metric["confirmed_lower_bound_over_eligible_clean_trials"] == 0.5


def test_empty_denominators_are_na_and_disabled_baseline_is_not_perfect():
    dataset, labels, receipt, _ = _fixtures()
    labels["cases"] = [labels["cases"][2]]
    dataset["cases"] = [dataset["cases"][2]]
    receipt["records"] = [receipt["records"][4]]
    receipt["selected_cases"] = [{"case_id": "guard-a", "repetition": 1}]
    receipt["attempts_reserved"] = 0
    _bind_hashes(dataset, labels, receipt)

    report = score_receipt(receipt, dataset, labels)
    baseline = reviewer_disabled_baseline()

    assert report["valid_review_coverage"]["value"] is None
    assert report["clean_case_false_positive_rate"]["value"] is None
    assert report["defect_detection_recall"]["value"] is None
    assert report["finding_precision"]["value"] is None
    assert baseline["reviewer_calls"] == 0
    assert baseline["semantic_findings"] == 0
    assert baseline["precision"] is None


def test_mixed_evidence_and_hash_mismatch_are_rejected():
    dataset, labels, receipt, _ = _fixtures()
    _bind_hashes(dataset, labels, receipt)
    receipt["records"][0]["evidence_kind"] = "live"
    with pytest.raises(ScoringError, match="mixes synthetic and live"):
        score_receipt(receipt, dataset, labels)

    receipt["records"][0]["evidence_kind"] = "synthetic-contract"
    labels["label_origin"] = "changed label file"
    with pytest.raises(ScoringError, match="label hash"):
        score_receipt(receipt, dataset, labels)


def test_live_evidence_has_a_distinct_label_and_annotations_binding():
    dataset, labels, receipt, annotations = _fixtures(evidence_kind="live")
    _bind_hashes(dataset, labels, receipt, annotations)
    for record in receipt["records"]:
        record["reported_model"] = "configured-provider-model"

    report = score_receipt(receipt, dataset, labels, annotations)

    assert report["evidence_kind"] == "live"
    assert (
        report["quality_statement"]
        == "descriptive_live_evidence_with_independent_annotations"
    )
    assert report["independent_adjudication_available"] is True
    assert report["accuracy_claim_allowed"] is False
    assert report["binding"]["annotation_sha256"] == sha256_json(annotations)


def test_score_files_checks_exact_frozen_inputs_and_optional_plan(tmp_path: Path):
    dataset, labels, receipt, annotations = _fixtures(evidence_kind="live")
    receipt["attempts_reserved"] = 4
    for record in receipt["records"]:
        if record["case_id"] == "guard-a":
            record["case_status"] = "invalid_reference"
            record["reason_code"] = "invalid_reference"
            record["model_invocations"] = 0
            record["attempt_reserved"] = False
            record["http_request_count"] = 0
    receipt_path = tmp_path / "receipt.json"
    dataset_path = tmp_path / "cases.json"
    labels_path = tmp_path / "labels.json"
    annotations_path = tmp_path / "annotations.json"
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "score.json"
    for path, value in ((dataset_path, dataset), (labels_path, labels)):
        path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    receipt["dataset"]["sha256"] = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    receipt["labels_sha256"] = hashlib.sha256(labels_path.read_bytes()).hexdigest()
    annotations["dataset_sha256"] = receipt["dataset"]["sha256"]
    annotations["labels_sha256"] = receipt["labels_sha256"]
    annotations_path.write_text(
        json.dumps(annotations, sort_keys=True), encoding="utf-8"
    )
    plan = {
        "schema_version": 1,
        "plan_kind": "semantic-review-live-pilot",
        "source_revision": receipt["sources"]["source_revision"],
        "source_sha256": receipt["sources"]["source_sha256"],
        "source_files_sha256": {},
        "reviewer_id": "requirements_domain_fidelity",
        "reviewer_prompt_sha256": receipt["sources"]["reviewer_prompt_sha256"],
        "dataset": {
            "id": "semantic_quality_v1",
            "path": "cases.json",
            "sha256": receipt["dataset"]["sha256"],
            "case_count": 3,
            "selected_case_ids": ["clean-a", "defect-a", "guard-a"],
        },
        "labels": {"path": "labels.json", "sha256": receipt["labels_sha256"]},
        "effective_config": dict(receipt["effective_config"]),
        "repetitions": 2,
        "attempt_policy": {
            "maximum_attempts": 40,
            "maximum_provider_attempts_for_selected_cases": 4,
            "one_at_a_time": True,
            "automatic_retries": False,
            "automatic_model_switches": False,
            "automatic_resume": False,
        },
        "selected_cases": [],
        "evidence_kind": "synthetic-contract-only-until-separately-authorized-live-run",
    }
    selected_case_ids = sorted({row["case_id"] for row in receipt["records"]})
    for case_id in selected_case_ids:
        record = next(row for row in receipt["records"] if row["case_id"] == case_id)
        eligible = case_id != "guard-a"
        plan["selected_cases"].append(
            {
                "case_id": case_id,
                "split": record["split"],
                "domain": record["domain"],
                "candidate_sha256": record["candidate_sha256"],
                "context_sha256": record["context_sha256"],
                "context_chars": record["context_chars"],
                "docs_available": record["docs_available"],
                "baseline": record["baseline"],
                "provenance": record["provenance"],
                "eligible": eligible,
                "preflight_status": None if eligible else "invalid_reference",
                "preflight_reason_code": None if eligible else "invalid_reference",
            }
        )
    receipt["plan_sha256"] = sha256_json(plan)
    plan["plan_sha256"] = receipt["plan_sha256"]
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")

    receipt_bytes = receipt_path.read_bytes()
    with pytest.raises(ScoringError, match="overwrite a frozen evidence input"):
        score_files(
            receipt_path,
            dataset_path,
            labels_path,
            output_path=receipt_path,
        )
    assert receipt_path.read_bytes() == receipt_bytes

    report = score_files(
        receipt_path,
        dataset_path,
        labels_path,
        annotations_path,
        output_path=output_path,
        plan_path=plan_path,
    )

    assert report["evidence_admission"]["preflight_invalid_reference_trials"] == 2
    assert report["evidence_admission"]["invalid_reference_trials"] == 0
    assert output_path.exists()
    markdown_path = output_path.with_suffix(".md")
    assert markdown_path.exists()
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert persisted["binding"]["receipt_sha256"] == report["binding"]["receipt_sha256"]
    assert "Semantic reviewer score report" in markdown
    assert "rationale" not in markdown
    assert "Synthetic safe finding" not in markdown
    changed_plan = dict(plan)
    changed_plan["effective_config"] = dict(plan["effective_config"])
    changed_plan["effective_config"]["model"] = "changed-model"
    changed_plan["plan_sha256"] = sha256_json(
        {key: value for key, value in changed_plan.items() if key != "plan_sha256"}
    )
    plan_path.write_text(json.dumps(changed_plan, sort_keys=True), encoding="utf-8")
    with pytest.raises(ScoringError, match="plan hash"):
        score_files(receipt_path, dataset_path, labels_path, plan_path=plan_path)

    bad_slot = next(item for item in plan["selected_cases"] if not item["eligible"])
    bad_slot["preflight_status"] = "input_limit"
    plan.pop("plan_sha256")
    receipt["plan_sha256"] = plan["plan_sha256"] = sha256_json(plan)
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    with pytest.raises(ScoringError, match="differs from the approved slot"):
        score_files(receipt_path, dataset_path, labels_path, plan_path=plan_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("http_request_count", 1),
        ("attempt_reserved", True),
        ("provider_dispatch_uncertain", True),
    ],
)
def test_preflight_reference_rejects_dispatch_evidence(field, value):
    dataset, labels, receipt, _ = _fixtures()
    _bind_hashes(dataset, labels, receipt)
    record = receipt["records"][4]
    assert record["model_invocations"] == 0
    record.update(case_status="invalid_reference", reason_code="invalid_reference")
    record[field] = value
    with pytest.raises(ScoringError, match="inconsistent dispatch metadata"):
        score_receipt(receipt, dataset, labels)


def test_live_receipt_rejects_reserved_synthetic_model_id():
    dataset, labels, receipt, _ = _fixtures(evidence_kind="live")
    _bind_hashes(dataset, labels, receipt)
    receipt["records"][0]["reported_model"] = "semantic-review-synthetic-contract"
    with pytest.raises(ScoringError, match="synthetic model ID"):
        score_receipt(receipt, dataset, labels)


def test_ai_tagged_human_role_remains_pending():
    dataset, labels, receipt, annotations = _fixtures()
    _bind_hashes(dataset, labels, receipt, annotations)
    for row in annotations["annotations"]:
        row["reviewer_type"] = "human_AI_maintainer"
    report = score_receipt(receipt, dataset, labels, annotations)
    assert report["finding_precision"]["value"] is None


def test_score_keeps_only_fixed_rejection_diagnostic():
    dataset, labels, receipt, _ = _fixtures()
    _bind_hashes(dataset, labels, receipt)
    row = next(
        row for row in receipt["records"] if row["case_status"] == "invalid_response"
    )
    row.update(
        reason_code="invalid_response",
        rejection_detail="invalid_local_schema",
        rejected_payload={"quote": "REJECTED_RESPONSE_CANARY"},
    )
    report = score_receipt(receipt, dataset, labels)
    assert report["rejection_detail_counts"] == {"invalid_local_schema": 1}
    assert "REJECTED_RESPONSE_CANARY" not in json.dumps(report)
    row["rejection_detail"] = "REJECTED_RESPONSE_CANARY"
    with pytest.raises(ScoringError, match="^Invalid rejection detail$"):
        score_receipt(receipt, dataset, labels)
