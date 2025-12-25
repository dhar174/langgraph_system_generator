"""Document caching utilities for offline indexing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from langchain_core.documents import Document


class DocumentCache:
    """Manages cached documentation for offline indexing."""

    def __init__(self, cache_path: str = "./data/cached_docs"):
        self.cache_path = Path(cache_path)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_path / "documents.json"

    def save_documents(self, documents: List[Document]) -> None:
        """Save documents to cache file."""
        serialized = [
            {
                "page_content": doc.page_content,
                "metadata": doc.metadata,
            }
            for doc in documents
        ]
        
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)

    def load_documents(self) -> List[Document]:
        """Load documents from cache file."""
        if not self.cache_file.exists():
            return []
        
        with open(self.cache_file, "r", encoding="utf-8") as f:
            serialized = json.load(f)
        
        return [
            Document(
                page_content=item["page_content"],
                metadata=item["metadata"],
            )
            for item in serialized
        ]

    def exists(self) -> bool:
        """Check if cache file exists."""
        return self.cache_file.exists()
