"""Plan, exercise, or score the advisory semantic reviewer on local fixtures.

The plan and dry-run paths are credential-free. ``run --live`` is deliberately
separate, requires an exact plan digest confirmation, and is never invoked by
tests or by this repository's synthetic-contract report.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from langgraph_system_generator.generator.state import (
    ArchitectureFeedback,
    CellSpec,
    Constraint,
    DocSnippet,
    DocsRetrievalFeedback,
    GenerationContextPack,
    GeneratorState,
    GraphDesignFeedback,
    GraphExportBundle,
    NotebookCompositionFeedback,
    NotebookDependencyPlan,
    NotebookPlan,
    QARepairFeedback,
    QAReport,
    RequirementsFeedback,
    ToolPlanningFeedback,
)
from langgraph_system_generator.qa.outcomes import (
    candidate_id,
    derive_generation_outcome,
)
from langgraph_system_generator.qa.registry import get_qa_repair_registry
from langgraph_system_generator.qa.specialist_models import (
    MAX_INPUT_CHARS,
    MAX_OUTPUT_TOKENS,
    REVIEW_TIMEOUT_SECONDS,
    REVIEWER_ID,
    SemanticReviewFeedback,
    SemanticReviewPolicy,
    review_response_format,
)
from langgraph_system_generator.qa.specialist_review import (
    build_review_context,
    review_candidate,
    skipped_review_feedback,
)
from langgraph_system_generator.utils.config import GenerationConfig, settings
from langgraph_system_generator.utils.error_handling import GenerationError
from langgraph_system_generator.utils.llm_endpoint_security import authorize_endpoint
from langgraph_system_generator.utils.model_compatibility import (
    chat_openai_compatibility_kwargs,
)

DEFAULT_DATASET = REPO_ROOT / "tests/evaluation/semantic_quality_v1/cases.json"
DEFAULT_LABELS = (
    REPO_ROOT / "tests/evaluation/semantic_quality_v1/reference_labels.json"
)
DATASET_SCHEMA_VERSION = 1
PLAN_SCHEMA_VERSION = 1
RECEIPT_SCHEMA_VERSION = "semantic-review-receipt-v1"
MAX_CASES = 20
MAX_REPETITIONS = 2
MAX_ATTEMPTS = 40
DEFAULT_REPETITIONS = 2
SYNTHETIC_MODEL_ID = "semantic-review-synthetic-contract"

# Only fields consumed by the real reviewer/context builder may cross this
# boundary. Case IDs, splits, categories, rationales, and candidate references
# remain evaluator metadata and are never copied into GeneratorState.
MODEL_STATE_FIELDS = frozenset(
    {
        "user_prompt",
        "requirements_messages",
        "constraints",
        "requirements_feedback",
        "architecture_feedback",
        "graph_design_feedback",
        "graph_exports",
        "selected_patterns",
        "docs_context",
        "docs_retrieval_feedback",
        "generation_context_pack",
        "notebook_plan",
        "architecture_justification",
        "architecture_type",
        "workflow_design",
        "tools_plan",
        "tool_planning_feedback",
        "notebook_composition_feedback",
        "notebook_dependency_plan",
        "generated_cells",
        "qa_reports",
        "qa_history",
        "repair_attempts",
    }
)

SOURCE_ROOTS = (REPO_ROOT / "src", REPO_ROOT / "scripts")
DEPENDENCY_DISTRIBUTIONS = (
    "httpx",
    "langchain-core",
    "langchain-openai",
    "langgraph",
    "openai",
    "pydantic",
)
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
SHA256_TOKEN = re.compile(r"^[a-f0-9]{64}$")
PROVENANCE_FIELDS = {
    "candidate_identity",
    "candidate_sha256",
    "candidate_origin",
    "context_digest",
    "context_chars",
    "docs_available",
    "fixture_origin",
    "fixture_recipe",
    "generator_revision",
    "original_bytes_sha256",
    "altered_bytes_sha256",
    "candidate_bytes_sha256",
    "mutation_record_id",
}
PROVENANCE_HASH_FIELDS = {
    "candidate_identity",
    "candidate_sha256",
    "context_digest",
    "original_bytes_sha256",
    "altered_bytes_sha256",
    "candidate_bytes_sha256",
}
QUALITY_FILE_SUFFIXES = {".json", ".py", ".ipynb"}


class EvaluationError(ValueError):
    """Expected refusal for invalid or stale local evaluation evidence."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _read_json(path: Path) -> tuple[Any, bytes]:
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8")), raw
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise EvaluationError("Evaluation input is missing or invalid JSON.") from None


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise EvaluationError("Unable to identify the repository revision.") from None
    return result.stdout.strip()


def _source_manifest() -> dict[str, str]:
    manifest: dict[str, str] = {}
    paths: set[Path] = set()
    for root in SOURCE_ROOTS:
        paths.update(path for path in root.rglob("*.py") if path.is_file())
    for path in sorted(paths):
        relpath = path.relative_to(REPO_ROOT).as_posix()
        try:
            manifest[relpath] = _sha256_bytes(path.read_bytes())
        except OSError:
            raise EvaluationError("Unable to hash evaluation source files.") from None
    for name in ("requirements.txt", "setup.py"):
        path = REPO_ROOT / name
        if path.is_file():
            manifest[name] = _sha256_bytes(path.read_bytes())
    quality_root = REPO_ROOT / "tests/evaluation/semantic_quality_v1"
    if quality_root.exists():
        for path in sorted(quality_root.rglob("*")):
            if path.is_file() and path.suffix.lower() in QUALITY_FILE_SUFFIXES:
                manifest[path.relative_to(REPO_ROOT).as_posix()] = _sha256_bytes(
                    path.read_bytes()
                )
    contract_corpus = REPO_ROOT / "tests/evaluation/semantic_review_cases.json"
    if contract_corpus.is_file():
        manifest[contract_corpus.relative_to(REPO_ROOT).as_posix()] = _sha256_bytes(
            contract_corpus.read_bytes()
        )
    return manifest


def _dependency_profile() -> dict[str, Any]:
    versions = {}
    for distribution in DEPENDENCY_DISTRIBUTIONS:
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "missing"
    return {
        "python": sys.version.split()[0],
        "distributions": versions,
        "profile_sha256": _sha256_text(
            _canonical_json(
                {"python": sys.version.split()[0], "distributions": versions}
            )
        ),
    }


def _safe_token(value: Any, *, maximum: int = 120) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= maximum
        and bool(SAFE_TOKEN.fullmatch(value))
        and not value.lower().startswith(("http://", "https://"))
        and not value.lower().startswith(("sk-", "ghp_", "github_pat_"))
    )


def _safe_provenance(value: Any) -> dict[str, Any]:
    """Retain only opaque identifiers, revisions, and content hashes."""
    if not isinstance(value, Mapping):
        return {}
    safe: dict[str, Any] = {}
    for key in sorted(PROVENANCE_FIELDS & set(value)):
        item = value[key]
        if key in PROVENANCE_HASH_FIELDS:
            if isinstance(item, str) and SHA256_TOKEN.fullmatch(item):
                safe[key] = item
        elif key == "context_chars":
            if type(item) is int and item >= 0:
                safe[key] = item
        elif key == "docs_available":
            if type(item) is bool:
                safe[key] = item
        elif _safe_token(item):
            safe[key] = item
    return safe


