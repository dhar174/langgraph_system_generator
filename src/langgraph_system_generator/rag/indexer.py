"""Documentation indexer for LangGraph references."""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable, List, Optional

import aiohttp
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langgraph_system_generator.utils.config import get_settings
from langgraph_system_generator.rag.embeddings import VectorStoreManager


class DocsIndexer:
    """Scrapes and chunks LangGraph documentation content."""

    PYTHON_DOCS_URLS = [
        "https://docs.langchain.com/oss/python/langgraph/use-graph-api",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/subagents",
        "https://docs.langchain.com/oss/python/langchain/agents",
    ]
    JAVASCRIPT_DOCS_URLS = [
        "https://docs.langchain.com/oss/javascript/langchain/multi-agent/router",
        "https://docs.langchain.com/oss/javascript/langgraph/persistence",
    ]
    DOCS_URLS = PYTHON_DOCS_URLS + JAVASCRIPT_DOCS_URLS

    def __init__(
        self,
        urls: Optional[Iterable[str]] = None,
        *,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        request_timeout: float = 30.0,
    ):
        self.urls = list(urls) if urls is not None else self.DOCS_URLS
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.request_timeout = request_timeout

    async def scrape_docs(self) -> List[Document]:
        """Scrape configured documentation pages and convert them to documents."""

        if not self.urls:
            return []

        async with aiohttp.ClientSession() as session:
            responses = await asyncio.gather(
                *[self._fetch(session, url) for url in self.urls],
                return_exceptions=True,
            )

        documents: List[Document] = []
        for url, result in zip(self.urls, responses):
            if isinstance(result, Exception):
                logging.warning("Failed to fetch %s: %s", url, result)
                continue
            doc = self._html_to_document(result, url)
            if doc.page_content.strip():
                documents.append(doc)

        return documents

    def chunk_documents(self, docs: List[Document]) -> List[Document]:
        """Split documents into overlapping chunks."""

        if not docs:
            return []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap
        )
        return splitter.split_documents(docs)

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str:
        async with session.get(url, timeout=self.request_timeout) as response:
            response.raise_for_status()
            return await response.text()

    def _html_to_document(self, html: str, source: str) -> Document:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = (
            soup.title.string.strip() if soup.title and soup.title.string else None
        )
        heading = None
        heading_tag = soup.find(
            lambda tag: tag.name in ("h1", "h2", "h3") and tag.get_text(strip=True)
        )
        if heading_tag:
            heading = heading_tag.get_text(strip=True)

        text = soup.get_text("\n", strip=True)
        cleaned_lines = [line for line in (ln.strip() for ln in text.splitlines()) if line]
        content = "\n".join(cleaned_lines)

        metadata = {"source": source}
        if title:
            metadata["title"] = title
        if heading:
            metadata["heading"] = heading

        return Document(page_content=content, metadata=metadata)


async def build_docs_index(
    *,
    documents: Optional[List[Document]] = None,
    urls: Optional[Iterable[str]] = None,
    store_path: Optional[str] = None,
    force_rebuild: bool = False,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    embeddings: Optional[Embeddings] = None,
) -> VectorStoreManager:
    """Build (or load) the LangGraph documentation vector index.

    If ``documents`` are provided they are used directly and any provided
    ``urls`` are ignored. Otherwise documentation pages are scraped from the
    configured URLs, chunked, and indexed. When an existing index is present
    and ``force_rebuild`` is False, it will be loaded instead of recreated.

    Parameters
    ----------
    documents
        Optional list of documents to index directly.
    urls
        Optional iterable of documentation URLs to scrape. Ignored when
        ``documents`` is provided.
    store_path
        Filesystem path to persist/load the vector store. Defaults to the
        configured ``vector_store_path``.
    force_rebuild
        When True, recreate the index even if one already exists.
    chunk_size
        Maximum characters per chunk when splitting documents.
    chunk_overlap
        Overlap size (in characters) between adjacent chunks.
    embeddings
        Optional LangChain-compatible embeddings implementation to use.

    Returns
    -------
    VectorStoreManager
        Manager with the loaded or newly created vector store.
    """

    settings = get_settings()
    destination = store_path or settings.vector_store_path

    indexer = DocsIndexer(
        urls=urls,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if documents is None:
        documents = await indexer.scrape_docs()

    chunks = indexer.chunk_documents(documents)

    manager = VectorStoreManager(destination, embeddings=embeddings)
    if manager.index_exists() and not force_rebuild:
        manager.load_index()
        return manager

    manager.create_index(chunks)
    return manager
