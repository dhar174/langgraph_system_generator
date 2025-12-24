"""Documentation indexer for LangGraph references."""

from __future__ import annotations

import asyncio
from typing import Iterable, List, Optional

import aiohttp
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langgraph_system_generator.utils.config import get_settings
from langgraph_system_generator.rag.embeddings import VectorStoreManager


class DocsIndexer:
    """Scrapes and chunks LangGraph documentation content."""

    DOCS_URLS = [
        "https://docs.langchain.com/oss/python/langgraph/use-graph-api",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/subagents",
        "https://docs.langchain.com/oss/javascript/langchain/multi-agent/router",
        "https://docs.langchain.com/oss/python/langchain/agents",
        "https://docs.langchain.com/oss/javascript/langgraph/persistence",
    ]

    def __init__(
        self,
        urls: Optional[Iterable[str]] = None,
        *,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        self.urls = list(urls) if urls is not None else self.DOCS_URLS
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

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
        async with session.get(url, timeout=30) as response:
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
        for header in soup.find_all(["h1", "h2", "h3"]):
            text = header.get_text(strip=True)
            if text:
                heading = text
                break

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
    embeddings=None,
) -> VectorStoreManager:
    """Build (or load) the LangGraph docs index and return the manager."""

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
