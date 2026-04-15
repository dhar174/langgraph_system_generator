# LangChain RAG Guide

LangChain v1 documents two recommended RAG shapes:

1. **RAG agent**: expose retrieval as a tool and let an agent decide when to
   call it
2. **Two-step RAG chain**: retrieve first, then answer in a single model call

## Indexing pipeline

```python
import bs4

from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings

loader = WebBaseLoader(
    web_paths=("https://lilianweng.github.io/posts/2023-06-23-agent/",),
    bs_kwargs={
        "parse_only": bs4.SoupStrainer(
            class_=("post-content", "post-title", "post-header")
        )
    },
)
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    add_start_index=True,
)
splits = splitter.split_documents(docs)

embedding_model = OpenAIEmbeddings()
vector_store = InMemoryVectorStore(embedding=embedding_model)
vector_store.add_documents(splits)
```

## Retrieval tool

```python
from langchain.tools import tool


@tool(response_format="content_and_artifact")
def retrieve_context(query: str):
    """Retrieve information to help answer a query."""
    retrieved_docs = vector_store.similarity_search(query, k=2)
    serialized = "\n\n".join(
        f"Source: {doc.metadata}\nContent: {doc.page_content}"
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs
```

## RAG agent

```python
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic

agent = create_agent(
    model=ChatAnthropic(model="claude-sonnet-4-5-20250929"),
    tools=[retrieve_context],
    system_prompt=(
        "Use the retrieval tool to ground answers in the indexed corpus. "
        "If the context is insufficient, say you do not know."
    ),
)
```

## Text splitters

Current splitter docs use the standalone `langchain-text-splitters` package:

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter
```

## Best practices

1. Keep indexing and query-time retrieval conceptually separate.
2. Track source metadata so answers can cite their origin.
3. Use a retrieval tool when you want agentic control over when retrieval runs.
4. Use a two-step chain when you want predictable latency and exactly one model
   generation pass.

## Resources

- **LangChain RAG guide**: <https://docs.langchain.com/oss/python/langchain/rag>
- **Retrieval with agents overview**: <https://docs.langchain.com/oss/python/langchain/retrieval>
- **Text splitters**: <https://docs.langchain.com/oss/python/integrations/splitters/index>
- **API Reference**: <https://reference.langchain.com/python>
