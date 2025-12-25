#!/usr/bin/env python3
"""Script to pre-fetch and cache documentation locally.

This script scrapes documentation from configured URLs and saves the content
to local files in the data/docs_cache directory. This allows the documentation
to be pre-cached in the repository for offline use or to avoid repeated network
requests.

Usage:
    python scripts/precache_docs.py

Note: This script has minimal dependencies (aiohttp, beautifulsoup4, langchain_core)
and doesn't require the full vector store dependencies.
"""

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import List
from urllib.parse import urlparse

try:
    import aiohttp
    from bs4 import BeautifulSoup
    from langchain_core.documents import Document
except ImportError as e:
    print(f"Error: Missing required dependency: {e}")
    print("\nPlease install required packages:")
    print("  pip install aiohttp beautifulsoup4 langchain-core")
    sys.exit(1)

# Add the src directory to the path to allow imports if needed
repo_root = Path(__file__).parent.parent

# Documentation URLs to fetch (same as DocsIndexer.DOCS_URLS)
# To customize which documentation to cache, modify these URL lists below:
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


def sanitize_filename(url: str) -> str:
    """Convert a URL to a safe filename.
    
    Args:
        url: The URL to convert
        
    Returns:
        A sanitized filename suitable for saving to disk
    """
    # Parse the URL
    parsed = urlparse(url)
    
    # Use the path component, replacing slashes with underscores
    path = parsed.path.strip("/").replace("/", "_")
    
    # If path is empty, use the domain
    if not path:
        path = parsed.netloc.replace(".", "_")
    
    # Remove or replace any remaining unsafe characters
    safe_name = re.sub(r'[^\w\-_.]', '_', path)
    
    # Add .txt extension if not present
    if not safe_name.endswith('.txt'):
        safe_name += '.txt'
    
    return safe_name


def html_to_document(html: str, source: str) -> Document:
    """Convert HTML to a Document object (same logic as DocsIndexer._html_to_document).
    
    Args:
        html: The HTML content
        source: The source URL
        
    Returns:
        A Document object with extracted text and metadata
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, and noscript tags
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Extract title
    title = (
        soup.title.string.strip() if soup.title and soup.title.string else None
    )
    
    # Extract first heading
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


async def fetch_url(session: aiohttp.ClientSession, url: str, timeout: float = 30.0) -> str:
    """Fetch a URL and return its content.
    
    Args:
        session: The aiohttp session
        url: The URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        The HTML content of the page
    """
    async with session.get(url, timeout=timeout) as response:
        response.raise_for_status()
        return await response.text()


async def scrape_docs(urls: List[str]) -> List[Document]:
    """Scrape documentation pages and convert them to documents.
    
    Args:
        urls: List of URLs to scrape
        
    Returns:
        List of Document objects
    """
    if not urls:
        return []

    async with aiohttp.ClientSession() as session:
        responses = await asyncio.gather(
            *[fetch_url(session, url) for url in urls],
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


async def main():
    """Main function to fetch and cache documentation."""
    print("Starting documentation pre-fetch and cache process...")
    print(f"Repository root: {repo_root}")
    
    # Create output directory if it doesn't exist
    output_dir = repo_root / "data" / "docs_cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    # Show URLs to fetch
    print(f"\nFetching {len(DOCS_URLS)} documentation URLs:")
    for url in DOCS_URLS:
        print(f"  - {url}")
    
    # Scrape the documentation
    print("\nScraping documentation...")
    try:
        documents = await scrape_docs(DOCS_URLS)
        print(f"Successfully scraped {len(documents)} documents")
    except Exception as e:
        print(f"Error scraping documents: {e}")
        return 1
    
    # Save each document to disk
    print("\nSaving documents to cache...")
    saved_count = 0
    for doc in documents:
        source_url = doc.metadata.get("source", "unknown")
        filename = sanitize_filename(source_url)
        filepath = output_dir / filename
        
        try:
            # Create content with metadata header
            content_lines = [
                "=" * 80,
                f"Source: {source_url}",
            ]
            
            if "title" in doc.metadata:
                content_lines.append(f"Title: {doc.metadata['title']}")
            
            if "heading" in doc.metadata:
                content_lines.append(f"Heading: {doc.metadata['heading']}")
            
            content_lines.extend([
                "=" * 80,
                "",
                doc.page_content
            ])
            
            content = "\n".join(content_lines)
            
            # Write to file
            filepath.write_text(content, encoding="utf-8")
            print(f"  ✓ Saved: {filename} ({len(doc.page_content)} chars)")
            saved_count += 1
        except Exception as e:
            print(f"  ✗ Error saving {filename}: {e}")
    
    print(f"\nCompleted! Successfully saved {saved_count}/{len(documents)} documents")
    print(f"Documentation cached in: {output_dir}")
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
