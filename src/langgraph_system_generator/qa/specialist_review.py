"""Host-owned semantic context and evidence admission; no provider calls."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from langgraph_system_generator.qa.specialist_models import (
    REVIEWER_ID,
    EvidenceLocation,
    ModelReviewResponse,
    ReviewReason,
    ReviewSource,
    SemanticFinding,
    SemanticReviewContext,
    SemanticReviewFeedback,
    SemanticReviewPolicy,
    SourceFamily,
    review_response_format,
)
from langgraph_system_generator.utils.config import Settings

if TYPE_CHECKING:
    from langgraph_system_generator.generator.state import QAReport
from langgraph_system_generator.utils.credential_redaction import (
    _sanitize_text_credentials,
    sanitize_generation_payload,
)


def canonical_json(value: Any) -> str:
    """Stable exact Unicode JSON, also used to measure the complete input."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, Mapping):
        return {str(k): _payload(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_payload(v) for v in value]
    return value


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_review_context(
    state: Mapping[str, Any], *, instructions: str
) -> SemanticReviewContext:
    """Snapshot full composed candidate and redacted supplied facts in memory."""
    from langgraph_system_generator.notebook.composer import NotebookComposer
    from langgraph_system_generator.qa.outcomes import (
        _is_summary,
        notebook_candidate_id,
    )

    notebook = NotebookComposer().build_notebook(state.get("generated_cells") or [])
    sources: list[ReviewSource] = []

    def add(
        family: SourceFamily,
        source_id: str,
        text: Any,
        location: Any,
        *,
        version: Any = None,
        cell_index: int | None = None,
    ) -> None:
        text = _sanitize_text_credentials(str(text))
        sources.append(
            ReviewSource(
                family=family,
                source_id=source_id,
                fingerprint=_hash(text),
                text=text,
                location=_sanitize_text_credentials(str(location)),
                version=(
                    _sanitize_text_credentials(str(version))
                    if version is not None
                    else None
                ),
                cell_index=cell_index,
            )
        )

    add("requirement", "request:prompt", state.get("user_prompt", ""), "user_prompt")
    for i, turn in enumerate(state.get("requirements_messages") or []):
        add(
            "requirement",
            f"request:turn:{i}",
            turn.get("content", ""),
            f"requirements_messages/{i}/{turn.get('role', '')}",
        )
    for i, constraint in enumerate(state.get("constraints") or []):
        add(
            "requirement",
            f"requirement:{i}",
            canonical_json(_payload(constraint)),
            f"constraints/{i}",
        )
    index = 0
    for cell in notebook.cells:
        if _is_summary(cell.cell_type, cell.metadata):
            continue
        add(
            "cell",
            f"cell:{index}",
            cell.source,
            f"candidate/cells/{index}",
            cell_index=index,
        )
        index += 1
    docs = [_payload(s) for s in state.get("docs_context") or []]
    pack = _payload(state.get("generation_context_pack") or {})
    docs.extend(pack.get("docs_snippets") or [])
    for i, doc in enumerate(docs):
        content = doc.get("content", doc.get("excerpt", ""))
        if str(content).strip():
            add(
                "docs",
                f"docs:{i}",
                content,
                doc.get("source", "supplied_context"),
                version=doc.get("version"),
            )
    facts = {
        key: _payload(state.get(key))
        for key in (
            "requirements_feedback",
            "workflow_design",
            "tools_plan",
            "graph_exports",
            "notebook_plan",
            "architecture_type",
            "selected_patterns",
            "generation_context_pack",
        )
    }
    facts["candidate_cell_metadata"] = [
        dict(cell.metadata)
        for cell in notebook.cells
        if not _is_summary(cell.cell_type, cell.metadata)
    ]
    candidate = notebook_candidate_id(notebook)
    attempt = int(state.get("repair_attempts", 0))
    data = {
        "candidate_id": candidate,
        "attempt": attempt,
        "sources": [s.model_dump() for s in sources],
        "facts": sanitize_generation_payload(facts),
    }
    envelope = {
        "messages": [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": "UNTRUSTED_REVIEW_DATA_JSON\n" + canonical_json(data),
            },
        ],
        "response_format": review_response_format(),
    }
    serialized = canonical_json(envelope)
    return SemanticReviewContext(
        candidate_id=candidate,
        attempt=attempt,
        sources=tuple(sources),
        docs_available=any(s.family == "docs" for s in sources),
        request_json=serialized,
        context_digest=_hash("semantic-review-context-v1\0" + serialized),
    )


