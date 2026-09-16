"""Base interfaces and models for documentation source providers."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from langgraph_system_generator.generator.state import DocSnippet


class DocsSourceStatus(str, Enum):
    """Execution status for a documentation source attempt."""

    SUCCESS = "success"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    SKIPPED = "skipped"


class DocsProviderResult(BaseModel):
    """Result returned by an individual documentation source provider."""

    source_id: str
    status: DocsSourceStatus
    snippets: List[DocSnippet] = Field(default_factory=list)
    latency_ms: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocsSourceProvider(ABC):
    """Abstract base class for documentation source providers."""

    source_id: str

    @abstractmethod
    def is_available(self, mode: str = "live") -> bool:
        """Return True if the source is configured and eligible for retrieval."""
        raise NotImplementedError

    @abstractmethod
    async def aretrieve(
        self,
        query: str,
        k: int = 5,
        mode: str = "live",
    ) -> DocsProviderResult:
        """Retrieve documentation snippets asynchronously."""
        raise NotImplementedError

    def retrieve(
        self,
        query: str,
        k: int = 5,
        mode: str = "live",
    ) -> DocsProviderResult:
        """Synchronous wrapper for aretrieve."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, self.aretrieve(query, k=k, mode=mode))
                return future.result()
        return asyncio.run(self.aretrieve(query, k=k, mode=mode))
