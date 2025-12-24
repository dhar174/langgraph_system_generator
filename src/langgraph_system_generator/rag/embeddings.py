"""Embedding and vector store management for documentation retrieval."""

from __future__ import annotations

import hashlib
import json
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
        """Create and persist a FAISS index from the given documents.

        Parameters
        ----------
        documents : List[Document]
            The list of documents to embed and store in the FAISS index.

        Returns
        -------
        FAISS
            The FAISS vector store created from the provided documents.

        Raises
        ------
        ValueError
            If no documents are provided for indexing.
        """

        if not documents:
            raise ValueError("No documents provided for indexing.")

        Path(self.store_path).mkdir(parents=True, exist_ok=True)
        self.vector_store = FAISS.from_documents(documents, self.embeddings)
        self.vector_store.save_local(self.store_path)
        self._write_integrity_manifest()
        return self.vector_store

    def load_index(self) -> FAISS:
        """Load an existing FAISS index from disk.

        Returns
        -------
        FAISS
            The loaded FAISS vector store instance.

        Raises
        ------
        FileNotFoundError
            If no persisted FAISS index exists at ``self.store_path``.
        ValueError
            If the integrity check for stored index files fails.
        """

        if not self.index_exists():
            raise FileNotFoundError(f"Vector store not found at {self.store_path}")

        self._validate_integrity()
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

    def _write_integrity_manifest(self) -> None:
        """Persist simple integrity hashes for stored FAISS files."""

        base = Path(self.store_path)
        manifest = {
            "index.faiss": self._file_hash(base / "index.faiss"),
            "index.pkl": self._file_hash(base / "index.pkl"),
        }
        (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def _validate_integrity(self) -> None:
        """Validate stored FAISS files against the manifest."""

        base = Path(self.store_path)
        manifest_path = base / "manifest.json"
        if not manifest_path.exists():
            return

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            raise ValueError("Corrupted vector store manifest.")

        for filename, expected_hash in manifest.items():
            current = self._file_hash(base / filename)
            if not expected_hash or current != expected_hash:
                raise ValueError(
                    f"Integrity check failed for {filename}; refusing to load index."
                )

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
