#!/usr/bin/env python
"""Demonstration of precached documentation usage.

This script shows how to use the precached LangGraph/LangChain documentation
without needing to scrape or have an OpenAI API key (for demo purposes).
"""

from langgraph_system_generator.rag.cache import DocumentCache


def main() -> None:
    """Demonstrate loading and using cached documentation."""
    print("=" * 70)
    print("Precached Documentation Demo")
    print("=" * 70)
    
    # Load cached documents
    print("\n1. Loading cached documents...")
    cache = DocumentCache("./data/cached_docs")
    
    if not cache.exists():
        print("ERROR: No cached documents found!")
        print("Run 'python scripts/build_index.py' to scrape documentation.")
        return
    
    documents = cache.load_documents()
    print(f"✓ Loaded {len(documents)} documents")
    
    # Show statistics
    print("\n2. Documentation statistics:")
    total_chars = sum(len(doc.page_content) for doc in documents)
    print(f"   Total content: {total_chars:,} characters")
    
    sources = set(doc.metadata.get("source", "") for doc in documents)
    langgraph_count = sum(1 for s in sources if "langgraph" in s.lower())
    langchain_count = sum(1 for s in sources if "langchain" in s.lower() and "langgraph" not in s.lower())
    print(f"   LangGraph sources: {langgraph_count}")
    print(f"   LangChain sources: {langchain_count}")
    
    # Show sample documents
    print("\n3. Sample documents:")
    for i, doc in enumerate(documents[:3], 1):
        source = doc.metadata.get("source", "Unknown")
        title = doc.metadata.get("title", "No title")
        content_preview = doc.page_content[:100].replace("\n", " ")
        
        print(f"\n   Document {i}:")
        print(f"   Source: {source}")
        print(f"   Title: {title}")
        print(f"   Content: {content_preview}...")
    
    # Show topics covered
    print("\n4. Topics covered:")
    topics = set()
    for doc in documents:
        source = doc.metadata.get("source", "").lower()
        if "multi_agent" in source or "multi-agent" in source:
            topics.add("Multi-agent architectures")
        if "state" in source:
            topics.add("State management")
        if "persistence" in source:
            topics.add("Persistence & checkpointing")
        if "streaming" in source:
            topics.add("Streaming")
        if "async" in source:
            topics.add("Async operations")
        if "tutorial" in source:
            topics.add("Tutorials & examples")
        if "concept" in source:
            topics.add("Core concepts")
        if "agent" in source and "multi" not in source:
            topics.add("Agent patterns")
        if "rag" in source or "retriev" in source:
            topics.add("RAG & retrieval")
    
    for topic in sorted(topics):
        print(f"   • {topic}")
    
    print("\n" + "=" * 70)
    print("Next steps:")
    print("=" * 70)
    print("To build a searchable vector index from these documents:")
    print("1. Set OPENAI_API_KEY in your .env file")
    print("2. Run: python scripts/build_index.py")
    print("\nThis will create a FAISS index for semantic search.")


if __name__ == "__main__":
    main()
