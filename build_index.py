import asyncio
from dotenv import load_dotenv
from langgraph_system_generator.rag.indexer import build_docs_index

# Load environment variables (ensure OPENAI_API_KEY is set for embeddings)
load_dotenv()

async def main():
    print("Starting documentation indexing...")
    
    # force_rebuild=True ensures we scrape and overwrite any existing index
    manager = await build_docs_index(
        force_rebuild=True,
        store_path="./data/vector_store"  # Default location
    )
    
    print(f"Successfully indexed documents to: {manager.store_path}")

if __name__ == "__main__":
    asyncio.run(main())