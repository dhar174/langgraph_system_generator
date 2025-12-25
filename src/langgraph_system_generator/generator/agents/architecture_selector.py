"""Architecture Selector agent for choosing optimal LangGraph pattern."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langgraph_system_generator.generator.state import Constraint, DocSnippet
from langgraph_system_generator.generator.utils import extract_json_from_llm_response
from langgraph_system_generator.rag.retriever import DocsRetriever
from langgraph_system_generator.utils.config import settings


class ArchitectureSelector:
    """Chooses optimal LangGraph pattern architecture."""

    def __init__(
        self, docs_retriever: DocsRetriever | None = None, model: str | None = None
    ):
        self.llm = ChatOpenAI(model=model or settings.default_model, temperature=0)
        self.docs_retriever = docs_retriever

    async def select_architecture(
        self, constraints: List[Constraint], docs_context: List[DocSnippet]
    ) -> Dict[str, Any]:
        """Select router vs subagents vs hybrid pattern.

        Args:
            constraints: Extracted project constraints
            docs_context: Retrieved documentation snippets

        Returns:
            Dictionary with patterns, architecture_type, and justification
        """
        # Retrieve pattern-specific documentation if retriever is available
        pattern_docs = []
        if self.docs_retriever:
            pattern_docs.extend(
                self.docs_retriever.retrieve_for_pattern("router") or []
            )
            pattern_docs.extend(
                self.docs_retriever.retrieve_for_pattern("subagents") or []
            )
            pattern_docs.extend(
                self.docs_retriever.retrieve_for_pattern("supervisor") or []
            )

        def _normalize_doc(doc: Any) -> Dict[str, Any]:
            if isinstance(doc, DocSnippet):
                return doc.model_dump()
            if hasattr(doc, "model_dump"):
                try:
                    return doc.model_dump()
                except AttributeError as exc:
                    logging.debug(
                        "Failed model_dump on doc snippet (AttributeError): %s", exc
                    )
                except TypeError as exc:
                    logging.debug(
                        "Failed model_dump on doc snippet (TypeError): %s", exc
                    )
            if isinstance(doc, dict):
                return doc
            return {
                "content": str(doc),
                "source": "",
                "heading": None,
                "relevance_score": 0.0,
            }

        # Format constraints for LLM
        constraints_text = "\n".join(
            [f"- [{c.type}] {c.value} (priority: {c.priority})" for c in constraints]
        )

        # Format documentation snippets
        docs_list = pattern_docs or docs_context
        normalized_docs = [_normalize_doc(doc) for doc in docs_list]
        docs_text = "\n\n".join(
            [
                f"[{doc.get('heading') or 'Section'}]\n{str(doc.get('content', ''))[:500]}"
                for doc in normalized_docs[:5]
            ]
        )

        selection_prompt = SystemMessage(
            content="""You are an expert in LangGraph architectures.
Based on the requirements and official documentation, recommend the best pattern:
- **router**: Single router that classifies inputs and routes to specialist functions
- **subagents**: Supervisor coordinating multiple subagent workers with their own contexts
- **hybrid**: Combination of router and subagents for complex workflows

Consider:
- Complexity of task decomposition
- Need for specialized contexts vs shared state
- Parallel vs sequential execution needs
- State management complexity
- Scalability requirements

Return a JSON object with this structure:
{
  "architecture_type": "router" | "subagents" | "hybrid",
  "patterns": {
    "primary": "pattern_name",
    "secondary": ["additional_patterns"]
  },
  "justification": "detailed explanation of why this architecture was chosen"
}"""
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
            return result
        except (ValueError, KeyError, TypeError):
            # Fallback to router pattern
            return {
                "architecture_type": "router",
                "patterns": {"primary": "router", "secondary": []},
                "justification": "Default router pattern selected as fallback due to parsing error.",
            }
