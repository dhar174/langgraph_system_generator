"""Descriptive scoring for the versioned semantic-review quality fixtures.

This module never calls a provider and never executes a candidate notebook.
Synthetic contract evidence is kept distinct from live evidence; scores from a
synthetic receipt are explicitly not accuracy claims.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, get_args

from langgraph_system_generator.qa.specialist_models import RejectionDetail

SCORE_SCHEMA_VERSION = "semantic-review-score-v1"
RECEIPT_SCHEMA_VERSION = "semantic-review-receipt-v1"
EVIDENCE_KINDS = {"synthetic-contract", "live"}
SYNTHETIC_MODEL_ID = "semantic-review-synthetic-contract"
CASE_STATUSES = (
    "reviewed",
    "skipped",
    "unavailable",
    "invalid_reference",
    "invalid_response",
    "input_limit",
    "output_limit",
    "insufficient_context",
    "cancellation",
    "incomplete",
    "disabled",
)
FINDING_CATEGORIES = {
    "requirements_gap",
    "contradiction",
    "domain_mismatch",
    "unsupported_capability_claim",
    "provided_docs_conflict",
}
ADJUDICATION_VERDICTS = {"supported", "unsupported", "ambiguous", "pending"}


class ScoringError(ValueError):
    """Raised when receipt, dataset, labels, or annotation bindings disagree."""


def canonical_json(value: Any) -> str:
    """Return stable JSON for in-memory hashes and deterministic reports."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _read_json(path: str | Path) -> tuple[Any, str]:
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        # Do not copy parser or OS exception payloads into reports.
        raise ScoringError("Could not read a scoring input as UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ScoringError("Scoring inputs must be JSON objects")
    return value, sha256_bytes(raw)


def _record_status(record: Mapping[str, Any]) -> str:
    raw = record.get("case_status") or record.get("status")
    reason = record.get("reason_code") or record.get("reason")
    aliases = {
        "cancelled": "cancellation",
        "canceled": "cancellation",
    }
    if raw == "incomplete" and reason in {
        "input_limit",
        "output_limit",
        "insufficient_context",
    }:
        raw = reason
    if not isinstance(raw, str):
        raise ScoringError("Receipt contains an unsupported case status")
    status = aliases.get(raw, raw)
    if status not in CASE_STATUSES:
        raise ScoringError("Receipt contains an unsupported case status")
    return status


def _case_maps(
    dataset: Mapping[str, Any], labels: Mapping[str, Any]
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    dataset_cases = dataset.get("cases")
    label_cases = labels.get("cases")
    if not isinstance(dataset_cases, list) or not isinstance(label_cases, list):
        raise ScoringError("Dataset and reference labels must contain case lists")
    ds: dict[str, Mapping[str, Any]] = {}
    refs: dict[str, Mapping[str, Any]] = {}
    for source, target in ((dataset_cases, ds), (label_cases, refs)):
        for item in source:
            if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
                raise ScoringError("Every dataset and label row needs a case_id")
            case_id = item["case_id"]
            if case_id in target:
                raise ScoringError("Dataset or labels contain duplicate case IDs")
            target[case_id] = item
    if set(ds) != set(refs):
        raise ScoringError("Dataset and reference labels contain different case IDs")
    return ds, refs


def _expectation(label_case: Mapping[str, Any]) -> Mapping[str, Any]:
    value = label_case.get("expectation", label_case.get("expected", {}))
    return value if isinstance(value, dict) else {}


def _defects(label_case: Mapping[str, Any]) -> list[dict[str, Any]]:
    defects = label_case.get("defects")
    if isinstance(defects, list):
        result = []
        for defect in defects:
            if not isinstance(defect, dict) or not isinstance(
                defect.get("defect_id"), str
            ):
                raise ScoringError("Each reference defect needs a defect_id")
            categories = defect.get("expected_categories") or defect.get("categories")
            if categories is None:
                categories = _expectation(label_case).get("categories", [])
            if not isinstance(categories, list) or any(
                category not in FINDING_CATEGORIES for category in categories
            ):
                raise ScoringError("Reference defect has invalid expected categories")
            result.append(
                {
                    **defect,
                    "expected_categories": categories,
                    "baseline_detected": defect.get("baseline_detected"),
                }
            )
        ids = [item["defect_id"] for item in result]
        if len(ids) != len(set(ids)):
            raise ScoringError("Reference labels contain duplicate defect IDs")
        return result

    # Small compatibility adapter for early drafts of the label file.
    defect_ids = label_case.get("defect_ids") or []
    expected = _expectation(label_case)
    categories = expected.get("categories") or []
    return [
        {
            "defect_id": defect_id,
            "expected_categories": categories,
            "baseline_detected": None,
        }
        for defect_id in defect_ids
    ]


def _case_kind(label_case: Mapping[str, Any]) -> str:
    expected = _expectation(label_case)
    kind = expected.get("kind") or label_case.get("kind")
    if kind not in {"clean", "defect", "guardrail"}:
        raise ScoringError("Reference label has an unsupported case kind")
    return kind


def _guardrail_expectation(
    label_case: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    expectation = _expectation(label_case)
    expected_status = expectation.get("expected_status") or expectation.get("status")
    expected_reason = expectation.get("expected_reason_code") or expectation.get(
        "reason_code"
    )
    aliases = {"cancelled": "cancellation", "canceled": "cancellation"}
    if isinstance(expected_status, str):
        expected_status = aliases.get(expected_status, expected_status)
    return (
        expected_status if isinstance(expected_status, str) else None,
        expected_reason if isinstance(expected_reason, str) else None,
    )


def _case_is_eligible(label_case: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    if label_case.get("eligibility") != "eligible":
        return False
    baseline = record.get("baseline")
    return not (isinstance(baseline, dict) and baseline.get("eligible") is False)


def _docs_available(
    case: Mapping[str, Any], label_case: Mapping[str, Any]
) -> bool | None:
    expected = _expectation(label_case)
    value = expected.get("docs_available", label_case.get("docs_available"))
    if isinstance(value, bool):
        return value
    value = case.get("docs_available")
    if isinstance(value, bool):
        return value
    for key in ("docs", "docs_context"):
        if isinstance(case.get(key), list):
            return bool(case[key])
    state = case.get("model_state") or case.get("state")
    if isinstance(state, dict):
        for key in ("docs_context", "docs"):
            if isinstance(state.get(key), list):
                return bool(state[key])
    return None


def _annotation_rows(annotations: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if annotations is None:
        return []
    rows = annotations.get("annotations")
    if not isinstance(rows, list):
        raise ScoringError("Annotation document must contain an annotations list")
    root_version = annotations.get("annotation_version")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ScoringError("Annotation entries must be objects")
        required = (
            "case_id",
            "finding_id",
            "verdict",
            "rationale",
            "reviewer_type",
        )
        if any(
            not isinstance(row.get(field), str) or not row[field] for field in required
        ):
            raise ScoringError("Annotation entries are missing required fields")
        if not isinstance(row.get("reviewer_identity") or row.get("reviewer_id"), str):
            raise ScoringError("Annotation entries require a reviewer identity")
        if row["verdict"] not in ADJUDICATION_VERDICTS:
            raise ScoringError("Annotation entry has an unsupported verdict")
        if type(row.get("repetition")) is not int or row["repetition"] < 1:
            raise ScoringError("Annotation repetition must be a positive integer")
        if "resolution" in row and type(row["resolution"]) is not bool:
            raise ScoringError("Annotation resolution marker must be boolean")
        version = row.get("annotation_version", root_version)
        if not isinstance(version, str) or not version:
            raise ScoringError("Annotations must name an annotation version")
        if row["verdict"] == "supported" and not isinstance(
            row.get("matched_defect_id"), str
        ):
            raise ScoringError("Supported annotations must identify a matched defect")
        if row["verdict"] == "unsupported" and row.get("matched_defect_id") is not None:
            raise ScoringError("Unsupported annotations cannot name a matched defect")
        if (
            row["verdict"] in {"ambiguous", "pending"}
            and row.get("matched_defect_id") is not None
        ):
            raise ScoringError("Unresolved annotations cannot name a matched defect")
        resolves = row.get("resolves_annotation_ids", [])
        if not isinstance(resolves, list) or any(
            not isinstance(item, str) for item in resolves
        ):
            raise ScoringError("Resolution references must be a list of annotation IDs")
        if row.get("resolution") is True and not _human_annotation(row):
            raise ScoringError("Only a human annotation can resolve conflicting votes")
        normalized = dict(row)
        normalized["reviewer_identity"] = row.get("reviewer_identity") or row.get(
            "reviewer_id"
        )
        normalized["annotation_version"] = version
        normalized["annotation_id"] = row.get("annotation_id") or sha256_json(row)
        result.append(normalized)
    return result


def _human_annotation(annotation: Mapping[str, Any]) -> bool:
    tokens = re.findall(r"[a-z0-9]+", str(annotation.get("reviewer_type", "")).lower())
    return "human" in tokens and "ai" not in tokens


def _resolve_annotations(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    refs = [row["annotation_id"] for row in rows]
    if not rows:
        return {"status": "pending", "verdict": None, "defect_id": None, "refs": refs}
    vote_rows = [row for row in rows if row.get("resolution") is not True]
    resolutions = [row for row in rows if row.get("resolution") is True]
    votes = {(row["verdict"], row.get("matched_defect_id")) for row in vote_rows}
    if resolutions:
        resolution_votes = {
            (row["verdict"], row.get("matched_defect_id")) for row in resolutions
        }
        vote_ids = {row["annotation_id"] for row in vote_rows}
        resolution_covers_votes = all(
            set(row.get("resolves_annotation_ids", [])) == vote_ids
            for row in resolutions
        )
        if len(resolution_votes) != 1 or not resolution_covers_votes:
            return {
                "status": "disagreement",
                "verdict": None,
                "defect_id": None,
                "refs": refs,
            }
        if not all(_human_annotation(row) for row in resolutions):
            return {
                "status": "pending_independent_adjudication",
                "verdict": None,
                "defect_id": None,
                "refs": refs,
            }
        verdict, defect_id = next(iter(resolution_votes))
        if verdict in {"pending", "ambiguous"}:
            return {
                "status": verdict,
                "verdict": None,
                "defect_id": None,
                "refs": refs,
            }
        return {
            "status": (
                "resolved_after_disagreement"
                if len(votes) > 1
                else "resolved_by_adjudication"
            ),
            "verdict": verdict,
            "defect_id": defect_id,
            "refs": refs,
        }
    if len(votes) != 1:
        return {
            "status": "disagreement",
            "verdict": None,
            "defect_id": None,
            "refs": refs,
        }
    verdict, defect_id = next(iter(votes))
    if verdict == "ambiguous":
        return {
            "status": "ambiguous",
            "verdict": None,
            "defect_id": None,
            "refs": refs,
        }
    if verdict == "pending":
        return {
            "status": "pending",
            "verdict": None,
            "defect_id": None,
            "refs": refs,
        }
    if not any(_human_annotation(row) for row in vote_rows):
        return {
            "status": "pending_independent_adjudication",
            "verdict": None,
            "defect_id": None,
            "refs": refs,
        }
    return {
        "status": "resolved",
        "verdict": verdict,
        "defect_id": defect_id,
        "refs": refs,
    }


def _is_resolved(outcome: Mapping[str, Any]) -> bool:
    return str(outcome.get("status", "")).startswith("resolved")


def _additional_concern_map(
    annotations: Mapping[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if annotations is None:
        return {}
    values = annotations.get("additional_concerns", [])
    if not isinstance(values, list):
        raise ScoringError("Additional concerns must be provided as a list")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for concern in values:
        if not isinstance(concern, dict):
            raise ScoringError("Additional concern entries must be objects")
        case_id = concern.get("case_id")
        concern_id = concern.get("defect_id")
        if not isinstance(case_id, str) or not isinstance(concern_id, str):
            raise ScoringError("Additional concerns need case and defect IDs")
        if not concern_id.startswith("additional:") or len(concern_id) <= len(
            "additional:"
        ):
            raise ScoringError(
                "Additional concern IDs must use the additional: namespace"
            )
        if (
            not isinstance(concern.get("requirement"), str)
            or not concern["requirement"]
        ):
            raise ScoringError("Additional concerns need a concrete requirement")
        if not isinstance(concern.get("source_locations"), list):
            raise ScoringError("Additional concerns need source locations")
        categories = concern.get("expected_categories", [])
        if not isinstance(categories, list) or any(
            category not in FINDING_CATEGORIES for category in categories
        ):
            raise ScoringError("Additional concern categories are invalid")
        if concern.get("baseline_detected") not in (True, False, None):
            raise ScoringError(
                "Additional concern baseline status must be boolean or unknown"
            )
        key = (case_id, concern_id)
        if key in result:
            raise ScoringError("Additional concern IDs must be unique within a case")
        result[key] = concern
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _latency_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = []
    for row in records:
        value = row.get("latency_ms")
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ScoringError("Latency must be a non-negative number")
        if not math.isfinite(value) or value < 0:
            raise ScoringError("Latency must be a non-negative finite number")
        values.append(float(value))
    return {
        "sample_count": len(values),
        "mean_ms": statistics.fmean(values) if values else None,
        "median_ms": statistics.median(values) if values else None,
        "p95_ms": _percentile(values, 0.95),
        "min_ms": min(values) if values else None,
        "max_ms": max(values) if values else None,
    }


def _safe_findings(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = record.get("safe_findings", record.get("findings", []))
    if value is None:
        return []
    if not isinstance(value, list):
        raise ScoringError("Safe findings must be a list")
    result = []
    for finding in value:
        if not isinstance(finding, dict):
            raise ScoringError("Safe findings must be objects")
        if finding.get("category") not in FINDING_CATEGORIES:
            raise ScoringError("Safe finding contains an unsupported category")
        finding_id = finding.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id:
            raise ScoringError("Safe findings require a stable finding_id")
        result.append(finding)
    return result


def _finding_summary(finding: Mapping[str, Any]) -> dict[str, Any]:
    """Retain admitted evidence identity without copying model prose to reports."""
    references = finding.get("references", [])
    if not isinstance(references, list):
        raise ScoringError("Finding references must be a list")
    safe_references = []
    for reference in references:
        if not isinstance(reference, dict):
            raise ScoringError("Finding evidence references must be objects")
        safe_references.append(
            {
                key: reference[key]
                for key in (
                    "source_id",
                    "family",
                    "fingerprint",
                    "start",
                    "end",
                    "cell_index",
                    "version",
                )
                if key in reference
            }
        )
    return {
        "finding_id": finding["finding_id"],
        "category": finding["category"],
        "references": safe_references,
    }


def _build_group_metrics(
    group_records: Sequence[Mapping[str, Any]],
    case_labels: Mapping[str, Mapping[str, Any]],
    defect_hits: set[tuple[str, int, str]],
) -> dict[str, Any]:
    status_counts = Counter(_record_status(record) for record in group_records)
    eligible_clean = []
    eligible_defect_trials: list[
        tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Any]]
    ] = []
    for record in group_records:
        label = case_labels[record["case_id"]]
        if not _case_is_eligible(label, record):
            continue
        kind = _case_kind(label)
        if kind == "clean":
            eligible_clean.append(record)
        elif kind == "defect":
            for defect in _defects(label):
                eligible_defect_trials.append((record, label, defect))
    hit_count = 0
    for record, label, defect in eligible_defect_trials:
        key = (record["case_id"], record["repetition"], defect["defect_id"])
        if key in defect_hits:
            hit_count += 1
    return {
        "selected_trials": len(group_records),
        "reviewed_trials": status_counts["reviewed"],
        "status_counts": {
            status: status_counts.get(status, 0) for status in CASE_STATUSES
        },
        "eligible_clean_trials": len(eligible_clean),
        "eligible_defect_trials": len(eligible_defect_trials),
        "confirmed_defect_hits": hit_count,
        "defect_recall": _ratio(hit_count, len(eligible_defect_trials)),
    }


def score_receipt(
    receipt: Mapping[str, Any],
    dataset: Mapping[str, Any],
    reference_labels: Mapping[str, Any],
    annotations: Mapping[str, Any] | None = None,
    *,
    input_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Score one receipt without pooling it with any other evidence class.

    ``input_hashes`` may supply byte-exact hashes calculated by ``score_files``.
    Direct callers get deterministic canonical-JSON hashes instead.
    """
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ScoringError("Unsupported semantic-review receipt schema")
    evidence_kind = receipt.get("evidence_kind")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ScoringError("Receipt evidence_kind must be synthetic-contract or live")
    dataset_hash = (input_hashes or {}).get("dataset_sha256") or sha256_json(dataset)
    labels_hash = (input_hashes or {}).get("labels_sha256") or sha256_json(
        reference_labels
    )
    receipt_hash = (input_hashes or {}).get("receipt_sha256") or sha256_json(receipt)
    annotation_hash = None
    if annotations is not None:
        annotation_hash = (input_hashes or {}).get("annotation_sha256") or sha256_json(
            annotations
        )

    ds_meta = receipt.get("dataset")
    if not isinstance(ds_meta, dict) or ds_meta.get("sha256") != dataset_hash:
        raise ScoringError("Receipt dataset hash does not match the supplied dataset")
    if receipt.get("labels_sha256") != labels_hash:
        receipt_label_hash = (receipt.get("labels") or {}).get("sha256")
        if receipt_label_hash != labels_hash:
            raise ScoringError("Receipt label hash does not match the supplied labels")
    dataset_id = ds_meta.get("id") or dataset.get("dataset_id") or dataset.get("id")
    if dataset_id != reference_labels.get("dataset_id"):
        raise ScoringError("Dataset and labels do not share a dataset ID")
    if annotations is not None:
        if annotations.get("schema_version") != 1:
            raise ScoringError("Unsupported annotation document schema")
        if not isinstance(annotations.get("annotation_version"), str):
            raise ScoringError("Annotation document needs a version")
        if annotations.get("dataset_sha256") != dataset_hash:
            raise ScoringError("Annotation dataset binding does not match")
        if annotations.get("labels_sha256") != labels_hash:
            raise ScoringError("Annotation label binding does not match")
        expected_receipt_hash = annotations.get("receipt_sha256")
        if expected_receipt_hash is not None and expected_receipt_hash != receipt_hash:
            raise ScoringError("Annotation receipt binding does not match")

    sources = receipt.get("sources")
    effective_config = receipt.get("effective_config")
    if not isinstance(sources, dict) or not isinstance(effective_config, dict):
        raise ScoringError(
            "Receipt must include source provenance and effective config"
        )
    prompt_hash = sources.get("reviewer_prompt_sha256")
    source_hash = sources.get("source_sha256")
    if prompt_hash is not None and not _is_sha256(prompt_hash):
        raise ScoringError("Receipt contains an invalid reviewer prompt hash")
    if source_hash is not None and not _is_sha256(source_hash):
        raise ScoringError("Receipt contains an invalid source hash")
    forbidden_endpoint_fields = {
        "endpoint_base_url",
        "base_url",
        "api_base",
        "endpoint_url",
    }
    if forbidden_endpoint_fields.intersection(effective_config):
        raise ScoringError(
            "Receipt config must retain endpoint policy, not endpoint URLs"
        )
    if any(
        isinstance(value, str) and value.startswith(("https://", "http://"))
        for value in effective_config.values()
    ):
        raise ScoringError("Receipt config must not persist provider endpoint URLs")

    dataset_cases, label_cases = _case_maps(dataset, reference_labels)
    additional_concerns = _additional_concern_map(annotations)
    for case_id, _concern_id in additional_concerns:
        if case_id not in label_cases:
            raise ScoringError("Additional concern references an unknown case")
    receipt_records = receipt.get("records")
    if not isinstance(receipt_records, list):
        raise ScoringError("Receipt must contain a records list")
    if len(receipt_records) > 40:
        raise ScoringError("Receipt exceeds the approved maximum selected trials")
    records: list[dict[str, Any]] = []
    seen_trials: set[tuple[str, int]] = set()
    for source_record in receipt_records:
        if not isinstance(source_record, dict):
            raise ScoringError("Receipt records must be objects")
        raw_case_id = source_record.get("case_id")
        repetition = source_record.get("repetition")
        if (
            not isinstance(raw_case_id, str)
            or raw_case_id not in dataset_cases
            or raw_case_id not in label_cases
        ):
            raise ScoringError(
                "Receipt references a case absent from the bound dataset"
            )
        case_id = raw_case_id
        if type(repetition) is not int or repetition < 1:
            raise ScoringError("Receipt repetition must be a positive integer")
        trial_key = (case_id, repetition)
        if trial_key in seen_trials:
            raise ScoringError("Receipt has duplicate case/repetition rows")
        seen_trials.add(trial_key)
        label = label_cases[case_id]
        if source_record.get("split") not in (None, label.get("split")):
            raise ScoringError(
                "Receipt split disagrees with the bound reference labels"
            )
        expected_domain = label.get("domain", dataset_cases[case_id].get("domain"))
        if source_record.get("domain") not in (None, expected_domain):
            raise ScoringError(
                "Receipt domain disagrees with the bound reference labels"
            )
        row_evidence_kind = source_record.get("evidence_kind", evidence_kind)
        if row_evidence_kind != evidence_kind:
            raise ScoringError("Receipt mixes synthetic and live trial evidence")
        status = _record_status(source_record)
        invocation_count = source_record.get("model_invocations", 0)
        if invocation_count is not None and (
            type(invocation_count) is not int or not 0 <= invocation_count <= 1
        ):
            raise ScoringError("Each trial must report zero or one reviewer invocation")
        attempt_reserved = source_record.get("attempt_reserved", invocation_count == 1)
        dispatch_uncertain = source_record.get("provider_dispatch_uncertain", False)
        if type(attempt_reserved) is not bool or type(dispatch_uncertain) is not bool:
            raise ScoringError("Receipt attempt reservation metadata must be boolean")
        if invocation_count is None and not (
            status in {"cancellation", "unavailable"}
            and attempt_reserved
            and dispatch_uncertain
        ):
            raise ScoringError(
                "Unknown invocation count requires a reserved uncertain dispatch"
            )
        baseline = source_record.get("baseline") or {}
        if not isinstance(baseline, dict):
            raise ScoringError("Receipt baseline metadata must be an object")
        for hash_field in ("candidate_sha256", "context_sha256"):
            value = source_record.get(hash_field)
            if value is not None and not _is_sha256(value):
                raise ScoringError("Receipt contains an invalid candidate/context hash")
        http_request_count = source_record.get("http_request_count", 0)
        if type(http_request_count) is not int or not 0 <= http_request_count <= 1:
            raise ScoringError("Each trial must report zero or one HTTP dispatch")
        detail = source_record.get("rejection_detail")
        if detail is not None and (
            detail not in get_args(RejectionDetail)
            or (source_record.get("reason_code") or source_record.get("reason"))
            not in {"invalid_response", "invalid_reference"}
        ):
            raise ScoringError("Invalid rejection detail")
        safe_findings = _safe_findings(source_record)
        if status != "reviewed" and safe_findings:
            raise ScoringError(
                "Non-reviewed receipt records cannot contain admitted findings"
            )
        if status == "reviewed" and invocation_count != 1:
            raise ScoringError(
                "A reviewed receipt record must show one reviewer invocation"
            )
        if (
            evidence_kind == "live"
            and source_record.get("reported_model") == SYNTHETIC_MODEL_ID
        ):
            raise ScoringError("Live receipt contains a synthetic model ID")
        preflight_reference = status == "invalid_reference" and invocation_count == 0
        if preflight_reference and (
            (source_record.get("reason_code") or source_record.get("reason"))
            != "invalid_reference"
            or http_request_count != 0
            or attempt_reserved
            or dispatch_uncertain
            or detail not in (None, "preflight_invalid_reference")
        ):
            raise ScoringError(
                "Preflight reference failure has inconsistent dispatch metadata"
            )
        if detail == "preflight_invalid_reference" and not preflight_reference:
            raise ScoringError(
                "Preflight reference detail requires a preflight rejection"
            )
        if http_request_count > 1:
            raise ScoringError("A trial cannot dispatch more than one HTTP request")
        if invocation_count is not None and http_request_count > invocation_count:
            raise ScoringError(
                "HTTP dispatch count exceeds the reviewer invocation count"
            )
        if invocation_count == 1 and not attempt_reserved:
            raise ScoringError(
                "A reviewer invocation must have a prior reserved attempt"
            )
        records.append(
            {
                **source_record,
                "case_id": case_id,
                "repetition": repetition,
                "case_status": status,
                "safe_findings": safe_findings,
            }
        )
    if (
        type(receipt.get("attempts_reserved")) is not int
        or not 0 <= receipt["attempts_reserved"] <= 40
    ):
        raise ScoringError("Receipt attempts_reserved exceeds the approved ceiling")
    observed_invocations = sum(row["model_invocations"] or 0 for row in records)
    uncertain_invocations = sum(row.get("model_invocations") is None for row in records)
    reserved_record_count = sum(row.get("attempt_reserved") is True for row in records)
    observed_http_requests = sum(row.get("http_request_count", 0) for row in records)
    if reserved_record_count != receipt["attempts_reserved"]:
        raise ScoringError("Receipt reservation count does not match its trial records")
    if observed_invocations + uncertain_invocations > receipt["attempts_reserved"]:
        raise ScoringError(
            "Observed invocations exceed conservatively reserved attempts"
        )
    if observed_http_requests > receipt["attempts_reserved"]:
        raise ScoringError("Observed HTTP requests exceed reserved attempts")
    annotation_rows = _annotation_rows(annotations)
    findings_by_key: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for record in records:
        for finding in record["safe_findings"]:
            key = (record["case_id"], record["repetition"], finding["finding_id"])
            findings_by_key.setdefault(key, [])
    known_defects = {
        case_id: {item["defect_id"] for item in _defects(label)}
        for case_id, label in label_cases.items()
    }
    for case_id, concern_id in additional_concerns:
        if concern_id in known_defects.get(case_id, set()):
            raise ScoringError(
                "Additional concern IDs must not collide with reference defects"
            )
        known_defects[case_id].add(concern_id)
    annotation_ids = [row["annotation_id"] for row in annotation_rows]
    if len(annotation_ids) != len(set(annotation_ids)):
        raise ScoringError("Annotation IDs must be unique")
    for annotation in annotation_rows:
        key = (
            annotation["case_id"],
            annotation["repetition"],
            annotation["finding_id"],
        )
        if key not in findings_by_key:
            raise ScoringError(
                "Annotation references a finding absent from the receipt"
            )
        defect_id = annotation.get("matched_defect_id")
        if defect_id is not None and defect_id not in known_defects.get(
            annotation["case_id"], set()
        ):
            raise ScoringError(
                "Annotation references a defect absent from its case labels"
            )
        findings_by_key[key].append(annotation)
    adjudication_by_finding = {
        key: _resolve_annotations(rows) for key, rows in findings_by_key.items()
    }

    status_counts = Counter(record["case_status"] for record in records)
    reviewed_no_findings = sum(
        record["case_status"] == "reviewed" and not record["safe_findings"]
        for record in records
    )
    reviewed_with_findings = sum(
        record["case_status"] == "reviewed" and bool(record["safe_findings"])
        for record in records
    )
    reason_counts = Counter(
        str(record.get("reason_code") or record.get("reason") or "unspecified")
        for record in records
    )
    status_reason_counts: dict[str, Counter[str]] = defaultdict(Counter)
    findings_total = 0
    category_counts: Counter[str] = Counter()
    resolved_supported = 0
    resolved_unsupported = 0
    unresolved_findings = 0
    ambiguous_findings = 0
    disagreement_findings = 0
    pending_findings = 0
    duplicate_findings = 0
    duplicate_supported_defect_findings = 0
    adjudicated_finding_count = 0
    unsupported_refs: list[str] = []
    record_adjudications: dict[tuple[str, int], list[dict[str, Any]]] = {}
    defect_hits: set[tuple[str, int, str]] = set()
    for record in records:
        status = record["case_status"]
        reason = str(record.get("reason_code") or record.get("reason") or "unspecified")
        status_reason_counts[status][reason] += 1
        per_record = []
        seen_matches: set[str] = set()
        seen_finding_ids: set[str] = set()
        for finding in record["safe_findings"]:
            findings_total += 1
            category_counts[finding["category"]] += 1
            key = (record["case_id"], record["repetition"], finding["finding_id"])
            outcome = adjudication_by_finding[key]
            refs = list(outcome["refs"])
            duplicate_finding = finding["finding_id"] in seen_finding_ids
            duplicate_supported_match = False
            if duplicate_finding:
                duplicate_findings += 1
            seen_finding_ids.add(finding["finding_id"])
            if not _is_resolved(outcome):
                unresolved_findings += 1
                if outcome["status"] == "ambiguous":
                    ambiguous_findings += 1
                elif outcome["status"] == "disagreement":
                    disagreement_findings += 1
                elif outcome["status"] in {
                    "pending",
                    "pending_independent_adjudication",
                }:
                    pending_findings += 1
                else:
                    pending_findings += 1
            else:
                adjudicated_finding_count += 1
                if outcome["verdict"] == "unsupported":
                    resolved_unsupported += 1
                    unsupported_refs.extend(refs)
                elif outcome["verdict"] == "supported":
                    resolved_supported += 1
                    defect_id = outcome["defect_id"]
                    hit = (record["case_id"], record["repetition"], defect_id)
                    if defect_id in seen_matches:
                        duplicate_supported_match = True
                        if not duplicate_finding:
                            duplicate_findings += 1
                        duplicate_supported_defect_findings += 1
                    else:
                        defect_hits.add(hit)
                        seen_matches.add(defect_id)
            per_record.append(
                {
                    "finding_id": finding["finding_id"],
                    "category": finding["category"],
                    "adjudication_status": outcome["status"],
                    "verdict": outcome["verdict"],
                    "matched_defect_id": outcome["defect_id"],
                    "annotation_refs": refs,
                    "duplicate_finding": duplicate_finding or duplicate_supported_match,
                }
            )
        record_adjudications[(record["case_id"], record["repetition"])] = per_record

    # Every selected row is expected, including rows cancelled before dispatch.
    selected_pairs = {(r["case_id"], r["repetition"]) for r in records}
    selected_cases = receipt.get("selected_cases")
    if not isinstance(selected_cases, list):
        raise ScoringError("Receipt must record every selected case/repetition")
    planned_pairs = set()
    for selected in selected_cases:
        if (
            not isinstance(selected, dict)
            or not isinstance(selected.get("case_id"), str)
            or type(selected.get("repetition")) is not int
            or selected["repetition"] < 1
        ):
            raise ScoringError(
                "Receipt selected_cases entries need case/repetition IDs"
            )
        pair = (selected["case_id"], selected["repetition"])
        if pair in planned_pairs:
            raise ScoringError("Receipt selected_cases contains duplicate trials")
        planned_pairs.add(pair)
    if selected_pairs != planned_pairs:
        raise ScoringError("Receipt must contain one record for every selected trial")
    repetitions = effective_config.get("repetitions")
    if type(repetitions) is not int or not 1 <= repetitions <= 2:
        raise ScoringError("Receipt repetitions exceed the approved pilot limit")
    if len(records) > 20 * repetitions:
        raise ScoringError("Receipt exceeds 20 cases times its repetition limit")

    eligible_records = [
        record
        for record in records
        if _case_is_eligible(label_cases[record["case_id"]], record)
        and _case_kind(label_cases[record["case_id"]]) in {"clean", "defect"}
    ]
    valid_records = [
        record for record in eligible_records if record["case_status"] == "reviewed"
    ]
    eligible_clean_records = [
        record
        for record in eligible_records
        if _case_kind(label_cases[record["case_id"]]) == "clean"
    ]
    reviewed_clean_records = [
        record
        for record in eligible_clean_records
        if record["case_status"] == "reviewed"
    ]
    false_positive_trials = 0
    false_positive_lower_bound_trials = 0
    resolved_clean_trials = 0
    unresolved_clean_trials = 0
    clean_trials_with_confirmed_concerns = 0
    for record in reviewed_clean_records:
        row_annotations = record_adjudications[
            (record["case_id"], record["repetition"])
        ]
        if not row_annotations:
            resolved_clean_trials += 1
        elif any(
            row["adjudication_status"].startswith("resolved")
            and row["verdict"] == "unsupported"
            for row in row_annotations
        ):
            false_positive_lower_bound_trials += 1
        if not row_annotations:
            continue
        if all(
            row["adjudication_status"].startswith("resolved") for row in row_annotations
        ):
            supported_additional = any(
                row["verdict"] == "supported"
                and str(row.get("matched_defect_id", "")).startswith("additional:")
                for row in row_annotations
            )
            unsupported = any(
                row["verdict"] == "unsupported" for row in row_annotations
            )
            if supported_additional and not unsupported:
                clean_trials_with_confirmed_concerns += 1
            else:
                resolved_clean_trials += 1
                if unsupported:
                    false_positive_trials += 1
        else:
            unresolved_clean_trials += 1
    unresolved_clean_trials += len(eligible_clean_records) - len(reviewed_clean_records)

    eligible_defect_trials: list[tuple[dict[str, Any], dict[str, Any]]] = []
    baseline_blocked_records = []
    for record in records:
        label = label_cases[record["case_id"]]
        if _case_kind(label) != "defect":
            continue
        baseline = record.get("baseline") or {}
        if label.get("eligibility") == "eligible" and baseline.get("eligible") is False:
            baseline_blocked_records.append(record)
        if not _case_is_eligible(label, record):
            continue
        for defect in _defects(label):
            eligible_defect_trials.append((record, defect))
    all_defect_trials = len(eligible_defect_trials)
    detected_defect_trials = sum(
        (
            record["case_id"],
            record["repetition"],
            defect["defect_id"],
        )
        in defect_hits
        for record, defect in eligible_defect_trials
    )
    eligible_unique_defects = {
        (record["case_id"], defect["defect_id"])
        for record, defect in eligible_defect_trials
    }
    detected_unique_defects = {
        (case_id, defect_id)
        for case_id, _repetition, defect_id in defect_hits
        if (case_id, defect_id) in eligible_unique_defects
    }
    eligible_defect_case_trials = {
        (record["case_id"], record["repetition"])
        for record, _defect in eligible_defect_trials
    }
    additional_defect_trials = 0
    baseline_redundant_defect_trials = 0
    baseline_unknown_defect_trials = 0
    additional_ids: set[tuple[str, str]] = set()
    additional_label_ids: set[tuple[str, str]] = set()
    baseline_unknown_additional_ids: set[tuple[str, str]] = set()
    category_defect_trials: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = (
        defaultdict(list)
    )
    for record, defect in eligible_defect_trials:
        key = (record["case_id"], record["repetition"], defect["defect_id"])
        detected = key in defect_hits
        baseline_detected = defect.get("baseline_detected")
        if detected and baseline_detected is False:
            additional_defect_trials += 1
            additional_ids.add((record["case_id"], defect["defect_id"]))
        elif detected and baseline_detected is True:
            baseline_redundant_defect_trials += 1
        elif detected:
            baseline_unknown_defect_trials += 1
        for category in defect["expected_categories"]:
            category_defect_trials[category].append((record, defect))

    for (case_id, concern_id), concern in additional_concerns.items():
        for record in records:
            if record["case_id"] != case_id or not _case_is_eligible(
                label_cases[case_id], record
            ):
                continue
            if (case_id, record["repetition"], concern_id) not in defect_hits:
                continue
            baseline_detected = concern.get("baseline_detected")
            if baseline_detected is False:
                additional_defect_trials += 1
                additional_ids.add((case_id, concern_id))
                additional_label_ids.add((case_id, concern_id))
            elif baseline_detected is True:
                baseline_redundant_defect_trials += 1
            else:
                baseline_unknown_defect_trials += 1
                baseline_unknown_additional_ids.add((case_id, concern_id))

    category_metrics = {}
    for category, trials in sorted(category_defect_trials.items()):
        hits = sum(
            (record["case_id"], record["repetition"], defect["defect_id"])
            in defect_hits
            for record, defect in trials
        )
        category_metrics[category] = {
            "eligible_defect_trials": len(trials),
            "confirmed_detected_trials": hits,
            "recall": _ratio(hits, len(trials)),
            "candidate_category_overlap_is_not_confirmation": True,
        }

    by_split = {}
    splits = sorted(
        {str(label_cases[r["case_id"]].get("split", "unspecified")) for r in records}
    )
    for split in splits:
        grouped = [
            r
            for r in records
            if str(label_cases[r["case_id"]].get("split", "unspecified")) == split
        ]
        by_split[split] = _build_group_metrics(grouped, label_cases, defect_hits)
    by_repetition = {}
    for repetition in sorted({r["repetition"] for r in records}):
        by_repetition[str(repetition)] = _build_group_metrics(
            [r for r in records if r["repetition"] == repetition],
            label_cases,
            defect_hits,
        )
    by_category = {}
    for category, trials in sorted(category_defect_trials.items()):
        group_keys = {(record["case_id"], record["repetition"]) for record, _ in trials}
        grouped = [
            record
            for record in records
            if (record["case_id"], record["repetition"]) in group_keys
        ]
        by_category[category] = {
            **category_metrics[category],
            "selected_trials": len(grouped),
            "status_counts": {
                status: sum(record["case_status"] == status for record in grouped)
                for status in CASE_STATUSES
            },
        }

    docs_missing_records = []
    missing_docs_expected_records = []
    for record in records:
        case = dataset_cases[record["case_id"]]
        label = label_cases[record["case_id"]]
        available = _docs_available(case, label)
        if available is False:
            docs_missing_records.append(record)
            expected = _expectation(label)
            expectation = expected.get("missing_docs_expectation") or label.get(
                "missing_docs_expectation"
            )
            if expectation in (True, "abstain", "insufficient_context"):
                missing_docs_expected_records.append(record)
    missing_docs_abstentions = sum(
        record["case_status"] == "insufficient_context"
        for record in docs_missing_records
    )
    missing_docs_claims = sum(
        finding["category"] == "provided_docs_conflict"
        for record in docs_missing_records
        for finding in record["safe_findings"]
    )
    expected_missing_docs_abstentions = sum(
        record["case_status"] == "insufficient_context"
        for record in missing_docs_expected_records
    )
    guardrail_expectation_rows = []
    for record in records:
        label = label_cases[record["case_id"]]
        if _case_kind(label) != "guardrail":
            continue
        expected_status, expected_reason = _guardrail_expectation(label)
        if expected_status is None and expected_reason is None:
            continue
        actual_reason = str(
            record.get("reason_code") or record.get("reason") or "unspecified"
        )
        matches = (
            expected_status is None or expected_status == record["case_status"]
        ) and (expected_reason is None or expected_reason == actual_reason)
        guardrail_expectation_rows.append(
            {
                "case_id": record["case_id"],
                "repetition": record["repetition"],
                "expected_status": expected_status,
                "expected_reason_code": expected_reason,
                "actual_status": record["case_status"],
                "actual_reason_code": actual_reason,
                "matches": matches,
            }
        )

    admitted_calls = [
        record
        for record in records
        if record["model_invocations"] == 1 or record["http_request_count"] > 0
    ]
    admission_failures = sum(
        record["case_status"] == "invalid_reference" for record in admitted_calls
    )
    latency_by_status = {
        status: _latency_summary([r for r in records if r["case_status"] == status])
        for status in CASE_STATUSES
    }
    unresolved_by_status = Counter(
        row["adjudication_status"]
        for rows in record_adjudications.values()
        for row in rows
        if not row["adjudication_status"].startswith("resolved")
    )
    baseline_stratum = {
        "baseline_blocked_defect_trials": len(baseline_blocked_records),
        "baseline_blocked_case_ids": sorted(
            {row["case_id"] for row in baseline_blocked_records}
        ),
        "excluded_from_eligible_defect_recall": True,
    }

    scored_records = []
    for record in records:
        record_key = (record["case_id"], record["repetition"])
        scored_records.append(
            {
                "case_id": record["case_id"],
                "repetition": record["repetition"],
                "split": label_cases[record["case_id"]].get("split"),
                "domain": label_cases[record["case_id"]].get(
                    "domain", dataset_cases[record["case_id"]].get("domain")
                ),
                "case_status": record["case_status"],
                "reason_code": record.get("reason_code") or record.get("reason"),
                "rejection_detail": record.get("rejection_detail"),
                "model_invocations": record["model_invocations"],
                "candidate_sha256": record.get("candidate_sha256"),
                "context_sha256": record.get("context_sha256"),
                "latency_ms": record.get("latency_ms"),
                "requested_model": record.get("requested_model"),
                "reported_model": record.get("reported_model"),
                "provenance": record.get("provenance", evidence_kind),
                "baseline": record.get("baseline"),
                "safe_findings": [
                    _finding_summary(finding) for finding in record["safe_findings"]
                ],
                "finding_adjudications": record_adjudications[record_key],
                "annotation_refs": list(
                    dict.fromkeys(
                        ref
                        for item in record_adjudications[record_key]
                        for ref in item["annotation_refs"]
                    )
                ),
            }
        )

    independently_adjudicated = any(_human_annotation(row) for row in annotation_rows)
    quality_statement = (
        "synthetic_contract_evidence_only_live_quality_not_measured"
        if evidence_kind == "synthetic-contract"
        else (
            "descriptive_live_evidence_with_independent_annotations"
            if independently_adjudicated
            else "live_calls_observed_but_semantic_quality_not_adjudicated"
        )
    )
    clean_rate = _ratio(false_positive_trials, resolved_clean_trials)
    precision = _ratio(resolved_supported, adjudicated_finding_count)
    report = {
        "schema_version": SCORE_SCHEMA_VERSION,
        "evidence_kind": evidence_kind,
        "quality_statement": quality_statement,
        "claim_scope": quality_statement,
        "accuracy_claim_allowed": False,
        "independent_adjudication_available": independently_adjudicated,
        "label_origin": reference_labels.get("label_origin", "unspecified"),
        "binding": {
            "run_id": receipt.get("run_id"),
            "plan_sha256": receipt.get("plan_sha256"),
            "receipt_sha256": receipt_hash,
            "dataset_id": dataset_id,
            "dataset_sha256": dataset_hash,
            "reference_labels_sha256": labels_hash,
            "annotation_sha256": annotation_hash,
            "reviewer_prompt_sha256": prompt_hash,
            "source_revision": sources.get("source_revision"),
            "source_sha256": source_hash,
        },
        "source_provenance": sources,
        "effective_config": effective_config,
        "attempts_reserved": receipt["attempts_reserved"],
        "attempts_observed": {
            "model_invocations_observed": observed_invocations,
            "model_invocations_uncertain": uncertain_invocations,
            "http_requests_observed": observed_http_requests,
        },
        "selected_trial_count": len(records),
        "status_counts": {
            status: status_counts.get(status, 0) for status in CASE_STATUSES
        },
        "reason_counts": dict(sorted(reason_counts.items())),
        "rejection_detail_counts": dict(
            sorted(
                Counter(
                    record.get("rejection_detail") or "unavailable"
                    for record in records
                    if (record.get("reason_code") or record.get("reason"))
                    in {"invalid_response", "invalid_reference"}
                ).items()
            )
        ),
        "review_outcomes": {
            "reviewed_no_findings": reviewed_no_findings,
            "reviewed_with_findings": reviewed_with_findings,
        },
        "status_reason_counts": {
            status: dict(sorted(counts.items()))
            for status, counts in sorted(status_reason_counts.items())
        },
        "valid_review_coverage": {
            "reviewed_eligible_quality_trials": len(valid_records),
            "eligible_quality_trial_denominator": len(eligible_records),
            "value": _ratio(len(valid_records), len(eligible_records)),
            "guardrail_trials_excluded": sum(
                _case_kind(label_cases[r["case_id"]]) == "guardrail" for r in records
            ),
            "baseline_blocked_trials_excluded": len(baseline_blocked_records),
        },
        "clean_case_false_positive_rate": {
            "confirmed_false_positive_clean_trials": false_positive_trials,
            "resolved_reviewed_clean_trial_denominator": resolved_clean_trials,
            "eligible_clean_trial_denominator": len(eligible_clean_records),
            "reviewed_clean_trials": len(reviewed_clean_records),
            "unresolved_clean_trials": unresolved_clean_trials,
            "excluded_clean_trials_with_confirmed_concerns": clean_trials_with_confirmed_concerns,
            "value": clean_rate,
            "confirmed_false_positive_lower_bound_trials": false_positive_lower_bound_trials,
            "confirmed_lower_bound_over_eligible_clean_trials": _ratio(
                false_positive_lower_bound_trials, len(eligible_clean_records)
            ),
            "confirmed_lower_bound_over_reviewed_clean_trials": _ratio(
                false_positive_lower_bound_trials, len(reviewed_clean_records)
            ),
            "interpretation": (
                "Conditional on fully adjudicated reviewed clean trials; unresolved trials remain in the eligible-cohort lower bound"
            ),
        },
        "defect_detection_recall": {
            "confirmed_one_to_one_defect_hits": detected_defect_trials,
            "eligible_defect_trial_denominator": all_defect_trials,
            "eligible_defect_case_trial_denominator": len(eligible_defect_case_trials),
            "eligible_unique_defect_denominator": len(eligible_unique_defects),
            "confirmed_unique_defects_detected": len(detected_unique_defects),
            "confirmed_unique_defect_recall": _ratio(
                len(detected_unique_defects), len(eligible_unique_defects)
            ),
            "value": _ratio(detected_defect_trials, all_defect_trials),
            "undetected_including_abstentions_and_invalid_reviews": (
                all_defect_trials - detected_defect_trials
            ),
            "baseline_blocked_skip_stratum": baseline_stratum,
        },
        "finding_precision": {
            "independently_adjudicated_supported_findings": resolved_supported,
            "independently_adjudicated_finding_denominator": adjudicated_finding_count,
            "value": precision,
            "pending_or_ambiguous_findings": unresolved_findings,
            "unresolved_by_status": dict(sorted(unresolved_by_status.items())),
            "annotation_origin_requirement": (
                "human annotation or explicit human adjudication; unresolved disagreements remain pending"
            ),
        },
        "finding_adjudication": {
            "total_admitted_findings": findings_total,
            "supported": resolved_supported,
            "unsupported": resolved_unsupported,
            "ambiguous": ambiguous_findings,
            "disagreement": disagreement_findings,
            "pending": pending_findings,
            "duplicates_after_one_to_one_matching": duplicate_findings,
            "confirmed_duplicate_defect_findings": duplicate_supported_defect_findings,
            "duplicate_rate_over_admitted_findings": _ratio(
                duplicate_findings, findings_total
            ),
            "unsupported_rate_over_adjudicated_findings": _ratio(
                resolved_unsupported, adjudicated_finding_count
            ),
            "counts_by_category": dict(sorted(category_counts.items())),
            "category_overlap_is_candidate_only": True,
        },
        "evidence_admission": {
            "invalid_reference_trials": admission_failures,
            "preflight_invalid_reference_trials": sum(
                record["case_status"] == "invalid_reference"
                and record["model_invocations"] == 0
                for record in records
            ),
            "invoked_trial_denominator": len(admitted_calls),
            "failure_rate": _ratio(admission_failures, len(admitted_calls)),
            "dispatch_uncertain_trials": uncertain_invocations,
        },
        "missing_docs_behavior": {
            "records_with_docs_unavailable": len(docs_missing_records),
            "insufficient_context_records_without_docs": missing_docs_abstentions,
            "abstention_rate_when_docs_unavailable": _ratio(
                missing_docs_abstentions, len(docs_missing_records)
            ),
            "docs_conflict_findings_admitted_without_docs": missing_docs_claims,
            "explicit_abstention_expectation_trials": len(
                missing_docs_expected_records
            ),
            "explicit_expectation_abstentions": expected_missing_docs_abstentions,
            "explicit_expectation_compliance": _ratio(
                expected_missing_docs_abstentions, len(missing_docs_expected_records)
            ),
        },
        "guardrail_expectation_agreement": {
            "expected_trial_denominator": len(guardrail_expectation_rows),
            "matching_trials": sum(
                row["matches"] for row in guardrail_expectation_rows
            ),
            "mismatching_trials": sum(
                not row["matches"] for row in guardrail_expectation_rows
            ),
            "value": _ratio(
                sum(row["matches"] for row in guardrail_expectation_rows),
                len(guardrail_expectation_rows),
            ),
            "records": guardrail_expectation_rows,
        },
        "additional_confirmed_concerns_beyond_deterministic_baseline": {
            "additional_confirmed_defect_trials": additional_defect_trials,
            "baseline_redundant_confirmed_defect_trials": baseline_redundant_defect_trials,
            "baseline_classification_unknown_confirmed_defect_trials": baseline_unknown_defect_trials,
            "additional_unique_defects": len(additional_ids),
            "additional_reference_defect_ids": [
                {"case_id": case_id, "defect_id": defect_id}
                for case_id, defect_id in sorted(additional_ids - additional_label_ids)
            ],
            "additional_concern_ids": [
                {"case_id": case_id, "defect_id": defect_id}
                for case_id, defect_id in sorted(additional_label_ids)
            ],
            "baseline_unknown_additional_concern_ids": [
                {"case_id": case_id, "defect_id": defect_id}
                for case_id, defect_id in sorted(baseline_unknown_additional_ids)
            ],
        },
        "latency": {
            "overall": _latency_summary(records),
            "by_status": latency_by_status,
        },
        "by_category": category_metrics,
        "by_split": by_split,
        "by_repetition": by_repetition,
        "records": scored_records,
        "limitations": [
            "Advisory review measures detection opinions; it does not repair outputs or establish generated-system correctness.",
            "Twenty cases are descriptive and do not support broad production-accuracy or automatic-blocking claims.",
            "Category overlap is a candidate match only; only versioned independent annotations count as confirmed findings.",
            "Synthetic contract evidence cannot be pooled with live evidence as an accuracy claim.",
        ],
    }
    return report


def score_files(
    receipt_path: str | Path,
    dataset_path: str | Path,
    labels_path: str | Path,
    annotations_path: str | Path | None = None,
    *,
    output_path: str | Path | None = None,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load frozen JSON inputs, verify byte hashes, score, and optionally persist."""
    output_json = Path(output_path) if output_path is not None else None
    output_markdown = (
        output_json.with_suffix(".md") if output_json is not None else None
    )
    if output_json is not None and output_markdown is not None:
        if output_json.suffix.lower() != ".json":
            raise ScoringError("Score output path must end in .json")
        input_paths = [receipt_path, dataset_path, labels_path]
        if annotations_path is not None:
            input_paths.append(annotations_path)
        if plan_path is not None:
            input_paths.append(plan_path)
        protected = {Path(path).resolve() for path in input_paths}
        destinations = {output_json.resolve(), output_markdown.resolve()}
        if protected.intersection(destinations):
            raise ScoringError("Score output cannot overwrite a frozen evidence input")
        if output_json.exists() or output_markdown.exists():
            raise ScoringError("Refusing to overwrite an existing score report")
    receipt, receipt_hash = _read_json(receipt_path)
    dataset, dataset_hash = _read_json(dataset_path)
    labels, labels_hash = _read_json(labels_path)
    annotation_doc = None
    annotation_hash = None
    if annotations_path is not None:
        annotation_doc, annotation_hash = _read_json(annotations_path)
    input_hashes = {
        "receipt_sha256": receipt_hash,
        "dataset_sha256": dataset_hash,
        "labels_sha256": labels_hash,
    }
    if annotation_hash is not None:
        input_hashes["annotation_sha256"] = annotation_hash
    if plan_path is not None:
        plan, _raw_plan_hash = _read_json(plan_path)
        _verify_plan_binding(plan, receipt)
    report = score_receipt(
        receipt,
        dataset,
        labels,
        annotation_doc,
        input_hashes=input_hashes,
    )
    if output_json is not None and output_markdown is not None:
        _write_report_pair(output_json, output_markdown, report)
    return report


def _ratio_text(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def _markdown_report(report: Mapping[str, Any]) -> str:
    """Render an aggregate-only handoff without prompts, prose, or rationales."""
    binding = report["binding"]
    coverage = report["valid_review_coverage"]
    clean = report["clean_case_false_positive_rate"]
    recall = report["defect_detection_recall"]
    precision = report["finding_precision"]
    evidence = report["evidence_admission"]
    missing_docs = report["missing_docs_behavior"]
    guardrail = report["guardrail_expectation_agreement"]
    latency = report["latency"]["overall"]
    status_lines = [
        f"| {status} | {count} |" for status, count in report["status_counts"].items()
    ]
    reason_lines = [
        f"| {reason} | {count} |" for reason, count in report["reason_counts"].items()
    ] or ["| unspecified | 0 |"]
    category_lines = [
        f"| {category} | {data['confirmed_detected_trials']} / "
        f"{data['eligible_defect_trials']} | {_ratio_text(data['recall'])} |"
        for category, data in report["by_category"].items()
    ] or ["| N/A | 0 / 0 | N/A |"]
    split_lines = [
        f"| {split} | {data['reviewed_trials']} / {data['selected_trials']} | "
        f"{data['confirmed_defect_hits']} / {data['eligible_defect_trials']} | "
        f"{_ratio_text(data['defect_recall'])} |"
        for split, data in report["by_split"].items()
    ] or ["| N/A | 0 / 0 | 0 / 0 | N/A |"]
    repetition_lines = [
        f"| {repetition} | {data['reviewed_trials']} / {data['selected_trials']} | "
        f"{data['confirmed_defect_hits']} / {data['eligible_defect_trials']} | "
        f"{_ratio_text(data['defect_recall'])} |"
        for repetition, data in report["by_repetition"].items()
    ] or ["| N/A | 0 / 0 | 0 / 0 | N/A |"]
    extra = report["additional_confirmed_concerns_beyond_deterministic_baseline"]
    concern_ids = [item["defect_id"] for item in extra["additional_concern_ids"]]
    if not concern_ids:
        concern_ids = ["None independently confirmed in this run."]
    lines = [
        "# Semantic reviewer score report",
        "",
        f"- Evidence kind: `{report['evidence_kind']}`",
        f"- Claim scope: `{report['claim_scope']}`",
        f"- Accuracy claim allowed: `{str(report['accuracy_claim_allowed']).lower()}`",
        f"- Dataset: `{binding['dataset_id']}` / `{binding['dataset_sha256']}`",
        f"- Reference labels SHA-256: `{binding['reference_labels_sha256']}`",
        f"- Annotation SHA-256: `{binding['annotation_sha256'] or 'none'}`",
        f"- Plan SHA-256: `{binding['plan_sha256'] or 'none'}`",
        f"- Reviewer prompt SHA-256: `{binding['reviewer_prompt_sha256'] or 'unknown'}`",
        (
            f"- Source revision/hash: `{binding['source_revision'] or 'unknown'}` / "
            f"`{binding['source_sha256'] or 'unknown'}`"
        ),
        (
            f"- Selected trials: {report['selected_trial_count']}; attempts reserved: "
            f"{report['attempts_reserved']}; observed HTTP requests: "
            f"{report['attempts_observed']['http_requests_observed']}"
        ),
        "",
        "## Review outcomes",
        "",
        f"Reviewed with no findings: {report['review_outcomes']['reviewed_no_findings']}",
        f"Reviewed with findings: {report['review_outcomes']['reviewed_with_findings']}",
        (
            f"Valid-review coverage: {coverage['reviewed_eligible_quality_trials']} / "
            f"{coverage['eligible_quality_trial_denominator']} "
            f"({_ratio_text(coverage['value'])})"
        ),
        "",
        "### Status counts",
        "",
        "| Status | Trials |",
        "| --- | ---: |",
        *status_lines,
        "",
        "### Reason counts",
        "",
        "| Reason | Trials |",
        "| --- | ---: |",
        *reason_lines,
        "",
        "### Rejection details",
        "",
        "| Detail | Trials |",
        "| --- | ---: |",
        *(
            f"| {detail} | {count} |"
            for detail, count in report["rejection_detail_counts"].items()
        ),
        "",
        f"Preflight reference failures: {evidence['preflight_invalid_reference_trials']}",
        "",
        "## Semantic metrics",
        "",
        (
            f"Clean false-positive rate on fully adjudicated reviewed trials: "
            f"{clean['confirmed_false_positive_clean_trials']} / "
            f"{clean['resolved_reviewed_clean_trial_denominator']} "
            f"({_ratio_text(clean['value'])}); unresolved clean trials: "
            f"{clean['unresolved_clean_trials']}; with confirmed additional concerns: "
            f"{clean['excluded_clean_trials_with_confirmed_concerns']}; confirmed lower bound: "
            f"{clean['confirmed_false_positive_lower_bound_trials']} / "
            f"{clean['eligible_clean_trial_denominator']} eligible clean trials "
            f"({_ratio_text(clean['confirmed_lower_bound_over_eligible_clean_trials'])})"
        ),
        (
            f"Defect recall: {recall['confirmed_one_to_one_defect_hits']} / "
            f"{recall['eligible_defect_trial_denominator']} "
            f"({_ratio_text(recall['value'])}); undetected, including abstentions and "
            f"invalid reviews: {recall['undetected_including_abstentions_and_invalid_reviews']}; "
            f"unique defects: {recall['confirmed_unique_defects_detected']} / "
            f"{recall['eligible_unique_defect_denominator']} "
            f"({_ratio_text(recall['confirmed_unique_defect_recall'])})"
        ),
        (
            f"Finding precision after independent adjudication: "
            f"{precision['independently_adjudicated_supported_findings']} / "
            f"{precision['independently_adjudicated_finding_denominator']} "
            f"({_ratio_text(precision['value'])}); pending/ambiguous: "
            f"{precision['pending_or_ambiguous_findings']}"
        ),
        (
            f"Duplicates after one-to-one matching: "
            f"{report['finding_adjudication']['duplicates_after_one_to_one_matching']}; "
            f"unsupported findings: {report['finding_adjudication']['unsupported']}"
        ),
        (
            f"Evidence-admission failures: {evidence['invalid_reference_trials']} / "
            f"{evidence['invoked_trial_denominator']} "
            f"({_ratio_text(evidence['failure_rate'])})"
        ),
        (
            f"Missing-docs cohort: {missing_docs['records_with_docs_unavailable']} trials; "
            f"insufficient-context abstentions: "
            f"{missing_docs['insufficient_context_records_without_docs']}; admitted docs-conflict "
            f"findings without docs: {missing_docs['docs_conflict_findings_admitted_without_docs']}"
        ),
        (
            f"Guardrail expected status/reason agreement: {guardrail['matching_trials']} / "
            f"{guardrail['expected_trial_denominator']} "
            f"({_ratio_text(guardrail['value'])})"
        ),
        (
            f"Latency: n={latency['sample_count']}, mean={_ratio_text(latency['mean_ms'])} ms, "
            f"median={_ratio_text(latency['median_ms'])} ms, p95={_ratio_text(latency['p95_ms'])} ms"
        ),
        "",
        "### Recall by category",
        "",
        "| Category | Confirmed / eligible defects | Recall |",
        "| --- | ---: | ---: |",
        *category_lines,
        "",
        "### Results by split",
        "",
        "| Split | Reviewed / selected | Detected / eligible defects | Recall |",
        "| --- | ---: | ---: | ---: |",
        *split_lines,
        "",
        "### Results by repetition",
        "",
        "| Repetition | Reviewed / selected | Detected / eligible defects | Recall |",
        "| ---: | ---: | ---: | ---: |",
        *repetition_lines,
        "",
        "## Additional concerns beyond the deterministic baseline",
        "",
        f"Confirmed additional reference-defect trials: {extra['additional_confirmed_defect_trials']}",
        (
            f"Confirmed redundant findings already detected by the baseline: "
            f"{extra['baseline_redundant_confirmed_defect_trials']}"
        ),
        "Additional concern IDs: " + ", ".join(f"`{value}`" for value in concern_ids),
        "",
        "## Limitations",
        "",
        *[f"- {item}" for item in report["limitations"]],
        "",
    ]
    return "\n".join(lines)


def _write_report_pair(
    json_path: Path, markdown_path: Path, report: Mapping[str, Any]
) -> None:
    contents = (
        (json_path, canonical_json(report) + "\n"),
        (markdown_path, _markdown_report(report)),
    )
    created: list[Path] = []
    try:
        for path, content in contents:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(path)
                stream.write(content)
    except (OSError, FileExistsError) as exc:
        for path in reversed(created):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ScoringError(
            "Could not create new JSON and Markdown score reports"
        ) from exc


def _verify_plan_binding(plan: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    """Verify the receipt still reflects the self-hashed reviewed plan."""
    if (
        plan.get("schema_version") != 1
        or plan.get("plan_kind") != "semantic-review-live-pilot"
    ):
        raise ScoringError("Unsupported approved plan schema")
    declared_hash = plan.get("plan_sha256")
    if not _is_sha256(declared_hash):
        raise ScoringError("Approved plan does not contain a valid plan hash")
    unhashed = dict(plan)
    unhashed.pop("plan_sha256", None)
    if sha256_json(unhashed) != declared_hash:
        raise ScoringError("Approved plan self-hash is invalid")
    if receipt.get("plan_sha256") != declared_hash:
        raise ScoringError("Receipt plan hash does not match the supplied plan")

    sources = receipt.get("sources") or {}
    dataset = receipt.get("dataset") or {}
    labels = plan.get("labels") or {}
    planned_dataset = plan.get("dataset") or {}
    plan_config = plan.get("effective_config") or {}
    receipt_config = receipt.get("effective_config") or {}
    if not all(
        isinstance(value, dict)
        for value in (
            sources,
            dataset,
            labels,
            planned_dataset,
            plan_config,
            receipt_config,
        )
    ):
        raise ScoringError("Approved plan and receipt bindings are incomplete")
    if (
        planned_dataset.get("id") != dataset.get("id")
        or planned_dataset.get("sha256") != dataset.get("sha256")
        or labels.get("sha256")
        != receipt.get("labels_sha256", (receipt.get("labels") or {}).get("sha256"))
    ):
        raise ScoringError(
            "Receipt dataset/label bindings differ from the approved plan"
        )
    if (
        plan.get("source_revision") != sources.get("source_revision")
        or plan.get("source_sha256") != sources.get("source_sha256")
        or plan.get("reviewer_prompt_sha256") != sources.get("reviewer_prompt_sha256")
    ):
        raise ScoringError("Receipt source or prompt differs from the approved plan")
    if plan_config != receipt_config or plan.get("repetitions") != receipt_config.get(
        "repetitions"
    ):
        raise ScoringError(
            "Receipt model or effective configuration differs from the approved plan"
        )
    if (
        plan.get("evidence_kind")
        != "synthetic-contract-only-until-separately-authorized-live-run"
    ):
        raise ScoringError("Plan live-pilot evidence scope is not recognized")

    forbidden_fields = {"endpoint_base_url", "base_url", "api_base", "endpoint_url"}

    def reject_endpoint_values(value: Any) -> None:
        if isinstance(value, dict):
            if forbidden_fields.intersection(value):
                raise ScoringError(
                    "Approved plan must store endpoint policy, not endpoint URLs"
                )
            for nested in value.values():
                reject_endpoint_values(nested)
        elif isinstance(value, list):
            for nested in value:
                reject_endpoint_values(nested)
        elif isinstance(value, str) and value.startswith(("https://", "http://")):
            raise ScoringError("Approved plan must not persist provider endpoint URLs")

    reject_endpoint_values(plan)

    attempt_policy = plan.get("attempt_policy") or {}
    plan_repetitions = plan.get("repetitions")
    selected = plan.get("selected_cases")
    if (
        type(plan_repetitions) is not int
        or not 1 <= plan_repetitions <= 2
        or not isinstance(selected, list)
        or len(selected) > 20
        or not isinstance(attempt_policy, dict)
    ):
        raise ScoringError("Approved plan exceeds the pilot case/repetition limits")
    if attempt_policy.get("maximum_provider_attempts_for_selected_cases", 41) > 40:
        raise ScoringError("Approved plan exceeds the reviewer-call ceiling")
    if (
        attempt_policy.get("one_at_a_time") is not True
        or attempt_policy.get("automatic_retries") not in (False, 0)
        or attempt_policy.get("automatic_model_switches") not in (False, 0)
        or attempt_policy.get("automatic_resume") not in (False, 0)
        or plan_config.get("concurrency") != 1
        or plan_config.get("max_retries") != 0
    ):
        raise ScoringError(
            "Approved plan contains concurrency, retry, switch, or resume behavior"
        )

    expected_pairs: set[tuple[str, int]] = set()
    case_ids: set[str] = set()
    for item in selected:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise ScoringError("Approved plan selected case is malformed")
        case_id = item["case_id"]
        if case_id in case_ids:
            raise ScoringError("Approved plan repeats a selected case")
        case_ids.add(case_id)
        expected_pairs.update(
            (case_id, repetition) for repetition in range(1, plan_repetitions + 1)
        )
    actual_pairs = {
        (row.get("case_id"), row.get("repetition"))
        for row in receipt.get("selected_cases", [])
        if isinstance(row, dict)
    }
    if actual_pairs != expected_pairs:
        raise ScoringError("Receipt selected trials differ from the approved plan")
    planned_by_case = {item["case_id"]: item for item in selected}
    receipt_records = receipt.get("records")
    if not isinstance(receipt_records, list):
        raise ScoringError("Receipt must contain records for the approved plan")
    for record in receipt_records:
        if not isinstance(record, dict):
            raise ScoringError("Receipt record is malformed")
        case_id = record.get("case_id")
        slot = planned_by_case.get(case_id)
        if slot is None:
            raise ScoringError("Receipt record has no approved candidate slot")
        if record.get("evidence_kind") != receipt.get("evidence_kind"):
            raise ScoringError("Receipt record evidence kind differs from its run")
        for field in (
            "pair_id",
            "candidate_ref",
            "split",
            "domain",
            "candidate_sha256",
            "context_sha256",
            "context_chars",
            "docs_available",
            "baseline",
            "provenance",
        ):
            if record.get(field) != slot.get(field):
                raise ScoringError(
                    "Receipt candidate provenance differs from the approved slot"
                )
        if not isinstance(slot.get("eligible"), bool):
            raise ScoringError("Approved candidate eligibility is missing")
        slot_baseline = slot.get("baseline")
        if (
            not isinstance(slot_baseline, dict)
            or type(slot_baseline.get("eligible")) is not bool
            or (slot["eligible"] and not slot_baseline["eligible"])
        ):
            raise ScoringError(
                "Approved candidate eligibility conflicts with its deterministic baseline"
            )
        if (
            _record_status(record) == "invalid_reference"
            and record.get("model_invocations") == 0
            and (
                slot["eligible"]
                or slot.get("preflight_status") != "invalid_reference"
                or slot.get("preflight_reason_code") != "invalid_reference"
            )
        ):
            raise ScoringError(
                "Preflight reference failure differs from the approved slot"
            )
        if not slot["eligible"] and (
            record.get("attempt_reserved") is not False
            or record.get("model_invocations") not in (0, None)
            or record.get("http_request_count", 0) != 0
        ):
            raise ScoringError("Ineligible candidate has a provider attempt")
        if record.get("model_invocations") is None and not slot["eligible"]:
            raise ScoringError(
                "Ineligible candidate cannot have uncertain provider dispatch"
            )
        if (
            not slot["eligible"]
            and record.get("provider_dispatch_uncertain") is not False
        ):
            raise ScoringError(
                "Ineligible candidate cannot have an uncertain provider dispatch"
            )

    attempts_reserved = receipt.get("attempts_reserved")
    maximum_provider_attempts = attempt_policy.get(
        "maximum_provider_attempts_for_selected_cases"
    )
    if (
        type(attempts_reserved) is not int
        or type(maximum_provider_attempts) is not int
        or attempts_reserved > maximum_provider_attempts
    ):
        raise ScoringError("Receipt attempts exceed the approved provider-attempt plan")


def reviewer_disabled_baseline() -> dict[str, Any]:
    """Return the correct interpretation of a reviewer-disabled comparison."""
    return {
        "mode": "reviewer_disabled",
        "semantic_findings": 0,
        "reviewer_calls": 0,
        "precision": None,
        "precision_reason": "No reviewer findings exist to adjudicate; this is not perfect precision.",
    }
