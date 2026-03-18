---
name: langchain
description: Framework for building LLM-powered applications with agents, chains, and RAG. Supports multiple providers (OpenAI, Anthropic, Google), ReAct agents, tool calling, memory management, and vector store retrieval. Use for building chatbots, question-answering systems, autonomous agents, or RAG applications.
---

# LangChain - Build LLM Applications with Agents & RAG

LangChain v1 is the fast way to build provider-agnostic agents and
LLM-powered applications. LangChain agents run on top of LangGraph, so you can
start high-level with `create_agent(...)` and drop to LangGraph when you need
more explicit control.

## When to use LangChain

**Use LangChain when you want to:**

- build agents quickly with `create_agent(...)`
- connect to OpenAI, Anthropic, Google, and other providers through dedicated
  integration packages
- add tools, structured output, and retrieval without hand-writing graph
  orchestration
- prototype RAG workflows before dropping into LangGraph for more control

**Use LangGraph instead when you need:**

- explicit stateful workflows with loops, `Command`, and `Send`
- persistence, interrupts, or custom orchestration logic as first-class concerns
- deeper control over node boundaries and execution flow

## Quick start

### Installation

```bash
# Core framework
pip install -U langchain

# Provider integrations
pip install -U langchain-anthropic
pip install -U langchain-openai

# Common RAG extras
pip install -U langchain-community langchain-chroma

# Text splitters package required for current RAG examples
pip install -U langchain-text-splitters
```

Official install docs:

- <https://docs.langchain.com/oss/python/langchain/install>
- <https://docs.langchain.com/oss/python/integrations/providers/overview>

### Basic model usage

```python
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-sonnet-4-5-20250929")
response = llm.invoke("Explain quantum computing in 2 sentences")
print(response.content)
```

### Create an agent

```python
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic


def get_weather(city: str) -> str:
    """Get weather information for a city."""
    return f"It's always sunny in {city}!"


agent = create_agent(
    model=ChatAnthropic(model="claude-sonnet-4-5-20250929"),
    tools=[get_weather],
    system_prompt="You are a helpful assistant. Use tools when needed.",
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "What's the weather in Paris?"}]}
)
print(result["messages"][-1].content)
```

`create_agent(...)` is the current LangChain v1 entry point. Older helper APIs
such as `create_tool_calling_agent(...)`, `create_react_agent(...)`,
`LLMChain`, `RetrievalQA`, and `ConversationBufferMemory` are legacy patterns
or have moved into `langchain-classic`.

## Core concepts

### 1. Models

```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

openai_model = ChatOpenAI(model="gpt-4o")
anthropic_model = ChatAnthropic(model="claude-sonnet-4-5-20250929")
google_model = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
```

### 2. Tools

```python
from langchain.tools import tool


@tool
def search_docs(query: str) -> str:
    """Search product documentation."""
    return f"Search results for: {query}"
```

### 3. Structured output

```python
from pydantic import BaseModel, Field


class WeatherReport(BaseModel):
    city: str = Field(description="City name")
    temperature: float = Field(description="Temperature in Fahrenheit")
    condition: str = Field(description="Weather condition")


structured_llm = llm.with_structured_output(WeatherReport)
report = structured_llm.invoke("Weather in SF: 65F and sunny")
print(report.city, report.temperature, report.condition)
```

## RAG in LangChain v1

The current LangChain docs show two common approaches:

1. **RAG agent**: wrap retrieval in a tool and let `create_agent(...)` decide
   when to call it.
2. **Two-step RAG chain**: retrieve documents first, then pass them to the model
   in a single answer-generation step.

### Minimal indexing example

```python
import bs4

from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

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
```

### Minimal retrieval tool

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

### RAG agent

```python
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic

agent = create_agent(
    model=ChatAnthropic(model="claude-sonnet-4-5-20250929"),
    tools=[retrieve_context],
    system_prompt=(
        "Use the retrieval tool whenever you need grounded context. "
        "If the retrieved context is not enough, say you do not know."
    ),
)
```

## Text splitters

Current LangChain docs use the standalone `langchain-text-splitters` package:

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)
```

## Persistence and LangGraph relationship

- LangChain is the recommended starting point for high-level agent loops.
- LangGraph is the lower-level orchestration runtime beneath LangChain agents.
- For persistence in LangGraph, the current in-memory checkpointer is
  `InMemorySaver`, with separate SQLite and Postgres integrations for durable
  backends.

## Best practices

1. Start with `create_agent(...)` for new agent work.
2. Prefer provider packages such as `langchain-openai` or
   `langchain-anthropic` over older monolithic integrations.
3. Use `langchain-text-splitters` for current splitter examples.
4. Treat `langchain-classic` as the home for legacy helpers you still need to
   keep around during migrations.
5. Use LangSmith or another trace workflow once an agent has multiple tools,
   branching behavior, or enough reasoning steps that debugging from final
   output alone is no longer practical.

## References

- **[Agents Guide](references/agents.md)** - current agent APIs and migration notes
- **[RAG Guide](references/rag.md)** - indexing, retrieval tools, and RAG agents
- **[Integration Guide](references/integration.md)** - providers, vector stores, and observability

## Resources

- **Docs**: <https://docs.langchain.com>
- **LangChain overview**: <https://docs.langchain.com/oss/python/langchain/overview>
- **LangChain install guide**: <https://docs.langchain.com/oss/python/langchain/install>
- **LangChain RAG guide**: <https://docs.langchain.com/oss/python/langchain/rag>
- **LangGraph overview**: <https://docs.langchain.com/oss/python/langgraph/overview>
- **API Reference**: <https://reference.langchain.com/python>