def admit_findings(
    context: SemanticReviewContext, response: ModelReviewResponse
) -> tuple[SemanticFinding, ...]:
    """Reject the entire response on invented evidence; persist no quotes."""
    sources = {source.source_id: source for source in context.sources}
    findings = []
    for finding in response.findings:
        refs = []
        families: Counter[str] = Counter()
        for ref in finding.references:
            source = sources.get(ref.source_id)
            if source is None or ref.end > len(source.text):
                raise ValueError("Invalid semantic evidence")
            fragment = source.text[ref.start : ref.end]
            if ref.quote != fragment:
                raise ValueError("Semantic quote does not match source range")
            families[source.family] += 1
            refs.append(
                EvidenceLocation(
                    source_id=source.source_id,
                    family=source.family,
                    fingerprint=source.fingerprint,
                    start=ref.start,
                    end=ref.end,
                    cell_index=source.cell_index,
                    version=source.version,
                    location=source.location,
                )
            )
        if not families["requirement"] or max(families.values()) > 2:
            raise ValueError("Missing requirement or excessive references")
        if finding.category == "provided_docs_conflict" and not families["docs"]:
            raise ValueError("Docs alignment requires supplied docs evidence")
        if not families["cell"]:
            raise ValueError("Finding requires candidate-cell evidence")
        message = _summary_text(finding.message)
        suggestions = tuple(_summary_text(s) for s in finding.suggestions)
        if not message or any(not s for s in suggestions):
            raise ValueError("Empty semantic text")
        identity = canonical_json(
            [
                context.candidate_id,
                context.context_digest,
                finding.category,
                [r.model_dump() for r in refs],
                message,
            ]
        )
        findings.append(
            SemanticFinding(
                finding_id=_hash(identity),
                rule_id=f"semantic.{REVIEWER_ID}.{finding.category}",
                category=finding.category,
                message=message,
                suggestions=suggestions,
                references=tuple(refs),
            )
        )
    return tuple(findings)


def _summary_text(text: str) -> str:
    return re.sub(
        r"[\x00-\x1f\x7f-\x9f]", " ", sanitize_generation_payload(text)
    ).strip()


def snapshot_review_policy(settings: Settings) -> SemanticReviewPolicy:
    """Operator-only immutable snapshot; never a public request option."""
    return SemanticReviewPolicy(
        mode=settings.lnf_specialist_qa_mode,
        plugin_modules=tuple(settings.qa_repair_plugin_modules),
    )


def skipped_review_feedback(state: Mapping[str, Any]) -> SemanticReviewFeedback | None:
    """Enabled-run eligibility/abstention, also used by direct packaging/stub."""
    from langgraph_system_generator.qa.summary import has_blocking_failures

    policy = state.get("semantic_review_policy") or SemanticReviewPolicy()
    if policy.mode == "off":
        return None
    reason: ReviewReason | None = None
    if state.get("generation_mode") == "stub":
        reason = "stub"
    elif not state.get("generated_cells"):
        reason = "no_cells"
    elif has_blocking_failures(state.get("qa_reports") or []):
        reason = "blocking_qa"
        for report in state["qa_reports"]:
            if (
                not report.passed
                and report.evidence.get("failure_kind") == "runtime_unavailable"
            ):
                reason = "runtime_unavailable"
                break
    if reason is None:
        return None
    from langgraph_system_generator.qa.outcomes import candidate_id

    return SemanticReviewFeedback(
        effective_mode="advisory",
        status="skipped",
        reason_code=reason,
        candidate_id=candidate_id(state.get("generated_cells") or []),
        attempt=int(state.get("repair_attempts", 0)),
    )


