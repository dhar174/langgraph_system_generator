"""Embedding and vector store management for documentation retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings


class VectorStoreManager:
    """Manages creation and loading of the documentation vector index."""

    def __init__(self, store_path: str, embeddings: Optional[Embeddings] = None):
        self.store_path = str(store_path)
        self.embeddings = embeddings or OpenAIEmbeddings()
        self.vector_store: Optional[FAISS] = None

    def index_exists(self) -> bool:
        """Return True if a saved FAISS index is already present."""

        base = Path(self.store_path)
        return (base / "index.faiss").exists() and (base / "index.pkl").exists()

    def create_index(self, documents: List[Document]) -> FAISS:
        """Create and persist a FAISS index from the given documents."""

        if not documents:
            raise ValueError("No documents provided for indexing.")

        Path(self.store_path).mkdir(parents=True, exist_ok=True)
        self.vector_store = FAISS.from_documents(documents, self.embeddings)
        self.vector_store.save_local(self.store_path)
        return self.vector_store

    def load_index(self) -> FAISS:
        """Load an existing FAISS index from disk."""

        if not self.index_exists():
            raise FileNotFoundError(f"Vector store not found at {self.store_path}")

        self.vector_store = FAISS.load_local(
            self.store_path,
            self.embeddings,
            allow_dangerous_deserialization=True,
        )
        return self.vector_store

    def load_or_create(self, documents: List[Document]) -> FAISS:
        """Load an existing index or create a new one if missing."""

        if self.index_exists():
            return self.load_index()
        return self.create_index(documents)
