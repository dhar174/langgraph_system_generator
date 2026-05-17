# LangChain Agents Guide

Current LangChain Python guidance is to use `create_agent(...)` for new agent
implementations. LangChain v1 positions this as the standard replacement for
older prebuilt ReAct helpers.

## Basic agent creation

```python
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic


def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


agent = create_agent(
    model=ChatAnthropic(model="claude-sonnet-4-5-20250929"),
    tools=[get_weather],
    system_prompt="You are a helpful assistant.",
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "What is the weather in SF?"}]}
)
print(result["messages"][-1].content)
```

## Tools

```python
from datetime import datetime

from langchain.tools import tool


@tool
def get_current_time() -> str:
    """Get the current time."""
    return datetime.now().strftime("%H:%M:%S")
```

## Streaming

```python
for step in agent.stream(
    {"messages": [{"role": "user", "content": "Research quantum computing"}]},
    stream_mode="values",
):
    print(step["messages"][-1].content)
```

## Migration note

For most new Python work:

- prefer `langchain.agents.create_agent`
- treat `langgraph.prebuilt.create_react_agent` as a lower-level or migration
  path
- treat `create_tool_calling_agent(...)` as a legacy helper rather than the
  default new entry point

## Resources

- **LangChain docs**: <https://docs.langchain.com>
- **LangChain agents**: <https://docs.langchain.com/oss/python/langchain/agents>
- **LangChain v1 release notes**: <https://docs.langchain.com/oss/python/releases/langchain-v1>
- **LangChain Python API reference**: <https://reference.langchain.com/python>
