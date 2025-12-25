#!/usr/bin/env python3
"""Script to pre-fetch and cache documentation locally.

This script uses the DocsIndexer to fetch documentation from configured URLs
and saves them to a local cache directory for offline access and faster loading.

Usage:
    python scripts/precache_docs.py [--output-dir DATA_DIR] [--urls URL1 URL2 ...]
"""

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import List, Optional

# Add the src directory to the path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langgraph_system_generator.rag.indexer import DocsIndexer
from langchain_core.documents import Document


def sanitize_filename(text: str, max_length: int = 100) -> str:
    """Convert a string to a safe filename.
    
    Args:
        text: The text to convert to a filename
        max_length: Maximum length of the filename (default: 100)
        
    Returns:
        A sanitized filename safe for use on most filesystems
    """
    # Remove or replace unsafe characters
    text = re.sub(r'[<>:"/\\|?*]', '_', text)
    # Replace spaces with underscores
    text = text.replace(' ', '_')
    # Remove multiple underscores
    text = re.sub(r'_+', '_', text)
    # Remove leading/trailing underscores and dots
    text = text.strip('_.')
    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]
    return text or "untitled"


def generate_filename_from_url(url: str) -> str:
    """Generate a filename from a URL.
    
    Args:
        url: The URL to generate a filename from
        
    Returns:
        A sanitized filename based on the URL path
    """
    # Extract the path component from the URL
    path_parts = url.rstrip('/').split('/')
    # Use the last meaningful parts of the path
    relevant_parts = [p for p in path_parts[-3:] if p and p not in ('https:', 'http:', '')]
    filename_base = '_'.join(relevant_parts)
    return sanitize_filename(filename_base)


def save_document(doc: Document, output_dir: Path) -> Path:
    """Save a document to disk.
    
    Args:
        doc: The document to save
        output_dir: The directory to save the document in
        
    Returns:
        Path to the saved file
    """
    # Try to generate a meaningful filename
    source_url = doc.metadata.get('source', '')
    title = doc.metadata.get('title', '')
    heading = doc.metadata.get('heading', '')
    
    # Prefer title or heading, fallback to URL-based name
    if title:
        filename_base = sanitize_filename(title)
    elif heading:
        filename_base = sanitize_filename(heading)
    elif source_url:
        filename_base = generate_filename_from_url(source_url)
    else:
        filename_base = "untitled"
    
    # Ensure unique filename
    output_path = output_dir / f"{filename_base}.txt"
    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{filename_base}_{counter}.txt"
        counter += 1
    
    # Write the document content
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write metadata as a header
        f.write("=" * 80 + "\n")
        f.write("METADATA\n")
        f.write("=" * 80 + "\n")
        for key, value in doc.metadata.items():
            f.write(f"{key}: {value}\n")
        f.write("=" * 80 + "\n\n")
        
        # Write the content
        f.write(doc.page_content)
    
    return output_path


async def main(
    output_dir: Optional[Path] = None,
    urls: Optional[List[str]] = None,
) -> int:
    """Main function to fetch and cache documentation.
    
    Args:
        output_dir: Directory to save cached documents (default: data/docs_cache)
        urls: Optional list of URLs to fetch (default: use DocsIndexer defaults)
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Determine output directory
    if output_dir is None:
        repo_root = Path(__file__).parent.parent
        output_dir = repo_root / "data" / "docs_cache"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Caching documentation to: {output_dir}")
    
    # Create the indexer
    if urls:
        logger.info(f"Fetching {len(urls)} custom URLs")
        indexer = DocsIndexer(urls=urls)
    else:
        logger.info(f"Fetching {len(DocsIndexer.DOCS_URLS)} default documentation URLs")
        indexer = DocsIndexer()
    
    # Fetch the documents
    logger.info("Scraping documentation...")
    try:
        documents = await indexer.scrape_docs()
    except Exception as e:
        logger.error(f"Failed to scrape documentation: {e}")
        return 1
    
    if not documents:
        logger.warning("No documents were fetched")
        return 1
    
    logger.info(f"Successfully fetched {len(documents)} documents")
    
    # Save each document
    saved_files = []
    for i, doc in enumerate(documents, 1):
        try:
            output_path = save_document(doc, output_dir)
            saved_files.append(output_path)
            logger.info(f"[{i}/{len(documents)}] Saved: {output_path.name}")
        except Exception as e:
            source = doc.metadata.get('source', 'unknown')
            logger.error(f"[{i}/{len(documents)}] Failed to save document from {source}: {e}")
    
    # Print summary
    logger.info("=" * 80)
    logger.info(f"Documentation caching complete!")
    logger.info(f"Successfully saved {len(saved_files)} out of {len(documents)} documents")
    logger.info(f"Cache directory: {output_dir}")
    logger.info("=" * 80)
    
    return 0 if saved_files else 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Pre-fetch and cache documentation locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Directory to save cached documents (default: data/docs_cache)',
    )
    parser.add_argument(
        '--urls',
        nargs='+',
        help='Custom URLs to fetch (default: use DocsIndexer defaults)',
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    exit_code = asyncio.run(main(
        output_dir=args.output_dir,
        urls=args.urls,
    ))
    sys.exit(exit_code)
