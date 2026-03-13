# LangChain Integration Guide

Integration with vector stores, LangSmith observability, and deployment.

## Vector store integrations

### Chroma (local, open-source)

```python
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
```

### Pinecone (cloud, scalable)

```python
from langchain_pinecone import PineconeVectorStore
import pinecone
```

### FAISS (fast similarity search)

```python
from langchain_community.vectorstores import FAISS
```

### Weaviate (production, ML-native)

```python
from langchain_weaviate import WeaviateVectorStore
import weaviate
```

### Qdrant (fast, open-source)

```python
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
```

## LangSmith observability

### Enable tracing

```python
import os

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "your-langsmith-api-key"
os.environ["LANGCHAIN_PROJECT"] = "my-project"
```

## Deployment patterns

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

### Docker deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langchain-app
spec:
  replicas: 3
```

## Model integrations

### OpenAI

```python
from langchain_openai import ChatOpenAI
```

### Anthropic

```python
from langchain_anthropic import ChatAnthropic
```

### Google

```python
from langchain_google_genai import ChatGoogleGenerativeAI
```

### Local models (Ollama)

```python
from langchain_community.llms import Ollama
```

### Azure OpenAI

```python
from langchain_openai import AzureChatOpenAI
```

## Best practices

1. **Use LangSmith in production** - Essential for debugging
2. **Cache aggressively** - LLM calls are expensive
3. **Set timeouts** - Prevent hanging requests
4. **Add retries** - Handle transient failures
5. **Monitor costs** - Track token usage

## Resources

- **LangSmith**: https://smith.langchain.com
- **Vector Stores**: https://python.langchain.com/docs/integrations/vectorstores
- **Model Providers**: https://python.langchain.com/docs/integrations/llms
- **Tools**: https://python.langchain.com/docs/integrations/tools
- **Deployment Guide**: https://docs.langchain.com/deploy
