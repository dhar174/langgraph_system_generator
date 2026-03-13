# LangChain RAG Guide

Complete guide to Retrieval-Augmented Generation with LangChain.

## What is RAG?

**RAG (Retrieval-Augmented Generation)** combines:
1. **Retrieval**: Find relevant documents from knowledge base
2. **Generation**: LLM generates answer using retrieved context

**Benefits**:
- Reduce hallucinations
- Up-to-date information
- Domain-specific knowledge
- Source citations

## RAG pipeline components

### 1. Document loading

```python
from langchain_community.document_loaders import (
    WebBaseLoader,
    PyPDFLoader,
    TextLoader,
    DirectoryLoader,
    CSVLoader,
    UnstructuredMarkdownLoader
)
```

### 2. Text splitting

```python
from langchain.text_splitter import (
    RecursiveCharacterTextSplitter,
    CharacterTextSplitter,
    TokenTextSplitter
)
```

### 3. Embeddings

```python
from langchain_openai import OpenAIEmbeddings
```

### 4. Vector stores

```python
from langchain_chroma import Chroma
from langchain_community.vectorstores import FAISS
from langchain_pinecone import PineconeVectorStore
```

### 5. Retrieval

```python
retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 4}
)
```

### 6. QA chain

```python
from langchain.chains import RetrievalQA
from langchain_anthropic import ChatAnthropic
```

## Advanced RAG patterns

### Conversational RAG

```python
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
```

### Multi-query retrieval

```python
from langchain.retrievers import MultiQueryRetriever
```

### Contextual compression

```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor
```

### Ensemble retrieval (hybrid search)

```python
from langchain.retrievers import EnsembleRetriever
from langchain.retrievers import BM25Retriever
```

## Best practices

1. **Chunk size matters** - 512-1024 tokens is usually optimal
2. **Add overlap** - 10-20% overlap prevents context loss
3. **Use metadata** - Track sources for citations
4. **Test retrieval quality** - Evaluate before using in production
5. **Hybrid search** - Combine vector + keyword for best results

## Resources

- **LangChain RAG Docs**: https://docs.langchain.com/oss/python/langchain/rag
- **Vector Stores**: https://python.langchain.com/docs/integrations/vectorstores
- **Document Loaders**: https://python.langchain.com/docs/integrations/document_loaders
- **Retrievers**: https://python.langchain.com/docs/modules/data_connection/retrievers