async def review_candidate(state: Mapping[str, Any]) -> SemanticReviewFeedback | None:
    """Resolve exactly one specialist, then admit only current host-bound evidence."""
    import asyncio

    from langgraph_system_generator.qa.registry import get_qa_repair_registry
    from langgraph_system_generator.qa.specialist_models import (
        MAX_INPUT_CHARS,
        REVIEW_TIMEOUT_SECONDS,
    )
    from langgraph_system_generator.utils.config import ModelConfig, settings

    policy = state.get("semantic_review_policy") or SemanticReviewPolicy()
    if policy.mode == "off":
        return None
    previous = state.get("semantic_review_feedback")
    skipped = skipped_review_feedback(state)
    if skipped:
        return skipped
    feedback = SemanticReviewFeedback(
        effective_mode="advisory",
        status="unavailable",
        reason_code="reviewer_unavailable",
        attempt=int(state.get("repair_attempts", 0)),
    )
    try:
        registration = get_qa_repair_registry(
            policy.plugin_modules
        ).specialist_reviewer(REVIEWER_ID)
        config = state.get("generation_config")
        model_config = (
            config.to_model_config(settings.default_model)
            if config
            else ModelConfig(model=settings.default_model, temperature=0)
        )
        reviewer = registration.factory(model_config)
        context = build_review_context(state, instructions=reviewer.instructions)
        if previous is not None:
            if previous.context_digest != context.context_digest:
                return previous.model_copy(
                    update={
                        "status": "incomplete",
                        "reason_code": "stale_context",
                        "findings": (),
                    }
                )
            return (
                previous  # No second provider call, even after an unsuccessful review.
            )
        feedback = feedback.model_copy(
            update={
                "reviewer_version": registration.version,
                "candidate_id": context.candidate_id,
                "context_digest": context.context_digest,
            }
        )
        if len(context.request_json) > MAX_INPUT_CHARS:
            return feedback.model_copy(
                update={"status": "incomplete", "reason_code": "input_limit"}
            )
        result = await asyncio.wait_for(
            reviewer.review(context), timeout=REVIEW_TIMEOUT_SECONDS
        )
        feedback = feedback.model_copy(
            update={
                "status": result.status,
                "reason_code": result.reason_code,
                "model_invocations": result.model_invocations,
            }
        )
        current = build_review_context(state, instructions=reviewer.instructions)
        if (
            result.candidate_id != current.candidate_id
            or result.context_digest != current.context_digest
            or context.context_digest != current.context_digest
        ):
            return feedback.model_copy(
                update={"status": "incomplete", "reason_code": "stale_context"}
            )
        if result.status == "reviewed":
            if result.response is None or result.response.assessment != "complete":
                return feedback.model_copy(
                    update={
                        "status": "invalid_response",
                        "reason_code": "invalid_response",
                    }
                )
            try:
                findings = admit_findings(context, result.response)
            except ValueError:
                return feedback.model_copy(
                    update={
                        "status": "invalid_response",
                        "reason_code": "invalid_reference",
                    }
                )
            return feedback.model_copy(
                update={
                    "findings": findings,
                    "docs_alignment": (
                        "provided_docs_only"
                        if context.docs_available
                        else "not_assessed"
                    ),
                }
            )
        return feedback
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return feedback.model_copy(
            update={
                "status": "unavailable",
                "reason_code": "timeout",
                "model_invocations": 1,
            }
        )
    except Exception:  # noqa: BLE001 - optional plugin failures remain advisories
        return feedback.model_copy(
            update={
                "status": "unavailable",
                "reason_code": "reviewer_unavailable",
                "findings": (),
            }
        )


def semantic_reports(feedback: SemanticReviewFeedback | None) -> list[QAReport]:
    from langgraph_system_generator.generator.state import QAReport

    if feedback is None or feedback.status != "reviewed":
        return []
    return [
        QAReport(
            check_name="Requirements/Domain Fidelity Review",
            rule_id=finding.rule_id,
            stage="semantic",
            passed=False,
            severity="warning",
            repairable=False,
            category=finding.category,
            message=finding.message,
            suggestions=list(finding.suggestions),
            attempt=feedback.attempt,
            evidence={
                "candidate_id": feedback.candidate_id,
                "context_digest": feedback.context_digest,
                "reviewer_id": feedback.reviewer_id,
                "reviewer_version": feedback.reviewer_version,
                "finding_id": finding.finding_id,
                "references": [ref.model_dump() for ref in finding.references],
            },
        )
        for finding in feedback.findings
    ]