def _verify_provenance_context(provenance: Any, context: Any) -> None:
    """Reject declared candidate/context digests that disagree with production."""
    if not isinstance(provenance, Mapping):
        return
    expected = {
        "candidate_sha256": context.candidate_id,
        "context_digest": context.context_digest,
        "context_chars": len(context.request_json),
        "docs_available": context.docs_available,
    }
    for key, actual in expected.items():
        if key in provenance:
            declared = provenance[key]
            if type(declared) is not type(actual) or declared != actual:
                raise EvaluationError(
                    "Candidate provenance does not match its context."
                )


def _source_sha256(manifest: Mapping[str, str]) -> str:
    return _sha256_text(_canonical_json(dict(manifest)))


def _safe_repo_path(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise EvaluationError("Dataset and label files must be inside the repository.")
    return resolved.relative_to(REPO_ROOT).as_posix()


def _tracked_and_clean(paths: list[Path]) -> bool:
    """Check local Git state only; this function never fetches or contacts GitHub."""
    relpaths = []
    for path in paths:
        try:
            relpath = path.resolve().relative_to(REPO_ROOT).as_posix()
            subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", relpath],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            return False
        relpaths.append(relpath)
    try:
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                *relpaths,
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not status.stdout.strip()


def _live_pilot_eligibility(
    dataset_path: Path, labels_path: Path, case_count: int, repetitions: int
) -> dict[str, Any]:
    reasons: list[str] = []
    if dataset_path.resolve() != DEFAULT_DATASET.resolve():
        reasons.append("dataset_is_not_versioned_quality_v1")
    if labels_path.resolve() != DEFAULT_LABELS.resolve():
        reasons.append("labels_are_not_versioned_quality_v1")
    if case_count != MAX_CASES or repetitions != MAX_REPETITIONS:
        reasons.append("pilot_requires_20_cases_and_two_repetitions")
    tracked_paths = [
        dataset_path,
        labels_path,
        REPO_ROOT / "requirements.txt",
        REPO_ROOT / "setup.py",
    ]
    tracked_paths.extend(path for root in SOURCE_ROOTS for path in root.rglob("*.py"))
    tracked_paths.extend(
        path
        for path in (REPO_ROOT / "tests/evaluation/semantic_quality_v1").rglob("*")
        if path.is_file() and path.suffix.lower() in QUALITY_FILE_SUFFIXES
    )
    if not _tracked_and_clean(tracked_paths):
        reasons.append("source_and_quality_corpus_must_be_tracked_and_clean")
    return {"eligible": not reasons, "ineligibility_reasons": reasons}


def _load_cases(dataset_bytes: bytes, *, dataset_path: Path) -> tuple[str, list[dict]]:
    try:
        dataset = json.loads(dataset_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise EvaluationError("Dataset is missing or invalid JSON.") from None
    if (
        not isinstance(dataset, dict)
        or dataset.get("schema_version") != DATASET_SCHEMA_VERSION
    ):
        raise EvaluationError("Unsupported semantic-quality dataset schema.")
    dataset_id = dataset.get("dataset_id")
    cases = dataset.get("cases")
    if not _safe_token(dataset_id, maximum=80):
        raise EvaluationError("Dataset identifier is missing.")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise EvaluationError("Dataset must contain between 1 and 20 cases.")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise EvaluationError("Dataset contains an invalid case row.")
        case_id_value = case.get("case_id")
        pair_id = case.get("pair_id")
        split = case.get("split")
        domain = case.get("domain")
        candidate = case.get("candidate")
        if (
            not isinstance(case_id_value, str)
            or not case_id_value
            or not _safe_token(case_id_value, maximum=80)
            or case_id_value in seen
            or not isinstance(split, str)
            or split not in {"development", "holdout", "guardrail"}
            or not isinstance(domain, str)
            or not domain
            or (pair_id is not None and not isinstance(pair_id, str))
            or not isinstance(candidate, dict)
            or not isinstance(candidate.get("model_state"), dict)
            or not _safe_token(candidate.get("candidate_ref"), maximum=80)
            or not _safe_token(domain, maximum=64)
            or (pair_id is not None and not _safe_token(pair_id, maximum=80))
        ):
            raise EvaluationError("Dataset contains an invalid case row.")
        seen.add(case_id_value)
    return cast(str, dataset_id), cast(list[dict[str, Any]], cases)


def _typed_list(
    value: Any, model: type[BaseModel], *, field_name: str
) -> list[BaseModel]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise EvaluationError(f"Invalid {field_name} fixture shape.")
    try:
        return [
            item if isinstance(item, model) else model.model_validate(item)
            for item in value
        ]
    except (ValidationError, TypeError, ValueError):
        raise EvaluationError(f"Invalid {field_name} fixture shape.") from None


def build_typed_state(
    model_state: Mapping[str, Any], generation_config: GenerationConfig
) -> GeneratorState:
    """Create a complete production state from the fixture allowlist."""
    if not isinstance(model_state, Mapping) or set(model_state) - MODEL_STATE_FIELDS:
        raise EvaluationError("Fixture model state has unsupported fields.")
    if not isinstance(model_state.get("user_prompt"), str):
        raise EvaluationError("Fixture model state requires a user prompt.")
    cells = _typed_list(
        model_state.get("generated_cells"), CellSpec, field_name="cells"
    )
    constraints = _typed_list(
        model_state.get("constraints"), Constraint, field_name="constraints"
    )
    docs_context = _typed_list(
        model_state.get("docs_context"), DocSnippet, field_name="docs_context"
    )
    qa_reports = _typed_list(
        model_state.get("qa_reports"), QAReport, field_name="qa_reports"
    )
    qa_history = _typed_list(
        model_state.get("qa_history"), QAReport, field_name="qa_history"
    )
    try:
        requirements_feedback = RequirementsFeedback.model_validate(
            model_state.get("requirements_feedback") or {}
        )
        architecture_feedback = ArchitectureFeedback.model_validate(
            model_state.get("architecture_feedback") or {}
        )
        graph_design_feedback = GraphDesignFeedback.model_validate(
            model_state.get("graph_design_feedback") or {}
        )
        graph_exports = GraphExportBundle.model_validate(
            model_state.get("graph_exports") or {}
        )
        docs_retrieval_feedback = DocsRetrievalFeedback.model_validate(
            model_state.get("docs_retrieval_feedback") or {}
        )
        generation_context_pack = GenerationContextPack.model_validate(
            model_state.get("generation_context_pack") or {}
        )
        notebook_plan = (
            NotebookPlan.model_validate(model_state["notebook_plan"])
            if model_state.get("notebook_plan") is not None
            else None
        )
        tool_planning_feedback = ToolPlanningFeedback.model_validate(
            model_state.get("tool_planning_feedback") or {}
        )
        notebook_composition_feedback = NotebookCompositionFeedback.model_validate(
            model_state.get("notebook_composition_feedback") or {}
        )
        notebook_dependency_plan = NotebookDependencyPlan.model_validate(
            model_state.get("notebook_dependency_plan") or {}
        )
        qa_repair_feedback = QARepairFeedback()
        attempt = int(model_state.get("repair_attempts", 0))
    except (ValidationError, TypeError, ValueError, KeyError):
        raise EvaluationError(
            "Fixture model state does not match production types."
        ) from None
    if attempt < 0:
        raise EvaluationError("Fixture repair attempt must be non-negative.")
    outcome = derive_generation_outcome(
        qa_reports,
        candidate_sha256=candidate_id(cells),
        pipeline="unknown",
        has_cells=bool(cells),
        repair_attempts=attempt,
        max_repair_attempts=0,
    )
    state: dict[str, Any] = {
        "user_prompt": model_state["user_prompt"],
        "requirements_messages": model_state.get("requirements_messages"),
        "uploaded_files": [],
        "constraints": constraints,
        "requirements_feedback": requirements_feedback,
        "architecture_feedback": architecture_feedback,
        "graph_design_feedback": graph_design_feedback,
        "graph_exports": graph_exports,
        "selected_patterns": model_state.get("selected_patterns") or {},
        "docs_context": docs_context,
        "docs_retrieval_feedback": docs_retrieval_feedback,
        "generation_context_pack": generation_context_pack,
        "notebook_plan": notebook_plan,
        "architecture_justification": model_state.get("architecture_justification")
        or "",
        "architecture_type": model_state.get("architecture_type"),
        "generation_config": generation_config,
        # Production review_candidate skips stub generations. These are prepared
        # candidate snapshots, not a generator run; no generation is performed.
        "generation_mode": "live",
        "workflow_design": model_state.get("workflow_design"),
        "tools_plan": model_state.get("tools_plan"),
        "tool_planning_feedback": tool_planning_feedback,
        "notebook_composition_feedback": notebook_composition_feedback,
        "notebook_dependency_plan": notebook_dependency_plan,
        "generated_cells": cells,
        "qa_reports": qa_reports,
        "qa_history": qa_history,
        "repair_attempts": attempt,
        "qa_repair_feedback": qa_repair_feedback,
        "qa_summary": {},
        "semantic_review_policy": SemanticReviewPolicy(
            mode="advisory", plugin_modules=()
        ),
        "generation_outcome": outcome,
        "artifacts_manifest": {},
        "generation_complete": False,
        "error_message": None,
    }
    return state  # type: ignore[return-value]


def _endpoint_binding(config: GenerationConfig, effective_policy: str | None = None):
    policy = effective_policy or config.endpoint_policy
    try:
        return authorize_endpoint(config.api_base, policy)  # no credential lookup
    except (GenerationError, TypeError, ValueError):
        raise EvaluationError(
            "Selected endpoint configuration is not authorized."
        ) from None


def _registered_reviewer(config: GenerationConfig):
    """Resolve the built-in reviewer through production registry and factory."""
    try:
        registration = get_qa_repair_registry(()).specialist_reviewer(REVIEWER_ID)
        reviewer = registration.factory(config.to_model_config(settings.default_model))
        instructions = reviewer.instructions
    except Exception:  # noqa: BLE001 - plugin/factory errors can contain secrets
        raise EvaluationError(
            "The registered semantic reviewer is unavailable."
        ) from None
    if not isinstance(instructions, str) or not instructions:
        raise EvaluationError("The registered semantic reviewer has no instructions.")
    return registration, instructions


def _config_payload(config: GenerationConfig) -> dict[str, Any]:
    binding = _endpoint_binding(config)
    effective_cap = min(config.max_tokens or MAX_OUTPUT_TOKENS, MAX_OUTPUT_TOKENS)
    model = config.model or settings.default_model
    compatibility = chat_openai_compatibility_kwargs(model, api_base=binding.base_url)
    is_responses_profile = bool(compatibility.get("use_responses_api"))
    return {
        "model": model,
        # Luna's production adapter omits temperature and uses the fixed low
        # reasoning Responses profile; other models use deterministic temp=0.
        "temperature": (
            None
            if is_responses_profile
            else 0.0 if config.temperature is None else config.temperature
        ),
        "response_api": "responses" if is_responses_profile else "chat_completions",
        "reasoning_profile": compatibility.get("reasoning"),
        "output_version": compatibility.get("output_version"),
        "requested_endpoint_policy": config.endpoint_policy,
        "effective_endpoint_policy": binding.policy,
        "provider_id": binding.provider_id,
        "endpoint_sha256": _sha256_text(binding.base_url),
        "requested_output_cap": config.max_tokens,
        "effective_output_cap": effective_cap,
        "input_limit_chars": MAX_INPUT_CHARS,
        "timeout_seconds": REVIEW_TIMEOUT_SECONDS,
        "max_retries": 0,
        "concurrency": 1,
    }


def _new_generation_config(
    model: str | None,
    endpoint_policy: str | None,
    api_base: str | None,
    output_cap: int | None,
) -> GenerationConfig:
    requested_policy = endpoint_policy or settings.lnf_llm_endpoint_policy
    chosen_model = model or settings.default_model
    if not _safe_token(chosen_model):
        raise EvaluationError("Model identifier contains unsupported characters.")
    try:
        return GenerationConfig(
            model=model or settings.default_model,
            temperature=None,
            max_tokens=output_cap,
            endpoint_policy=requested_policy,
            api_base=api_base,
        )
    except (ValidationError, TypeError, ValueError):
        raise EvaluationError("Invalid model or generation configuration.") from None


def _case_preflight(
    case: Mapping[str, Any], config: GenerationConfig
) -> dict[str, Any]:
    """Build exact production context without constructing a model client."""
    raw_candidate = case.get("candidate")
    candidate: Mapping[str, Any] = (
        raw_candidate if isinstance(raw_candidate, Mapping) else {}
    )
    try:
        _registration, instructions = _registered_reviewer(config)
        state = build_typed_state(candidate["model_state"], config)
        context = build_review_context(state, instructions=instructions)
        _verify_provenance_context(candidate.get("provenance"), context)
        skipped = skipped_review_feedback(state)
    except Exception:  # noqa: BLE001 - fixture and context errors may include prompts
        return {
            "case_id": case["case_id"],
            "pair_id": case.get("pair_id"),
            "split": case["split"],
            "domain": case["domain"],
            "candidate_ref": candidate.get("candidate_ref"),
            "provenance": _safe_provenance(candidate.get("provenance")),
            "candidate_sha256": None,
            "context_sha256": None,
            "context_chars": 0,
            "docs_available": False,
            "eligible": False,
            "preflight_status": "invalid_reference",
            "preflight_reason_code": "invalid_reference",
            "baseline": {"eligible": False, "blocking_rule_ids": []},
        }
    status: str | None = None
    reason_code: str | None = None
    if skipped is not None:
        status, reason_code = "skipped", skipped.reason_code
    elif len(context.request_json) > MAX_INPUT_CHARS:
        status, reason_code = "input_limit", "input_limit"
    blocking_rule_ids = sorted(
        {
            report.rule_id
            for report in state["qa_reports"]
            if not report.passed and report.severity == "error"
        }
    )
    return {
        "case_id": case["case_id"],
        "pair_id": case.get("pair_id"),
        "split": case["split"],
        "domain": case["domain"],
        "candidate_ref": candidate.get("candidate_ref"),
        "provenance": _safe_provenance(candidate.get("provenance")),
        "candidate_sha256": context.candidate_id,
        "context_sha256": context.context_digest,
        "context_chars": len(context.request_json),
        "docs_available": context.docs_available,
        "eligible": status is None,
        "preflight_status": status,
        "preflight_reason_code": reason_code,
        "baseline": {
            # This describes deterministic QA only. Reviewer input eligibility
            # (for example, the 48k context cap) is reported separately above.
            "eligible": not blocking_rule_ids,
            "blocking_rule_ids": blocking_rule_ids,
        },
    }


def _plan_body(
    *,
    dataset_path: Path,
    labels_path: Path,
    config: GenerationConfig,
    repetitions: int,
) -> dict[str, Any]:
    if not 1 <= repetitions <= MAX_REPETITIONS:
        raise EvaluationError("Repetitions must be between 1 and 2.")
    dataset_raw = dataset_path.read_bytes()
    labels_raw = labels_path.read_bytes()
    dataset_id, cases = _load_cases(dataset_raw, dataset_path=dataset_path)
    if not _safe_repo_path(dataset_path) or not _safe_repo_path(labels_path):
        raise EvaluationError("Evaluation inputs must be repository-controlled.")
    preflight = [
        _case_preflight(case, config)
        for case in sorted(cases, key=lambda x: x["case_id"])
    ]
    source_manifest = _source_manifest()
    source_sha = _source_sha256(source_manifest)
    dependencies = _dependency_profile()
    config_data = _config_payload(config)
    config_data["repetitions"] = repetitions
    registration, instructions = _registered_reviewer(config)
    pilot = _live_pilot_eligibility(
        dataset_path, labels_path, len(preflight), repetitions
    )
    eligible = sum(1 for item in preflight if item["eligible"])
    maximum_provider_attempts = min(MAX_ATTEMPTS, eligible * repetitions)
    body = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_kind": "semantic-review-live-pilot",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": _git("rev-parse", "HEAD"),
        "source_sha256": source_sha,
        "source_files_sha256": source_manifest,
        "dependency_profile": dependencies,
        "response_schema_sha256": _sha256_text(
            _canonical_json(review_response_format())
        ),
        "reviewer_id": REVIEWER_ID,
        "reviewer_version": registration.version,
        "reviewer_prompt_sha256": _sha256_text(instructions),
        "dataset": {
            "id": dataset_id,
            "path": _safe_repo_path(dataset_path),
            "sha256": _sha256_bytes(dataset_raw),
            "case_count": len(preflight),
            "selected_case_ids": [item["case_id"] for item in preflight],
            "selected_opaque_case_slots": [
                {"slot": f"case-{index + 1:02d}", "case_id": item["case_id"]}
                for index, item in enumerate(preflight)
            ],
        },
        "labels": {
            "path": _safe_repo_path(labels_path),
            "sha256": _sha256_bytes(labels_raw),
        },
        "effective_config": config_data,
        "repetitions": repetitions,
        "live_pilot_eligibility": pilot,
        "attempt_policy": {
            "maximum_attempts": MAX_ATTEMPTS,
            "maximum_provider_attempts_for_selected_cases": maximum_provider_attempts,
            "one_at_a_time": True,
            "automatic_retries": 0,
            "automatic_model_switches": 0,
            "automatic_resume": False,
        },
        "selected_cases": preflight,
        "evidence_kind": "synthetic-contract-only-until-separately-authorized-live-run",
    }
    body["plan_sha256"] = _sha256_text(_canonical_json(body))
    return body


def _verify_plan_hash(plan: Mapping[str, Any]) -> str:
    if not isinstance(plan, Mapping):
        raise EvaluationError("Plan is invalid.")
    expected = plan.get("plan_sha256")
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    actual = _sha256_text(_canonical_json(body))
    if not isinstance(expected, str) or expected != actual:
        raise EvaluationError("Plan digest does not match its contents.")
    return actual


def validate_plan(
    plan_path: Path, *, api_base: str | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]], GenerationConfig]:
    """Reject stale source, dataset, labels, prompt, or effective configuration."""
    plan, _ = _read_json(plan_path)
    _verify_plan_hash(plan)
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise EvaluationError("Unsupported plan schema.")
    dataset_path = (REPO_ROOT / plan["dataset"]["path"]).resolve()
    labels_path = (REPO_ROOT / plan["labels"]["path"]).resolve()
    dataset_raw = dataset_path.read_bytes()
    labels_raw = labels_path.read_bytes()
    dataset_id, cases = _load_cases(dataset_raw, dataset_path=dataset_path)
    if _sha256_bytes(dataset_raw) != plan["dataset"]["sha256"]:
        raise EvaluationError("Dataset changed after plan approval.")
    if _sha256_bytes(labels_raw) != plan["labels"]["sha256"]:
        raise EvaluationError("Reference labels changed after plan approval.")
    if dataset_id != plan["dataset"]["id"]:
        raise EvaluationError("Dataset identity changed after plan approval.")
    if _git("rev-parse", "HEAD") != plan["source_revision"]:
        raise EvaluationError("Source revision changed after plan approval.")
    source_manifest = _source_manifest()
    if (
        source_manifest != plan["source_files_sha256"]
        or _source_sha256(source_manifest) != plan["source_sha256"]
    ):
        raise EvaluationError("Runner or reviewer source changed after plan approval.")
    if _dependency_profile() != plan["dependency_profile"]:
        raise EvaluationError(
            "Installed dependency profile changed after plan approval."
        )
    if (
        _sha256_text(_canonical_json(review_response_format()))
        != plan["response_schema_sha256"]
    ):
        raise EvaluationError("Reviewer response schema changed after plan approval.")
    config_data = plan["effective_config"]
    config = GenerationConfig(
        model=config_data["model"],
        temperature=None,
        max_tokens=config_data["requested_output_cap"],
        endpoint_policy=config_data["requested_endpoint_policy"],
        api_base=api_base,
    )
    registration, instructions = _registered_reviewer(config)
    if (
        registration.version != plan.get("reviewer_version")
        or _sha256_text(instructions) != plan["reviewer_prompt_sha256"]
    ):
        raise EvaluationError("Reviewer prompt changed after plan approval.")
    comparable_config = _config_payload(config)
    comparable_config["repetitions"] = plan["repetitions"]
    if comparable_config != config_data:
        raise EvaluationError(
            "Effective model or endpoint policy changed after planning."
        )
    expected_cases = [
        _case_preflight(case, config)
        for case in sorted(cases, key=lambda x: x["case_id"])
    ]
    if expected_cases != plan["selected_cases"]:
        raise EvaluationError(
            "Candidate context or eligibility changed after planning."
        )
    pilot = _live_pilot_eligibility(
        dataset_path, labels_path, len(expected_cases), plan["repetitions"]
    )
    if pilot != plan["live_pilot_eligibility"]:
        raise EvaluationError("Live pilot source eligibility changed after planning.")
    return plan, expected_cases, config


