"""Architecture Selector agent for choosing optimal LangGraph pattern."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from langgraph_system_generator.generator.agents._llm import build_chat_llm
from langgraph_system_generator.generator.architecture_registry import (
    ArchitectureRegistry,
    get_default_architecture_registry,
)
from langgraph_system_generator.generator.state import (
    ArchitectureAlternative,
    ArchitectureFeedback,
    ArchitecturePatternSelection,
    ArchitectureSelectionResult,
    Constraint,
    DocSnippet,
)
from langgraph_system_generator.generator.utils import extract_json_from_llm_response
from langgraph_system_generator.rag.retriever import DocsRetriever
from langgraph_system_generator.utils.config import ModelConfig, settings
from langgraph_system_generator.utils.generation_options import (
    SUPPORTED_AGENT_TYPES,
    normalize_agent_type,
)

logger = logging.getLogger(__name__)


class ArchitectureSelector:
    """Chooses optimal LangGraph pattern architecture."""

    def __init__(
        self,
        docs_retriever: DocsRetriever | None = None,
        model: str | None = None,
        model_config: ModelConfig | None = None,
        architecture_registry: ArchitectureRegistry | None = None,
    ):
        self.llm = build_chat_llm(
            model=model,
            model_config=model_config,
            chat_openai_class=ChatOpenAI,
        )
        self.docs_retriever = docs_retriever
        self.architecture_registry = (
            architecture_registry.clone()
            if architecture_registry is not None
            else get_default_architecture_registry().clone()
        )

    async def select_architecture(
        self, constraints: List[Constraint], docs_context: List[DocSnippet]
    ) -> ArchitectureSelectionResult:
        """Select router vs subagents vs hybrid vs autoagent pattern."""

        prompt_docs = await self._select_prompt_docs(docs_context)
        docs_considered = [self._doc_label(doc) for doc in prompt_docs]

        constraints_text = "\n".join(
            [f"- [{c.type}] {c.value} (priority: {c.priority})" for c in constraints]
        )
        docs_text = "\n\n".join(
            [
                f"[{doc.get('heading') or 'Section'}]\n{str(doc.get('content', ''))[:500]}"
                for doc in prompt_docs
            ]
        )

        selection_prompt = SystemMessage(
            content=f"""You are an expert in LangGraph architectures.
Based on the requirements and official documentation, recommend the best pattern.

Registered architecture catalog:
{self.architecture_registry.render_selector_prompt_catalog()}

Consider:
- Complexity of task decomposition
- Need for specialized contexts vs shared state
- Parallel vs sequential execution needs
- State management complexity
- Scalability requirements

Return a JSON object with this structure:
{{
  "architecture_type": "router" | "subagents" | "hybrid" | "autoagent",
  "patterns": {{
    "primary": "pattern_name",
    "secondary": ["additional_patterns"]
  }},
  "justification": "detailed explanation of why this architecture was chosen",
  "feedback": {{
    "confidence": 0.0,
    "alternatives": [
      {{
        "architecture_type": "router",
        "score": 0.0,
        "rationale": "why this alternative ranked lower"
      }}
    ],
    "tradeoffs": ["short tradeoff statement"]
  }}
}}"""
            )

        user_message = HumanMessage(
            content=f"""Requirements:
{constraints_text}

Documentation Context:
{docs_text}

