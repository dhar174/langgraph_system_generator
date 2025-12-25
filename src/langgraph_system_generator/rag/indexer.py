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

    # Comprehensive curated list of LangGraph and LangChain documentation
    # Core LangGraph concepts and API
    LANGGRAPH_CORE_URLS = [
        "https://langchain-ai.github.io/langgraph/",
        "https://langchain-ai.github.io/langgraph/concepts/",
        "https://langchain-ai.github.io/langgraph/concepts/low_level/",
        "https://langchain-ai.github.io/langgraph/concepts/high_level/",
        "https://langchain-ai.github.io/langgraph/how-tos/",
        "https://langchain-ai.github.io/langgraph/tutorials/",
    ]
    
    # LangGraph patterns and multi-agent architectures
    LANGGRAPH_PATTERNS_URLS = [
        "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/agent_supervisor/",
        "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/hierarchical_agent_teams/",
        "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/",
        "https://langchain-ai.github.io/langgraph/how-tos/subgraph/",
        "https://langchain-ai.github.io/langgraph/how-tos/branching/",
        "https://langchain-ai.github.io/langgraph/how-tos/create-react-agent/",
    ]
    
    # LangGraph state management and persistence
    LANGGRAPH_STATE_URLS = [
        "https://langchain-ai.github.io/langgraph/how-tos/persistence/",
        "https://langchain-ai.github.io/langgraph/how-tos/state-model/",
        "https://langchain-ai.github.io/langgraph/how-tos/state-context-key/",
        "https://langchain-ai.github.io/langgraph/concepts/persistence/",
    ]
    
    # LangChain core concepts
    LANGCHAIN_CORE_URLS = [
        "https://python.langchain.com/docs/introduction/",
        "https://python.langchain.com/docs/concepts/",
        "https://python.langchain.com/docs/tutorials/",
        "https://python.langchain.com/docs/how_to/",
    ]
    
    # LangChain agents and tools
    LANGCHAIN_AGENTS_URLS = [
        "https://python.langchain.com/docs/concepts/agents/",
        "https://python.langchain.com/docs/tutorials/agents/",
        "https://python.langchain.com/docs/how_to/agent_executor/",
        "https://python.langchain.com/docs/how_to/custom_tools/",
        "https://python.langchain.com/docs/integrations/tools/",
    ]
    
    # LangChain RAG and retrieval
    LANGCHAIN_RAG_URLS = [
        "https://python.langchain.com/docs/tutorials/rag/",
        "https://python.langchain.com/docs/how_to/vectorstores/",
        "https://python.langchain.com/docs/how_to/embed_text/",
        "https://python.langchain.com/docs/integrations/vectorstores/faiss/",
    ]
    
    # LangChain chains and prompts
    LANGCHAIN_CHAINS_URLS = [
        "https://python.langchain.com/docs/concepts/chains/",
        "https://python.langchain.com/docs/concepts/prompts/",
        "https://python.langchain.com/docs/how_to/prompts/",
        "https://python.langchain.com/docs/how_to/sequence/",
    ]
    
    # LangGraph streaming and async
    LANGGRAPH_ADVANCED_URLS = [
        "https://langchain-ai.github.io/langgraph/how-tos/streaming-tokens/",
        "https://langchain-ai.github.io/langgraph/how-tos/streaming-from-final-node/",
        "https://langchain-ai.github.io/langgraph/how-tos/async/",
    ]
    
    # Combine all URLs
    DOCS_URLS = (
        LANGGRAPH_CORE_URLS +
        LANGGRAPH_PATTERNS_URLS +
        LANGGRAPH_STATE_URLS +
        LANGCHAIN_CORE_URLS +
        LANGCHAIN_AGENTS_URLS +
        LANGCHAIN_RAG_URLS +
        LANGCHAIN_CHAINS_URLS +
        LANGGRAPH_ADVANCED_URLS
    )

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
