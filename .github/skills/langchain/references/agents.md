# LangChain Agents Guide

Complete guide to building agents with ReAct, tool calling, and streaming.

## What are agents?

Agents combine language models with tools to solve complex tasks through reasoning and action:

1. **Reasoning**: LLM decides what to do
2. **Acting**: Execute tools based on reasoning
3. **Observation**: Receive tool results
4. **Loop**: Repeat until task complete

This is the **ReAct pattern** (Reasoning + Acting).

## Basic agent creation

```python
import ast
import operator as op

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic

# Define tools
_ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
}


def calculator(expression: str) -> str:
    """Evaluate a basic math expression safely."""

    def _evaluate(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
            return _ALLOWED_OPERATORS[type(node.op)](
                _evaluate(node.left), _evaluate(node.right)
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
            return _ALLOWED_OPERATORS[type(node.op)](_evaluate(node.operand))
        raise ValueError("Only basic arithmetic expressions are supported.")

    try:
        return str(_evaluate(ast.parse(expression, mode="eval").body))
    except ZeroDivisionError as exc:
        raise ValueError("Division by zero is not supported.") from exc

def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

# Create agent
agent = create_agent(
    model=ChatAnthropic(model="claude-sonnet-4-5-20250929"),
    tools=[calculator, search],
    system_prompt="You are a helpful assistant. Use tools when needed."
)

# Run agent
result = agent.invoke({
    "messages": [{"role": "user", "content": "What is 25 * 17?"}]
})
print(result["messages"][-1].content)
```

## Agent components

### 1. Model - The reasoning engine

```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
```

### 2. Tools - Actions the agent can take

```python
from langchain.tools import tool

@tool
def get_current_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")
```

### 3. System prompt - Agent behavior

```python
system_prompt = "You are a helpful assistant. Use tools when needed."
```

## Agent types

### 1. Tool-calling agent (recommended)

```python
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.prompts import ChatPromptTemplate
```

### 2. ReAct agent (reasoning trace)

```python
from langchain.agents import create_react_agent
```

## Tool execution patterns

### Parallel tool execution

```python
agent = create_tool_calling_agent(llm=model, tools=[get_weather, search])
```

### Sequential tool chaining

```python
@tool
def search_company(name: str) -> str:
    """Search for company information."""
    return "Company ID: 12345, Industry: Tech"
```

## Streaming

### Stream agent steps

```python
for step in agent_executor.stream({"input": "Research quantum computing"}):
    if "actions" in step:
        action = step["actions"][0]
        print(f"Tool: {action.tool}, Input: {action.tool_input}")
```

## Error handling

### Tool error handling

```python
@tool
def fallible_tool(query: str) -> str:
    """A tool that might fail."""
    try:
        result = risky_operation(query)
        return f"Success: {result}"
    except Exception as e:
        return f"Error: {str(e)}. Please try a different approach."
```

## Best practices

1. **Use tool-calling agents** - Fastest and most reliable
2. **Keep tool descriptions clear** - Agent needs to understand when to use each tool
3. **Add error handling** - Tools will fail, handle gracefully
4. **Set max_iterations** - Prevent infinite loops
5. **Enable streaming** - Better UX for long tasks

## Resources

- **ReAct Paper**: https://arxiv.org/abs/2210.03629
- **LangChain Agents Docs**: https://docs.langchain.com/oss/python/langchain/agents
- **LangSmith Debugging**: https://smith.langchain.com