Recommend the best architecture."""
        )

        response = await self.llm.ainvoke([selection_prompt, user_message])

        try:
            result = extract_json_from_llm_response(response.content)
            return self._normalize_selection_result(result, docs_considered=docs_considered)
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            reason = f"Architecture selection fallback used: {exc}"
            logger.warning(reason)
            return self._fallback_result(
                reason,
                docs_considered=docs_considered,
                validation_errors=[str(exc)],
            )

    def _normalize_doc(self, doc: Any) -> Dict[str, Any]:
        if isinstance(doc, DocSnippet):
            return doc.model_dump()
        if hasattr(doc, "model_dump"):
            try:
                return doc.model_dump()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed model_dump on doc snippet: %s", exc)
        if isinstance(doc, dict):
            return doc
        return {
            "content": str(doc),
            "source": "",
            "heading": None,
            "relevance_score": 0.0,
        }

    def _doc_key(self, doc: Dict[str, Any]) -> tuple[str, str, str]:
        """Return the dedupe key for selector prompt docs."""

        source = str(doc.get("source") or "").strip()
        heading = str(doc.get("heading") or "").strip()
        content_fallback = ""
        if not source or not heading:
            content = str(doc.get("content") or "").strip()
            if content:
                content_fallback = hashlib.sha1(
                    content.encode("utf-8", "ignore")
                ).hexdigest()[:12]
        return source, heading, content_fallback

    def _doc_score(self, doc: Dict[str, Any]) -> float:
        """Return a sortable relevance score for a prompt doc."""

        try:
            return float(doc.get("weighted_relevance_score", doc.get("relevance_score", 0.0)))
        except (TypeError, ValueError):
            return 0.0

    async def _select_prompt_docs(
        self,
        docs_context: List[DocSnippet],
    ) -> List[Dict[str, Any]]:
        """Collect, weight, dedupe, and cap selector prompt docs."""

        prompt_limit = max(1, int(settings.architecture_prompt_doc_limit))
        normalized_docs: list[Dict[str, Any]] = []
        if self.docs_retriever:
            query_overrides = settings.architecture_pattern_doc_queries
            weight_overrides = settings.architecture_pattern_doc_weights
            query_specs: list[tuple[str, float]] = []
            for architecture_id in self.architecture_registry.supported_architecture_types():
                queries = self.architecture_registry.docs_queries_for(
                    architecture_id,
                    query_overrides=query_overrides,
                )
                weight = self.architecture_registry.docs_weight_for(
                    architecture_id,
                    weight_overrides=weight_overrides,
                )
                for query in queries:
                    query_specs.append((query, weight))

            if query_specs:
                retrieved_groups = await asyncio.gather(
                    *[
                        asyncio.to_thread(self.docs_retriever.retrieve, query, prompt_limit)
                        for query, _weight in query_specs
                    ]
                )
                for (_query, weight), docs in zip(query_specs, retrieved_groups):
                    for doc in docs or []:
                        normalized = self._normalize_doc(doc)
                        normalized["weighted_relevance_score"] = self._doc_score(normalized) * weight
                        normalized_docs.append(normalized)

        if not normalized_docs:
            normalized_docs = [self._normalize_doc(doc) for doc in docs_context]

        deduped: dict[tuple[str, str, str], Dict[str, Any]] = {}
        for doc in normalized_docs:
            key = self._doc_key(doc)
            existing = deduped.get(key)
            if existing is None or self._doc_score(doc) > self._doc_score(existing):
                deduped[key] = doc

        ranked_docs = sorted(
            deduped.values(),
            key=lambda item: (self._doc_score(item), self._doc_label(item)),
            reverse=True,
        )
        return ranked_docs[:prompt_limit]

    def _doc_label(self, doc: Dict[str, Any]) -> str:
        heading = str(doc.get("heading") or "").strip()
        source = str(doc.get("source") or "").strip()
        if heading and source:
            return f"{source}#{heading}"
        if heading:
            return heading
        if source:
            return source
        content = str(doc.get("content", "")).strip()
        return content[:80] if content else "doc"

    def _normalize_architecture_type(self, value: Any) -> str:
        normalized = normalize_agent_type(value if isinstance(value, str) else None)
        selectable = set(self.architecture_registry.selectable_architecture_types())
        if normalized not in selectable:
            raise ValueError(
                f"Unsupported architecture_type '{value}'. "
                f"Expected one of: {', '.join(sorted(selectable))}."
            )
        return normalized

    def _normalize_patterns(
        self,
        architecture_type: str,
        raw_patterns: Any,
    ) -> tuple[ArchitecturePatternSelection, List[str]]:
        validation_errors: List[str] = []
        if raw_patterns in (None, ""):
            _, normalized_secondary = self.architecture_registry.normalize_patterns(
                architecture_type
            )
            return (
                ArchitecturePatternSelection(
                    primary=architecture_type,
                    secondary=normalized_secondary,
                ),
                validation_errors,
            )
        if not isinstance(raw_patterns, dict):
            raise ValueError("Architecture selection returned malformed patterns payload.")

        primary = raw_patterns.get("primary")
        normalized_primary = normalize_agent_type(
            primary if isinstance(primary, str) else None
        )
        if normalized_primary is None:
            normalized_primary = architecture_type
        elif normalized_primary not in SUPPORTED_AGENT_TYPES:
            raise ValueError(
                "Architecture selection returned malformed patterns payload: "
                f"unsupported primary '{primary}'."
            )
        elif normalized_primary != architecture_type:
            validation_errors.append(
                "Returned primary pattern did not match architecture_type; normalized to the selected architecture."
            )
            normalized_primary = architecture_type

        secondary = raw_patterns.get("secondary", [])
        if secondary is None:
            secondary = []
        if not isinstance(secondary, list):
            raise ValueError("Architecture selection returned malformed patterns payload.")

        _, normalized_secondary = self.architecture_registry.normalize_patterns(
            normalized_primary,
            secondary_patterns=secondary,
        )
        for item in secondary:
            normalized_item = normalize_agent_type(item if isinstance(item, str) else None)
            if normalized_item is None:
                continue
            if normalized_item not in SUPPORTED_AGENT_TYPES:
                raise ValueError(
                    "Architecture selection returned malformed patterns payload: "
                    f"unsupported secondary '{item}'."
                )

        return (
            ArchitecturePatternSelection(
                primary=normalized_primary,
                secondary=normalized_secondary,
            ),
            validation_errors,
        )

    def _normalize_feedback(
        self,
        raw_feedback: Any,
        *,
        docs_considered: List[str],
        validation_errors: List[str],
    ) -> ArchitectureFeedback:
        if raw_feedback in (None, ""):
            return ArchitectureFeedback(
                validation_errors=list(validation_errors),
                docs_considered=docs_considered,
            )
        if not isinstance(raw_feedback, dict):
            return ArchitectureFeedback(
                validation_errors=[
                    *validation_errors,
                    "Architecture feedback payload was not an object and was ignored.",
                ],
                docs_considered=docs_considered,
            )

        feedback_validation_errors = list(validation_errors)
        alternatives_payload = raw_feedback.get("alternatives", [])
        if alternatives_payload in (None, ""):
            alternatives_payload = []
        if not isinstance(alternatives_payload, list):
            feedback_validation_errors.append(
                "Architecture feedback alternatives payload was not a list and was ignored."
            )
            alternatives_payload = []

        alternatives: List[ArchitectureAlternative] = []
        for alternative in alternatives_payload:
            if not isinstance(alternative, dict):
                feedback_validation_errors.append(
                    "Ignored non-object architecture alternative entry."
                )
                continue
            alt_type = normalize_agent_type(
                alternative.get("architecture_type")
                if isinstance(alternative.get("architecture_type"), str)
                else None
            )
            if alt_type not in SUPPORTED_AGENT_TYPES:
                feedback_validation_errors.append(
                    "Ignored architecture alternative with unsupported architecture_type."
                )
                continue
            try:
                alternatives.append(
                    ArchitectureAlternative(
                        architecture_type=alt_type,
                        score=alternative.get("score"),
                        rationale=alternative.get("rationale"),
                    )
                )
            except ValidationError as exc:
                feedback_validation_errors.append(
                    f"Ignored malformed architecture alternative: {exc.errors()[0]['msg']}."
                )

        tradeoffs_payload = raw_feedback.get("tradeoffs", [])
        if tradeoffs_payload in (None, ""):
            tradeoffs_payload = []
        if not isinstance(tradeoffs_payload, list):
            feedback_validation_errors.append(
                "Architecture feedback tradeoffs payload was not a list and was ignored."
            )
            tradeoffs_payload = []

        tradeoffs = [str(item).strip() for item in tradeoffs_payload if str(item).strip()]
        try:
            return ArchitectureFeedback(
                confidence=raw_feedback.get("confidence"),
                alternatives=alternatives,
                tradeoffs=tradeoffs,
                validation_errors=feedback_validation_errors,
                docs_considered=docs_considered,
            )
        except ValidationError as exc:
            feedback_validation_errors.append(
                f"Architecture feedback validation failed: {exc.errors()[0]['msg']}."
            )
            return ArchitectureFeedback(
                alternatives=alternatives,
                tradeoffs=tradeoffs,
                validation_errors=feedback_validation_errors,
                docs_considered=docs_considered,
            )

    def _normalize_selection_result(
        self,
        payload: Any,
        *,
        docs_considered: List[str],
    ) -> ArchitectureSelectionResult:
        if not isinstance(payload, dict):
            raise ValueError("Architecture selection payload must be an object.")

        architecture_type = self._normalize_architecture_type(payload.get("architecture_type"))
        justification = str(payload.get("justification") or "").strip()
        if not justification:
            raise ValueError("Architecture selection must include a non-empty justification.")

        patterns, validation_errors = self._normalize_patterns(
            architecture_type,
            payload.get("patterns"),
        )
        feedback = self._normalize_feedback(
            payload.get("feedback"),
            docs_considered=docs_considered,
            validation_errors=validation_errors,
        )

        return ArchitectureSelectionResult(
            architecture_type=architecture_type,
            patterns=patterns,
            justification=justification,
            feedback=feedback,
        )

    def _fallback_result(
        self,
        reason: str,
        *,
        docs_considered: List[str],
        validation_errors: List[str] | None = None,
    ) -> ArchitectureSelectionResult:
        return ArchitectureSelectionResult(
            architecture_type="router",
            patterns=ArchitecturePatternSelection(
                primary="router",
                secondary=self.architecture_registry.normalize_patterns("router")[1],
            ),
            justification=(
                "Default router pattern selected as a safe fallback because "
                "architecture selection could not be validated."
            ),
            feedback=ArchitectureFeedback(
                fallback_used=True,
                fallback_reason=reason,
                validation_errors=list(validation_errors or []),
                tradeoffs=[
                    "Router fallback favors reliability over architecture-specific optimization."
                ],
                docs_considered=docs_considered,
            ),
        )
