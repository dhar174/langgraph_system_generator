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
        "https://docs.langchain.com/oss/python/langgraph/overview",
        "https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph",
        "https://docs.langchain.com/oss/python/langgraph/durable-execution",
        "https://docs.langchain.com/oss/python/langgraph/streaming",
        "https://docs.langchain.com/oss/python/langgraph/interrupts",
        "https://docs.langchain.com/oss/python/langgraph/use-subgraphs",
        "https://docs.langchain.com/oss/python/langgraph/application-structure",
        "https://docs.langchain.com/oss/python/langgraph/test",
        "https://docs.langchain.com/oss/python/langgraph/ui",
        "https://docs.langchain.com/oss/python/langchain/agents",
        "https://docs.langchain.com/oss/python/langchain/models",
        "https://docs.langchain.com/oss/python/langchain/messages",
        "https://docs.langchain.com/oss/python/langchain/tools",
        "https://docs.langchain.com/oss/python/langchain/short-term-memory",
        "https://docs.langchain.com/oss/python/langchain/streaming",
        "https://docs.langchain.com/oss/python/langchain/structured-output",
        "https://docs.langchain.com/oss/python/langchain/middleware/overview",
        "https://docs.langchain.com/oss/python/langchain/middleware/built-in",
        "https://docs.langchain.com/oss/python/langchain/middleware/custom",
        "https://docs.langchain.com/oss/python/langchain/runtime",
        "https://docs.langchain.com/oss/python/langchain/context-engineering",
        "https://docs.langchain.com/oss/python/langchain/mcp",
        "https://docs.langchain.com/oss/python/langchain/human-in-the-loop",
        "https://docs.langchain.com/oss/python/langchain/retrieval",
        "https://docs.langchain.com/oss/python/langchain/long-term-memory",
        "https://docs.langchain.com/oss/python/deepagents/quickstart",
        "https://docs.langchain.com/oss/python/deepagents/customization",
        "https://docs.langchain.com/oss/python/deepagents/harness",
        "https://docs.langchain.com/oss/python/deepagents/backends",
        "https://docs.langchain.com/oss/python/deepagents/subagents",
        "https://docs.langchain.com/oss/python/deepagents/human-in-the-loop",
        "https://docs.langchain.com/oss/python/deepagents/middleware",
        "https://docs.langchain.com/oss/python/deepagents/cli",
        "https://docs.langchain.com/oss/python/integrations/chat/openai",
        "https://docs.langchain.com/oss/python/langgraph/agentic-rag",
        "https://docs.langchain.com/oss/python/langgraph/sql-agent",
        "https://docs.langchain.com/oss/python/langchain/knowledge-base",
        "https://docs.langchain.com/oss/python/langchain/rag",
        "https://docs.langchain.com/oss/python/langchain/sql-agent",
        "https://docs.langchain.com/oss/python/langchain/voice-agent",
        "https://docs.langchain.com/oss/python/langchain/component-architecture",
        "https://reference.langchain.com/python/langgraph/agents/",
        "https://reference.langchain.com/python/langgraph/supervisor/",
        "https://reference.langchain.com/python/langgraph/swarm/",
        "https://reference.langchain.com/python/langgraph/graphs/",
        "https://reference.langchain.com/python/langgraph/func/",
        "https://reference.langchain.com/python/langgraph/pregel/",
        "https://reference.langchain.com/python/langgraph/checkpoints/",
        "https://reference.langchain.com/python/langgraph/store/",
        "https://reference.langchain.com/python/langgraph/cache/",
        "https://reference.langchain.com/python/langgraph/types/",
        "https://reference.langchain.com/python/langgraph/runtime/",
        "https://reference.langchain.com/python/langgraph/config/",
        "https://reference.langchain.com/python/langgraph/errors/",
        "https://reference.langchain.com/python/langgraph/constants/",
        "https://reference.langchain.com/python/langgraph/channels/",
        "https://reference.langchain.com/python/langchain/agents/",
        "https://reference.langchain.com/python/langchain/middleware/",
        "https://reference.langchain.com/python/langchain/messages/",
        "https://reference.langchain.com/python/langchain/tools/",
        "https://reference.langchain.com/python/langchain/embeddings/",
        "https://reference.langchain.com/python/langchain_core/caches/",
        "https://reference.langchain.com/python/langchain_core/callbacks/",
        "https://reference.langchain.com/python/langchain_core/documents/",
        "https://reference.langchain.com/python/langchain_core/document_loaders/",
        "https://reference.langchain.com/python/langchain_core/prompts/",
        "https://reference.langchain.com/python/langchain_core/runnables/",
        "https://reference.langchain.com/python/langchain_core/vectorstores/#langchain_core.vectorstores.base.VectorStore",
        "https://reference.langchain.com/python/deepagents/",
    ]
    
    # LangGraph patterns and multi-agent architectures
    LANGGRAPH_PATTERNS_URLS = [
        "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/agent_supervisor/",
        "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/hierarchical_agent_teams/",
        "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/",
        "https://langchain-ai.github.io/langgraph/how-tos/subgraph/",
        "https://langchain-ai.github.io/langgraph/how-tos/branching/",
        "https://langchain-ai.github.io/langgraph/how-tos/create-react-agent/",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/index",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/subagents",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/skills",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/router",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/custom-workflow",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs-customer-support",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/router-knowledge-base",
        "https://docs.langchain.com/oss/python/langchain/multi-agent/skills-sql-assistant",
        "https://docs.langchain.com/oss/python/langgraph/workflows-agents",

    ]
    
    # LangGraph state management and persistence
    LANGGRAPH_STATE_URLS = [
        "https://langchain-ai.github.io/langgraph/how-tos/persistence/",
        "https://langchain-ai.github.io/langgraph/how-tos/state-model/",
        "https://langchain-ai.github.io/langgraph/how-tos/state-context-key/",
        "https://langchain-ai.github.io/langgraph/concepts/persistence/",
        "https://docs.langchain.com/oss/python/concepts/memory",
        "https://docs.langchain.com/oss/python/concepts/context",
        "https://docs.langchain.com/oss/python/deepagents/long-term-memory",
        "https://docs.langchain.com/oss/python/langgraph/persistence",
        "https://docs.langchain.com/oss/python/langgraph/use-time-travel",
        "https://docs.langchain.com/oss/python/langgraph/add-memory",

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
            # Filter out redirect pages and minimal content
            content = doc.page_content.strip()
            if content and len(content) >= 100 and not self._is_redirect_page(content):
                documents.append(doc)
            elif content and len(content) < 100:
                logging.warning("Skipping %s: content too short (%d chars)", url, len(content))
            elif self._is_redirect_page(content):
                logging.warning("Skipping %s: redirect page detected", url)

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

    def _is_redirect_page(self, content: str) -> bool:
        """Check if the content appears to be a redirect page."""
        # Common redirect patterns
        redirect_indicators = [
            "Redirecting...",
            "Documentation has moved",
            "Redirecting you now",
        ]
        # Check if content is very short and contains redirect keywords
        if len(content) < 200:
            return any(indicator in content for indicator in redirect_indicators)
        return False


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


async def build_index_from_cache(
    cache_path: str = "./data/cached_docs",
    store_path: Optional[str] = None,
    embeddings: Optional[Embeddings] = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> VectorStoreManager:
    """Build vector index from cached documents.
    
    This is useful when you want to rebuild the index without re-scraping
    the documentation (e.g., with a different embedding model).
    
    Parameters
    ----------
    cache_path
        Path to the cached documents directory.
    store_path
        Filesystem path to persist the vector store. Defaults to the
        configured ``vector_store_path``.
    embeddings
        Optional LangChain-compatible embeddings implementation to use.
    chunk_size
        Maximum characters per chunk when splitting documents.
    chunk_overlap
        Overlap size (in characters) between adjacent chunks.
        
    Returns
    -------
    VectorStoreManager
        Manager with the newly created vector store.
    """
    from langgraph_system_generator.rag.cache import DocumentCache
    
    settings = get_settings()
    destination = store_path or settings.vector_store_path
    
    # Load documents from cache
    cache = DocumentCache(cache_path)
    if not cache.exists():
        raise FileNotFoundError(f"No cached documents found at {cache_path}")
    
    documents = cache.load_documents()
    
    # Chunk documents
    indexer = DocsIndexer(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = indexer.chunk_documents(documents)
    
    # Create index
    manager = VectorStoreManager(destination, embeddings=embeddings)
    manager.create_index(chunks)
    return manager