def _write_new_bytes(path: Path, data: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".semantic-review-", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard-link creates the final name atomically and refuses overwrite.
        os.link(temp_path, path)
    except FileExistsError:
        raise EvaluationError(
            "Refusing to overwrite an existing evidence file."
        ) from None
    except OSError:
        raise EvaluationError("Unable to persist evaluation evidence.") from None
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    data = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _write_new_bytes(path, data)


def _plan_markdown(plan: Mapping[str, Any]) -> str:
    config = plan["effective_config"]
    lines = [
        "# Semantic reviewer pilot plan",
        "",
        "This is a reviewable plan only. Planning makes zero provider requests.",
        "Synthetic contract responses do not establish live model accuracy.",
        "",
        f"- Plan SHA-256: `{plan['plan_sha256']}`",
        f"- Dataset: `{plan['dataset']['id']}` ({plan['dataset']['case_count']} cases)",
        f"- Dataset SHA-256: `{plan['dataset']['sha256']}`",
        f"- Reference labels SHA-256: `{plan['labels']['sha256']}`",
        f"- Source revision: `{plan['source_revision']}`",
        f"- Source SHA-256: `{plan['source_sha256']}`",
        f"- Reviewer prompt SHA-256: `{plan['reviewer_prompt_sha256']}`",
        f"- Reviewer version: `{plan['reviewer_version']}`",
        f"- Response schema SHA-256: `{plan['response_schema_sha256']}`",
        f"- Model: `{config['model']}`",
        f"- Provider: `{config['provider_id']}`",
        f"- Endpoint policy: `{config['effective_endpoint_policy']}`",
        f"- Endpoint fingerprint: `{config['endpoint_sha256']}`",
        f"- Output cap: `{config['effective_output_cap']}` tokens",
        f"- Repetitions: `{plan['repetitions']}`",
        f"- Maximum reviewer attempts: `{plan['attempt_policy']['maximum_attempts']}`",
        f"- Maximum eligible attempts for this selection: `{plan['attempt_policy']['maximum_provider_attempts_for_selected_cases']}`",
        f"- Live-pilot eligible: `{str(plan['live_pilot_eligibility']['eligible']).lower()}`",
        "",
        "## Selected opaque cases",
        "",
        "| Slot | Case ID | Split | Domain | Context characters | Planned calls | Eligibility |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for slot, case in zip(
        plan["dataset"]["selected_opaque_case_slots"], plan["selected_cases"]
    ):
        calls = plan["repetitions"] if case["eligible"] else 0
        eligible = "eligible" if case["eligible"] else case["preflight_status"]
        lines.append(
            f"| {slot['slot']} | `{case['case_id']}` | {case['split']} | {case['domain']} | "
            f"{case['context_chars']} | {calls} | {eligible} |"
        )
    reasons = plan["live_pilot_eligibility"]["ineligibility_reasons"]
    if reasons:
        lines.extend(
            [
                "",
                "Live-pilot eligibility findings: "
                + ", ".join(f"`{x}`" for x in reasons)
                + ".",
            ]
        )
    lines.extend(
        [
            "",
            (
                "A future live run requires explicit `--live`, exact digest confirmation, "
                "and an unused local claim for this plan. No automatic retry or resume is allowed."
            ),
            "",
        ]
    )
    return "\n".join(lines)


class _Journal:
    def __init__(self, path: Path):
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._stream = path.open("x", encoding="utf-8", newline="\n")
        except FileExistsError:
            raise EvaluationError(
                "Refusing to resume or overwrite an attempt journal."
            ) from None
        except OSError:
            raise EvaluationError(
                "Unable to create the local attempt journal."
            ) from None

    def append(self, item: Mapping[str, Any]) -> None:
        self._stream.write(_canonical_json(item) + "\n")
        self._stream.flush()
        os.fsync(self._stream.fileno())

    def close(self) -> None:
        self._stream.close()


def _synthetic_http_response(request: httpx.Request) -> httpx.Response:
    """Return a synthetic, exact-evidence finding without using evaluator labels."""
    content = _synthetic_review_content(request)
    if request.url.path.endswith("/responses"):
        payload = {
            "id": "resp_semantic_review_contract",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "model": SYNTHETIC_MODEL_ID,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "output": [
                {
                    "id": "msg_semantic_review_contract",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": content, "annotations": []}
                    ],
                }
            ],
            "metadata": {},
        }
        return httpx.Response(200, json=payload)
    payload = {
        "id": "chatcmpl-semantic-review-contract",
        "object": "chat.completion",
        "created": 0,
        "model": SYNTHETIC_MODEL_ID,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                },
            }
        ],
    }
    return httpx.Response(200, json=payload)


