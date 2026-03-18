# LangChain Integration Guide

LangChain v1 keeps provider integrations in dedicated packages so model, vector
store, and utility dependencies can evolve independently.

## Provider packages

```bash
pip install -U langchain-openai
pip install -U langchain-anthropic
pip install -U langchain-google-genai
```

## Vector store integrations

First, create or load some `Document` objects. For example:

```python
from langchain_core.documents import Document

docs = [
    Document(
        page_content="LangChain makes it easy to build LLM-powered applications.",
        metadata={"source": "integration_guide"},
    )
]
```

```python
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

vectorstore = Chroma.from_documents(
    documents=docs,
    embedding=OpenAIEmbeddings(),
    persist_directory="./chroma_db",
)
```

```python
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

vectorstore = FAISS.from_documents(docs, OpenAIEmbeddings())
```

## LangSmith observability

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=your-langsmith-api-key
export LANGCHAIN_PROJECT=my-project
```

## Deployment note

LangChain agents are built on LangGraph, so once you outgrow the default agent
loop you can keep your provider and tool integrations and move the orchestration
into LangGraph without changing your model stack.

## Resources

- **LangChain docs**: <https://docs.langchain.com>
- **Provider integrations**: <https://docs.langchain.com/oss/python/integrations/providers/overview>
- **LangChain API reference**: <https://reference.langchain.com/python>
- **LangGraph overview**: <https://docs.langchain.com/oss/python/langgraph/overview>
