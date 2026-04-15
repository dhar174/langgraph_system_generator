# LangChain Integration Guide

Integration with vector stores, LangSmith observability, hosted APIs, local
open-source models, and deployment patterns.

LangChain v1 keeps provider integrations in dedicated packages so model, vector
store, and utility dependencies can evolve independently. For LNF-style agent
projects, that means you can keep the orchestration layer stable while swapping
between hosted APIs and local model runtimes as needed.

## Provider packages

```bash
# Hosted APIs
pip install -U langchain-openai
pip install -U langchain-anthropic
pip install -U langchain-google-genai

# Local open-source models via Ollama (for Llama-family models and similar)
pip install -U langchain-ollama
```

`langchain-openai` covers both standard OpenAI endpoints and Azure OpenAI
deployments.

## Environment setup

Set the environment variables for the provider you plan to use before building
agents or API services.

```bash
export OPENAI_API_KEY=your-openai-key
export ANTHROPIC_API_KEY=your-anthropic-key
export LANGCHAIN_API_KEY=your-langsmith-api-key
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

### Chroma (local, open-source)

```python
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

vectorstore = Chroma.from_documents(
    documents=docs,
    embedding=OpenAIEmbeddings(),
    persist_directory="./chroma_db",
)
```

### FAISS (fast local similarity search)

FAISS remains a practical default for local retrieval pipelines and is the main
vector-store backend used by this repository's cached-docs workflow.

```python
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

vectorstore = FAISS.from_documents(docs, OpenAIEmbeddings())
vectorstore.save_local("faiss_index")
```

### Pinecone (managed cloud index)

```python
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings

vectorstore = PineconeVectorStore.from_documents(
    documents=docs,
    embedding=OpenAIEmbeddings(),
    index_name="my-index",
)
```

### Weaviate (production, ML-native)

```python
from langchain_weaviate import WeaviateVectorStore
```

### Qdrant (fast, open-source)

```python
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
```

## Model integrations

### OpenAI

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4o")
```

### Anthropic

```python
from langchain_anthropic import ChatAnthropic

model = ChatAnthropic(model="claude-sonnet-4-5-20250929")
```

### Google

```python
from langchain_google_genai import ChatGoogleGenerativeAI

model = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
```

### Azure OpenAI

```python
from langchain_openai import AzureChatOpenAI
```

### Local models (Ollama / Llama-family)

For local or Docker-based development, LangChain can target Llama-family and
other open-source models exposed through Ollama. This is useful for character or
simulation workloads that need to run without external API calls.

```python
from langchain_ollama import ChatOllama

model = ChatOllama(model="llama3.1")
```

## LangSmith observability

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=your-langsmith-api-key
export LANGCHAIN_PROJECT=my-project
# Keep real keys out of source control.
```

```python
import os

if not os.getenv("LANGCHAIN_API_KEY"):
    raise RuntimeError(
        "Set LANGCHAIN_API_KEY in your environment before running traced LangChain workloads."
    )
```

## API and application integration patterns

### FastAPI server

```python
from fastapi import FastAPI
from pydantic import BaseModel
from langchain.agents import create_agent
```

### Streaming responses

```python
from fastapi.responses import StreamingResponse
from langchain.callbacks import AsyncIteratorCallbackHandler
```

### Hosted API vs local-model deployments

For workloads like simulation, roleplay, or character-agent systems, keep the
LangChain app code the same and swap only the model integration:

- use hosted APIs such as OpenAI or Anthropic when you want managed models and
  simpler operations
- use local open-source models through Ollama when you need offline execution,
  tighter cost control, or Docker-contained development environments

## Docker deployment

### App container

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Local model sidecar / separate service

A common pattern is to run the application container separately from an Ollama
container that serves local Llama-family models.

```yaml
services:
  app:
    build: .
    environment:
      OLLAMA_HOST: http://ollama:11434
    depends_on:
      - ollama

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
```

## Deployment note

LangChain agents are built on LangGraph, so once you outgrow the default agent
loop you can keep your provider and tool integrations and move the orchestration
into LangGraph without changing your model stack.

## Best practices

1. **Pick the model runtime last** - design around tools, retrieval, and state,
   then decide whether the best fit is a hosted API or a local model.
2. **Keep FAISS/Chroma for local workflows** - they are convenient for notebook
   demos, doc retrieval, and Docker-friendly development loops.
3. **Use LangSmith in production** - tracing becomes important once you have
   multiple tools, branching behavior, or multi-step reasoning.
4. **Set timeouts and retries** - both hosted APIs and local model servers can
   stall or fail transiently.
5. **Containerize the boundaries** - run your API server and any local model
   runtime as separate services when you need predictable local orchestration.

## Resources

- **LangChain docs**: <https://docs.langchain.com>
- **Provider integrations**: <https://docs.langchain.com/oss/python/integrations/providers/overview>
- **LangChain API reference**: <https://reference.langchain.com/python>
- **LangGraph overview**: <https://docs.langchain.com/oss/python/langgraph/overview>
- **LangSmith**: <https://smith.langchain.com>
- **Text splitters**: <https://docs.langchain.com/oss/python/integrations/splitters/index>