def _synthetic_review_content(request: httpx.Request) -> str:
    output: dict[str, Any] = {"assessment": "complete", "findings": []}
    try:
        body = json.loads(request.content.decode("utf-8"))

        def strings(value: Any) -> Iterator[str]:
            if isinstance(value, str):
                yield value
            elif isinstance(value, Mapping):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)

        prefix = "UNTRUSTED_REVIEW_DATA_JSON\n"
        serialized = next(
            (item[len(prefix) :] for item in strings(body) if item.startswith(prefix)),
            None,
        )
        review_data = json.loads(serialized) if serialized is not None else {}
        sources = review_data.get("sources") or []
        prompt_source = next(
            (
                source
                for source in sources
                if source.get("source_id") == "request:prompt"
            ),
            None,
        )
        structured_requirements = [
            source
            for source in sources
            if str(source.get("source_id", "")).startswith("requirement:")
        ]
        if (
            prompt_source
            and not structured_requirements
            and len(str(prompt_source.get("text", "")).split()) <= 12
        ):
            # Exercise the production abstention path from visible context shape
            # alone; no dataset identity or evaluator label is consulted.
            output["assessment"] = "insufficient_context"
            return json.dumps(output, separators=(",", ":"))
        requirement = next(
            (
                source
                for source in sources
                if source.get("family") == "requirement" and source.get("text")
            ),
            None,
        )
        candidate = next(
            (
                source
                for source in sources
                if source.get("family") == "cell" and source.get("text")
            ),
            None,
        )
        if requirement and candidate:
            refs = []
            for source in (requirement, candidate):
                quote = source["text"][: min(80, len(source["text"]))]
                refs.append(
                    {
                        "source_id": source["source_id"],
                        "start": 0,
                        "end": len(quote),
                        "quote": quote,
                    }
                )
            output["findings"] = [
                {
                    "category": "requirements_gap",
                    "message": "Synthetic contract evidence admission check.",
                    "suggestions": [],
                    "references": refs,
                }
            ]
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        AttributeError,
        KeyError,
        IndexError,
    ):
        # The fixed empty answer still proves the configured response parser.
        pass
    return json.dumps(output, separators=(",", ":"))


