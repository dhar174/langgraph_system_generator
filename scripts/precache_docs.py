#!/usr/bin/env python3
"""Pre-fetch and cache documentation locally.

This script fetches documentation from configured URLs and saves them to a
local cache directory. This allows keeping documentation in the repository
for offline access or faster loading.

Usage:
    python scripts/precache_docs.py
    python scripts/precache_docs.py --output-dir PATH
    python scripts/precache_docs.py --urls URL1 URL2 ...
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup
from langchain_core.documents import Document


# Default documentation URLs (copied from DocsIndexer)
PYTHON_DOCS_URLS = [
    "https://docs.langchain.com/oss/python/langgraph/use-graph-api",
    "https://docs.langchain.com/oss/python/langchain/multi-agent/subagents",
    "https://docs.langchain.com/oss/python/langchain/agents",
]
JAVASCRIPT_DOCS_URLS = [
    "https://docs.langchain.com/oss/javascript/langchain/multi-agent/router",
    "https://docs.langchain.com/oss/javascript/langgraph/persistence",
]
DEFAULT_DOCS_URLS = PYTHON_DOCS_URLS + JAVASCRIPT_DOCS_URLS


def sanitize_filename(text: str) -> str:
    """Create a safe filename from a URL or text.
    
    Args:
        text: Input text (typically a URL or title)
        
    Returns:
        Sanitized filename safe for filesystem use
    """
    # Remove protocol and www
    text = re.sub(r'^https?://(www\.)?', '', text)
    # Replace non-alphanumeric characters with underscores
    text = re.sub(r'[^\w\s-]', '_', text)
    # Replace whitespace with underscores
    text = re.sub(r'[\s]+', '_', text)
    # Remove consecutive underscores
    text = re.sub(r'_{2,}', '_', text)
    # Trim underscores from ends
    text = text.strip('_')
    # Limit length
    if len(text) > 200:
        text = text[:200]
    return text


async def fetch_url(
    session: aiohttp.ClientSession, url: str, timeout: float = 30.0
) -> str:
    """Fetch content from a URL.
    
    Args:
        session: aiohttp client session
        url: URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        HTML content as string
    """
    async with session.get(url, timeout=timeout) as response:
        response.raise_for_status()
        return await response.text()


def html_to_document(html: str, source: str) -> Document:
    """Convert HTML to a Document object.
    
    Args:
        html: HTML content
        source: Source URL
        
    Returns:
        Document object with extracted text and metadata
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, and noscript tags
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Extract title
    title = (
        soup.title.string.strip() if soup.title and soup.title.string else None
    )
    
    # Extract heading
    heading = None
    heading_tag = soup.find(
        lambda tag: tag.name in ("h1", "h2", "h3") and tag.get_text(strip=True)
    )
    if heading_tag:
        heading = heading_tag.get_text(strip=True)

    # Extract and clean text
    text = soup.get_text("\n", strip=True)
    cleaned_lines = [line for line in (ln.strip() for ln in text.splitlines()) if line]
    content = "\n".join(cleaned_lines)

    # Build metadata
    metadata = {"source": source}
    if title:
        metadata["title"] = title
    if heading:
        metadata["heading"] = heading

    return Document(page_content=content, metadata=metadata)


async def scrape_docs(urls: List[str], timeout: float = 30.0) -> List[Document]:
    """Scrape documentation pages and convert them to documents.
    
    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        
    Returns:
        List of Document objects
    """
    if not urls:
        return []

    async with aiohttp.ClientSession() as session:
        responses = await asyncio.gather(
            *[fetch_url(session, url, timeout) for url in urls],
            return_exceptions=True,
        )

    documents: List[Document] = []
    for url, result in zip(urls, responses):
        if isinstance(result, Exception):
            logging.warning("Failed to fetch %s: %s", url, result)
            continue
        doc = html_to_document(result, url)
        if doc.page_content.strip():
            documents.append(doc)

    return documents


def save_documents_to_cache(
    documents: List[Document],
    output_dir: Path,
) -> None:
    """Save fetched documents to local cache directory.
    
    Args:
        documents: List of Document objects from DocsIndexer
        output_dir: Directory to save cached documents
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Track metadata for all cached documents
    cache_metadata = []
    
    print(f"\nSaving {len(documents)} documents to {output_dir}")
    
    for idx, doc in enumerate(documents):
        # Generate filename from URL
        source_url = doc.metadata.get("source", f"document_{idx}")
        filename = sanitize_filename(source_url)
        
        # Ensure unique filenames
        base_filename = filename
        counter = 1
        while (output_dir / f"{filename}.txt").exists():
            filename = f"{base_filename}_{counter}"
            counter += 1
        
        # Save document content
        doc_path = output_dir / f"{filename}.txt"
        doc_path.write_text(doc.page_content, encoding="utf-8")
        
        # Track metadata
        doc_metadata = {
            "filename": f"{filename}.txt",
            "source": source_url,
            "title": doc.metadata.get("title"),
            "heading": doc.metadata.get("heading"),
            "size_bytes": len(doc.page_content.encode("utf-8")),
        }
        cache_metadata.append(doc_metadata)
        
        print(f"  ✓ Saved: {filename}.txt (source: {source_url})")
    
    # Save metadata index
    metadata_path = output_dir / "cache_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(cache_metadata, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved metadata index: {metadata_path}")
    print(f"✓ Total documents cached: {len(documents)}")


async def main():
    """Main entry point for the documentation pre-caching script."""
    parser = argparse.ArgumentParser(
        description="Pre-fetch and cache documentation locally"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "docs_cache",
        help="Directory to save cached documentation (default: data/docs_cache)",
    )
    parser.add_argument(
        "--urls",
        nargs="*",
        help="Specific URLs to fetch (default: use DEFAULT_DOCS_URLS)",
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Documentation Pre-Caching Script")
    print("=" * 60)
    
    # Determine URLs to fetch
    urls = args.urls if args.urls else DEFAULT_DOCS_URLS
    print(f"\nFetching {len(urls)} documentation URLs...")
    
    # Display URLs being fetched
    print("\nURLs to fetch:")
    for url in urls:
        print(f"  • {url}")
    
    # Fetch documents
    print("\nFetching documentation...")
    documents = await scrape_docs(urls)
    
    if not documents:
        print("\n⚠ Warning: No documents were successfully fetched.")
        return 1
    
    print(f"✓ Successfully fetched {len(documents)} documents")
    
    # Save to cache
    save_documents_to_cache(documents, args.output_dir)
    
    print("\n" + "=" * 60)
    print("Documentation caching complete!")
    print("=" * 60)
    print(f"\nCached files are stored in: {args.output_dir}")
    print("These files can now be committed to the repository for offline access.")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