@contextmanager
def _synthetic_transport(
    config: GenerationConfig,
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> Iterator[list[httpx.Request]]:
    """Patch only the existing SDK HTTP transport seam for one serial trial."""
    from langgraph_system_generator.generator.agents import _llm

    captured: list[httpx.Request] = []
    responder = handler or _synthetic_http_response

    def dispatch(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return responder(request)

    real_sync, real_async = httpx.Client, httpx.AsyncClient

    def fake_sync(**kwargs: Any) -> httpx.Client:
        return real_sync(**kwargs, transport=httpx.MockTransport(dispatch))

    def fake_async(**kwargs: Any) -> httpx.AsyncClient:
        return real_async(**kwargs, transport=httpx.MockTransport(dispatch))

    binding = _endpoint_binding(config)
    # Credentials are synthetic in this scope; there is no network transport.
    env_patch = {binding.api_key_env: "synthetic-contract-credential"}
    if binding.provider_id == "local-custom":
        env_patch["LNF_CUSTOM_LLM_NO_AUTH"] = "false"
    with patch.dict(os.environ, env_patch), patch.object(
        _llm, "Client", fake_sync
    ), patch.object(_llm, "AsyncClient", fake_async):
        yield captured


def _case_status(feedback: SemanticReviewFeedback | None) -> tuple[str, str]:
    if feedback is None:
        return "unavailable", "reviewer_unavailable"
    if feedback.status == "reviewed":
        return "reviewed", feedback.reason_code
    if feedback.status == "skipped":
        return "skipped", feedback.reason_code
    if feedback.status == "unavailable":
        return "unavailable", feedback.reason_code
    if feedback.status == "invalid_response":
        return (
            (
                "invalid_reference"
                if feedback.reason_code == "invalid_reference"
                else "invalid_response"
            ),
            feedback.reason_code,
        )
    if feedback.reason_code == "input_limit":
        return "input_limit", feedback.reason_code
    if feedback.reason_code == "output_limit":
        return "output_limit", feedback.reason_code
    if feedback.reason_code == "insufficient_context":
        return "insufficient_context", feedback.reason_code
    if feedback.reason_code == "off":
        return "skipped", feedback.reason_code
    return "invalid_response", feedback.reason_code


def _record_base(
    planned: Mapping[str, Any],
    repetition: int,
    *,
    requested_model: str,
    evidence_kind: str,
) -> dict[str, Any]:
    return {
        "case_id": planned["case_id"],
        "pair_id": planned.get("pair_id"),
        "split": planned["split"],
        "domain": planned["domain"],
        "candidate_ref": planned.get("candidate_ref"),
        "repetition": repetition,
        "evidence_kind": evidence_kind,
        "case_status": "skipped",
        "reason_code": "not_attempted",
        "rejection_detail": None,
        "attempt_reserved": False,
        "provider_dispatch_uncertain": False,
        "model_invocations": 0,
        "http_request_count": 0,
        "candidate_sha256": planned["candidate_sha256"],
        "context_sha256": planned["context_sha256"],
        "context_chars": planned["context_chars"],
        "docs_available": planned["docs_available"],
        "latency_ms": None,
        "requested_model": requested_model,
        "reported_model": None,
        "reported_usage": "unknown",
        "reviewer_version": None,
        "safe_findings": [],
        "baseline": planned["baseline"],
        "provenance": planned.get("provenance") or {},
        "annotation_refs": [],
    }


def _feedback_record(
    planned: Mapping[str, Any],
    repetition: int,
    *,
    requested_model: str,
    feedback: SemanticReviewFeedback | None,
    elapsed_ms: float,
    evidence_kind: str,
    attempted: bool,
    http_request_count: int,
    reported_model: str | None,
    reported_usage: Mapping[str, int] | None,
) -> dict[str, Any]:
    status, reason = _case_status(feedback)
    record = _record_base(
        planned,
        repetition,
        requested_model=requested_model,
        evidence_kind=evidence_kind,
    )
    record.update(
        {
            "case_status": status,
            "reason_code": reason,
            "rejection_detail": feedback.rejection_detail,
            "attempt_reserved": attempted,
            "model_invocations": feedback.model_invocations if feedback else 0,
            "http_request_count": http_request_count,
            "latency_ms": round(elapsed_ms, 3),
            "reviewer_version": feedback.reviewer_version if feedback else None,
            "safe_findings": (
                [item.model_dump(mode="json") for item in feedback.findings]
                if feedback
                else []
            ),
        }
    )
    if evidence_kind == "synthetic-contract":
        record["reported_model"] = SYNTHETIC_MODEL_ID
    elif _safe_token(reported_model):
        record["reported_model"] = reported_model
    if reported_usage:
        record["reported_usage"] = dict(reported_usage)
    return record


def _safe_model_observation(message: Any) -> tuple[str | None, dict[str, int] | None]:
    """Extract only allowlisted scalar metadata; discard message text and extras."""
    metadata = getattr(message, "response_metadata", None)
    reported_model = None
    if isinstance(metadata, Mapping):
        candidate = metadata.get("model_name") or metadata.get("model")
        if _safe_token(candidate):
            reported_model = candidate
    raw_usage = getattr(message, "usage_metadata", None)
    usage = None
    if isinstance(raw_usage, Mapping):
        selected = {
            field: raw_usage[field]
            for field in ("input_tokens", "output_tokens", "total_tokens")
            if type(raw_usage.get(field)) is int and raw_usage[field] >= 0
        }
        if selected:
            usage = selected
    return reported_model, usage


@contextmanager
def _observe_live_http_requests() -> Iterator[dict[str, Any]]:
    """Count dispatches and retain only safe scalar model metadata."""
    from langgraph_system_generator.generator.agents import _llm, requirements_reviewer

    observation: dict[str, Any] = {
        "requests": 0,
        "reported_model": None,
        "usage": None,
    }
    real_async_client = _llm.AsyncClient
    base_chat_openai = requirements_reviewer.ChatOpenAI  # type: ignore[attr-defined]

    class ObservedChatOpenAI(base_chat_openai):  # type: ignore[valid-type,misc]
        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            message = await super().ainvoke(*args, **kwargs)
            model_id, usage = _safe_model_observation(message)
            if model_id:
                observation["reported_model"] = model_id
            if usage:
                observation["usage"] = usage
            return message

    def observed_client(**kwargs: Any) -> httpx.AsyncClient:
        hooks = {
            key: list(value) for key, value in (kwargs.get("event_hooks") or {}).items()
        }

        async def count_request(_request: httpx.Request) -> None:
            observation["requests"] += 1

        hooks.setdefault("request", []).append(count_request)
        kwargs["event_hooks"] = hooks
        return real_async_client(**kwargs)

    with patch.object(_llm, "AsyncClient", observed_client), patch.object(
        requirements_reviewer, "ChatOpenAI", ObservedChatOpenAI
    ):
        yield observation


async def _execute_trials(
    *,
    plan: Mapping[str, Any],
    planned_cases: list[dict[str, Any]],
    config: GenerationConfig,
    receipt_path: Path,
    evidence_kind: str,
    cases_by_id: Mapping[str, Mapping[str, Any]],
    live_claim: Mapping[str, Any] | None = None,
    synthetic_response: Callable[[httpx.Request], httpx.Response] | None = None,
) -> dict[str, Any]:
    plan_digest = plan["plan_sha256"]
    journal_path = receipt_path.with_suffix(receipt_path.suffix + ".journal.jsonl")
    journal = _Journal(journal_path)
    records: list[dict[str, Any]] = []
    attempts_reserved = 0
    stop_status: str | None = None
    request_handler = synthetic_response or _synthetic_http_response
    config_data = plan["effective_config"]
    try:
        scheduled = [
            {"case_id": case["case_id"], "repetition": repetition}
            for case in planned_cases
            for repetition in range(1, plan["repetitions"] + 1)
        ]
        journal.append(
            {
                "event": "run_header",
                "plan_sha256": plan_digest,
                "evidence_kind": evidence_kind,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "scheduled_trials": scheduled,
                "maximum_attempts": MAX_ATTEMPTS,
                "concurrency": 1,
            }
        )
        if evidence_kind == "live":
            # This checks authorization and credential presence without sending
            # a request. The credential value is never retained or reported.
            binding = _endpoint_binding(config)
            try:
                binding.credential()
            except GenerationError:
                stop_status = "provider_credentials_unavailable"
        for planned in planned_cases:
            for repetition in range(1, plan["repetitions"] + 1):
                record = _record_base(
                    planned,
                    repetition,
                    requested_model=config_data["model"],
                    evidence_kind=evidence_kind,
                )
                if stop_status:
                    record.update(
                        {
                            "case_status": (
                                "cancellation"
                                if stop_status == "cancellation"
                                else "unavailable"
                            ),
                            "reason_code": stop_status,
                        }
                    )
                    records.append(record)
                    journal.append({"event": "final", **record})
                    continue
                if not planned["eligible"]:
                    record.update(
                        {
                            "case_status": planned["preflight_status"],
                            "reason_code": planned["preflight_reason_code"],
                        }
                    )
                    if record["case_status"] == "invalid_reference":
                        record["rejection_detail"] = "preflight_invalid_reference"
                    records.append(record)
                    journal.append({"event": "final", **record})
                    continue
                if attempts_reserved >= MAX_ATTEMPTS:
                    record.update(
                        {"case_status": "skipped", "reason_code": "attempt_ceiling"}
                    )
                    records.append(record)
                    journal.append({"event": "final", **record})
                    continue
                attempts_reserved += 1
                reservation = {
                    "event": "reservation",
                    "plan_sha256": plan_digest,
                    "attempt_number": attempts_reserved,
                    "case_id": planned["case_id"],
                    "repetition": repetition,
                    "reserved_at": datetime.now(timezone.utc).isoformat(),
                    "timeout_seconds": REVIEW_TIMEOUT_SECONDS,
                    "requested_model": config_data["model"],
                    "evidence_kind": evidence_kind,
                }
                journal.append(reservation)
                started = time.monotonic()
                request_count = 0
                fake_requests: list[httpx.Request] | None = None
                live_request_count: dict[str, Any] | None = None
                try:
                    state = build_typed_state(
                        cases_by_id[planned["case_id"]]["candidate"]["model_state"],
                        config,
                    )
                    if evidence_kind == "synthetic-contract":
                        with _synthetic_transport(
                            config, request_handler
                        ) as fake_requests:
                            feedback = await review_candidate(state)
                    else:
                        with _observe_live_http_requests() as live_request_count:
                            feedback = await review_candidate(state)
                    request_count = (
                        len(fake_requests)
                        if fake_requests is not None
                        else (live_request_count or {}).get("requests", 0)
                    )
                    elapsed_ms = (time.monotonic() - started) * 1000
                    record = _feedback_record(
                        planned,
                        repetition,
                        requested_model=config_data["model"],
                        feedback=feedback,
                        elapsed_ms=elapsed_ms,
                        evidence_kind=evidence_kind,
                        attempted=True,
                        http_request_count=request_count,
                        reported_model=(live_request_count or {}).get("reported_model"),
                        reported_usage=(live_request_count or {}).get("usage"),
                    )
                    record["evidence_kind"] = evidence_kind
                    # Provider model and usage are not returned by the safe
                    # production review API, so live values remain unknown.
                    if evidence_kind == "synthetic-contract":
                        record["reported_model"] = SYNTHETIC_MODEL_ID
                    records.append(record)
                    journal.append({"event": "final", **record})
                    if record["case_status"] == "unavailable":
                        stop_status = "stopped_after_provider_unavailable"
                except asyncio.CancelledError:
                    elapsed_ms = (time.monotonic() - started) * 1000
                    request_count = (
                        len(fake_requests)
                        if fake_requests is not None
                        else (live_request_count or {}).get("requests", 0)
                    )
                    record.update(
                        {
                            "case_status": "cancellation",
                            "reason_code": "cancelled_request_outcome_uncertain",
                            "attempt_reserved": True,
                            "provider_dispatch_uncertain": True,
                            "model_invocations": 1 if request_count else None,
                            "http_request_count": request_count,
                            "reported_model": (live_request_count or {}).get(
                                "reported_model"
                            ),
                            "reported_usage": (live_request_count or {}).get("usage")
                            or "unknown",
                            "latency_ms": round(elapsed_ms, 3),
                        }
                    )
                    records.append(record)
                    journal.append({"event": "final", **record})
                    stop_status = "cancellation"
                except Exception:  # noqa: BLE001 - failures may carry private payloads
                    elapsed_ms = (time.monotonic() - started) * 1000
                    request_count = (
                        len(fake_requests)
                        if fake_requests is not None
                        else (live_request_count or {}).get("requests", 0)
                    )
                    record.update(
                        {
                            "case_status": "unavailable",
                            "reason_code": "runner_failure_outcome_uncertain",
                            "attempt_reserved": True,
                            "provider_dispatch_uncertain": True,
                            "model_invocations": 1 if request_count else None,
                            "http_request_count": request_count,
                            "reported_model": (live_request_count or {}).get(
                                "reported_model"
                            ),
                            "reported_usage": (live_request_count or {}).get("usage")
                            or "unknown",
                            "latency_ms": round(elapsed_ms, 3),
                        }
                    )
                    records.append(record)
                    journal.append({"event": "final", **record})
                    stop_status = "stopped_after_runner_failure"
        report = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "run_id": str(uuid4()),
            "evidence_kind": evidence_kind,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "plan_sha256": plan_digest,
            "dataset": plan["dataset"],
            "labels": plan["labels"],
            "selected_cases": scheduled,
            "sources": {
                "source_revision": plan["source_revision"],
                "source_sha256": plan["source_sha256"],
                "reviewer_prompt_sha256": plan["reviewer_prompt_sha256"],
                "response_schema_sha256": plan["response_schema_sha256"],
                "dependency_profile_sha256": plan["dependency_profile"][
                    "profile_sha256"
                ],
            },
            "effective_config": config_data,
            "attempts_reserved": attempts_reserved,
            "attempt_ceiling": MAX_ATTEMPTS,
            "latency_sample_count": sum(
                record["latency_ms"] is not None for record in records
            ),
            "usage": "unknown",
            "stop_reason": stop_status,
            "annotation_refs": [],
            "live_claim": live_claim,
            "records": records,
            "journal_path": journal_path.name,
            "limitations": [
                "Advisory detection only; this reviewer does not repair candidate output.",
                "Synthetic contract responses are not model accuracy evidence.",
                "Small local fixture results do not support broad accuracy claims.",
            ],
        }
        return report
    finally:
        journal.close()


def _claim_live_plan(plan_digest: str) -> dict[str, str]:
    claim = {
        "plan_sha256": plan_digest,
        "claim_id": str(uuid4()),
        "claimed_at": datetime.now(timezone.utc).isoformat(),
    }
    common_dir = Path(_git("rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = REPO_ROOT / common_dir
    claim_path = (
        common_dir.resolve()
        / "codex-semantic-review-live-claims"
        / f"{plan_digest}.json"
    )
    try:
        _write_new_json(claim_path, claim)
    except EvaluationError:
        raise EvaluationError(
            "This reviewed plan already has a live-use claim."
        ) from None
    return claim


def run_plan(
    plan_path: Path,
    output_path: Path,
    *,
    dry_run: bool,
    api_base: str | None = None,
    confirm_plan: str | None = None,
) -> dict[str, Any]:
    plan, planned_cases, config = validate_plan(plan_path, api_base=api_base)
    if not dry_run and not plan["live_pilot_eligibility"]["eligible"]:
        raise EvaluationError("Plan is not eligible for the bounded live pilot.")
    if not dry_run and confirm_plan != plan["plan_sha256"]:
        raise EvaluationError("Live run confirmation must match the exact plan digest.")
    dataset_path = REPO_ROOT / plan["dataset"]["path"]
    dataset_raw = dataset_path.read_bytes()
    if _sha256_bytes(dataset_raw) != plan["dataset"]["sha256"]:
        raise EvaluationError("Dataset changed after plan validation.")
    cases_by_id = {
        case["case_id"]: case
        for case in _load_cases(dataset_raw, dataset_path=dataset_path)[1]
    }
    report_path = output_path.resolve()
    journal_path = report_path.with_suffix(report_path.suffix + ".journal.jsonl")
    if report_path.exists() or journal_path.exists():
        raise EvaluationError("Refusing to overwrite an existing report or journal.")
    live_claim = _claim_live_plan(plan["plan_sha256"]) if not dry_run else None
    kind = "synthetic-contract" if dry_run else "live"
    report = asyncio.run(
        _execute_trials(
            plan=plan,
            planned_cases=planned_cases,
            config=config,
            receipt_path=report_path,
            evidence_kind=kind,
            cases_by_id=cases_by_id,
            live_claim=live_claim,
        )
    )
    _write_new_json(report_path, report)
    return report


def _score_command(args: argparse.Namespace) -> int:
    if __package__:
        from .semantic_review_scoring import score_files
    else:
        from semantic_review_scoring import score_files

    report = score_files(
        args.receipt,
        args.dataset,
        args.labels,
        annotations_path=args.annotations,
        output_path=args.output,
        plan_path=args.plan,
    )
    print(
        json.dumps(
            {
                "score_report": str(args.output.resolve()),
                "evidence_kind": report.get("evidence_kind"),
                "claim_scope": report.get("claim_scope"),
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    plan = modes.add_parser("plan", help="Create a no-provider-call review plan")
    plan.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    plan.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--model")
    plan.add_argument("--endpoint-policy", choices=("local", "hosted"))
    plan.add_argument("--api-base")
    plan.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    plan.add_argument("--output-cap", type=int, default=MAX_OUTPUT_TOKENS)

    dry = modes.add_parser("dry-run", help="Exercise production reviewer via fake HTTP")
    dry.add_argument("--plan", type=Path, required=True)
    dry.add_argument("--output", type=Path, required=True)
    dry.add_argument("--api-base")

    live = modes.add_parser("run", help="Run a separately approved live pilot")
    live.add_argument("--live", action="store_true", required=True)
    live.add_argument(
        "--confirm-plan", required=True, help="Exact reviewed plan SHA-256"
    )
    live.add_argument("--plan", type=Path, required=True)
    live.add_argument("--output", type=Path, required=True)
    live.add_argument("--api-base")

    score = modes.add_parser("score", help="Score a privacy-safe receipt")
    score.add_argument("--receipt", type=Path, required=True)
    score.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    score.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    score.add_argument("--annotations", type=Path)
    score.add_argument("--plan", type=Path)
    score.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.mode == "plan":
            if args.output.suffix.lower() != ".json":
                raise EvaluationError("Plan output must use a .json filename.")
            markdown_path = args.output.with_suffix(".md")
            if args.output.exists() or markdown_path.exists():
                raise EvaluationError("Refusing to overwrite an existing plan file.")
            config = _new_generation_config(
                args.model,
                args.endpoint_policy,
                args.api_base,
                args.output_cap,
            )
            plan = _plan_body(
                dataset_path=args.dataset,
                labels_path=args.labels,
                config=config,
                repetitions=args.repetitions,
            )
            _write_new_json(args.output, plan)
            _write_new_bytes(
                markdown_path,
                _plan_markdown(plan).encode("utf-8"),
            )
            print(
                json.dumps(
                    {
                        "plan": str(args.output.resolve()),
                        "plan_markdown": str(markdown_path.resolve()),
                        "plan_sha256": plan["plan_sha256"],
                        "selected_cases": plan["dataset"]["case_count"],
                        "maximum_provider_attempts_for_selected_cases": plan[
                            "attempt_policy"
                        ]["maximum_provider_attempts_for_selected_cases"],
                        "provider_requests": 0,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.mode == "dry-run":
            report = run_plan(
                args.plan, args.output, dry_run=True, api_base=args.api_base
            )
            print(
                json.dumps(
                    {
                        "receipt": str(args.output.resolve()),
                        "evidence_kind": report["evidence_kind"],
                        "attempts_reserved": report["attempts_reserved"],
                        "provider_requests": 0,
                    },
                    sort_keys=True,
                )
            )
            return 0 if report["stop_reason"] is None else 1
        if args.mode == "run":
            report = run_plan(
                args.plan,
                args.output,
                dry_run=False,
                api_base=args.api_base,
                confirm_plan=args.confirm_plan,
            )
            print(
                json.dumps(
                    {
                        "receipt": str(args.output.resolve()),
                        "evidence_kind": report["evidence_kind"],
                        "attempts_reserved": report["attempts_reserved"],
                    },
                    sort_keys=True,
                )
            )
            return 0 if report["stop_reason"] is None else 1
        return _score_command(args)
    except EvaluationError as exc:
        # All expected errors are intentionally generic; provider and fixture
        # exception payloads are never included in reports or command output.
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - prevent SDK payloads reaching console output
        # Keep unexpected package/SDK payloads out of the console as well as
        # out of durable reports.
        print("Semantic review evaluation failed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
