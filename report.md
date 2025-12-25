# Building State‑of‑the‑Art Multi‑Agent Applications with LangGraph (2025)

**LangGraph** is a low‑level orchestration framework for designing long‑running, stateful agents.  It integrates tightly with the **LangChain** ecosystem but can be used standalone.  LangGraph models an application as a directed graph where nodes perform work (e.g., call an LLM or a tool) and edges decide which node runs next.  Because the framework separates state management from logic, you can build robust multi‑agent workflows that persist across failures, stream intermediate results, pause for human feedback and even jump to earlier checkpoints.  This guide summarizes the latest documentation (late‑2025) and shows how to build a modern multi‑agent system using LangGraph.

## Installation & Setup

1. **Install LangGraph and dependencies** – install the base libraries and your chosen LLM integration.  For Anthropic models:

   ```bash
   pip install -U langgraph langchain_core langchain-anthropic
   ```

2. **Provide API keys** – LLM providers require an API key.  When using Anthropic, the docs recommend setting the `ANTHROPIC_API_KEY` environment variable programmatically when it’s not already defined【938974216281041†L100-L124】:

   ```python
   import os, getpass
   if not os.environ.get("ANTHROPIC_API_KEY"):
       os.environ["ANTHROPIC_API_KEY"] = getpass.getpass("ANTHROPIC_API_KEY: ")
   ```

3. **Initialize the chat model** – the example notebooks use the `ChatAnthropic` client:

   ```python
   from langchain_anthropic import ChatAnthropic
   llm = ChatAnthropic(model="claude-sonnet-4-5-20250929")
   ```

4. **Set up LangSmith** (optional but recommended) – LangGraph integrates with LangSmith for tracing, evaluation and observability.  The docs encourage signing up and using trace data to debug and improve agent performance【524036067177045†L88-L110】.

## Core Concepts

### Graphs and the `StateGraph` class

LangGraph represents an agentic system as a graph.  You define the graph using three components【805266789363047†L123-L135】:

1. **State** – a shared data structure that holds the application’s current snapshot (inputs, intermediate results and messages).  It is typically defined as a `TypedDict` or a Pydantic model【805266789363047†L123-L135】.  The schema defines the keys available to every node.

2. **Nodes** – functions that take the current state and return an updated state.  Nodes contain all the work your agent does; they can call an LLM, execute Python code, or invoke external tools.  Node functions simply return a dictionary of updates.  When a node finishes, its updates are merged into the global state using a **reducer** (LangGraph uses an additive reducer by default).

3. **Edges** – transitions that determine which node(s) to run next.  Edges may be **normal** (a fixed next node), **conditional** (choose a node based on the state) or implemented via a **Command** (more on that below).

To create a graph you:

- Instantiate a `StateGraph` with your state schema.
- Add nodes using `add_node(name, func)` (the name defaults to the function name).
- Add edges using `add_edge(source, destination)` or by providing a conditional edge function.
- Compile the graph with `.compile()`.  Compilation performs sanity checks and allows you to configure persistence, checkpointers and breakpoints【805266789363047†L166-L179】.

#### Example: hello‑world graph

```python
from langgraph.graph import StateGraph, START, END
from langgraph.graph import MessagesState  # built‑in schema for message‑based systems

# Define an LLM node that replies "hello world"
def mock_llm(state: MessagesState):
    return {"messages": [{"role": "ai", "content": "hello world"}]}

# Build the graph
graph_builder = StateGraph(MessagesState)
graph_builder.add_node("mock_llm", mock_llm)
# Connect start → node → end
graph_builder.add_edge(START, "mock_llm")
graph_builder.add_edge("mock_llm", END)

# Compile and run
graph = graph_builder.compile()
result = graph.invoke({"messages": [{"role": "user", "content": "hi!"}]})
print(result["messages"][-1])
```

### Functional API

Besides the graph API, LangGraph exposes a **Functional API** that wraps tasks and entrypoints.  It allows you to add LangGraph features (persistence, streaming, memory) to other frameworks.  You decorate functions with `@task` to turn them into tasks that are executed once and cached when resuming durable workflows.  You use `@entrypoint()` to declare the top‑level function that orchestrates the workflow.  This API is especially convenient for multi‑agent networks.

## Building Agents

LangGraph does not impose a particular agent architecture; instead, it provides primitives for building your own.  However, LangChain offers several **prebuilt agent types** (e.g., ReAct) built on top of LangGraph.  The function `create_react_agent(model, tools, prompt)` returns an agent runnable that follows the ReAct pattern and uses the given prompt and tool list【524036067177045†L188-L203】.  When the agent is invoked, it returns a dictionary with a list of `messages` and any `tool_calls` made.  You can embed these agents inside LangGraph nodes or call them via the Functional API.

#### Defining tools

Tools are normal Python functions decorated with `@tool` from `langchain_core.tools`.  In ReAct agents you can mark a tool with `return_direct=True` so that the agent exits early when the tool is called, allowing a higher‑level orchestrator to hand off control【524036067177045†L150-L169】.

```python
from langchain_core.tools import tool

@tool(return_direct=True)
def transfer_to_hotel_advisor():
    """Signal that control should transfer to the hotel advisor."""
    return "Successfully transferred to hotel advisor"
```

### Multi‑agent Patterns

LangChain’s advanced multi‑agent guide identifies five patterns for coordinating multiple agents【888862858458267†L116-L154】:

| Pattern | Description | Use Cases |
| --- | --- | --- |
| **Subagents** | A main agent treats subagents as tools.  All routing passes through the main agent which decides when to invoke each subagent【888862858458267†L143-L156】. | Distributed development; simple branching workflows. |
| **Handoffs** | Each agent can call tools that modify state variables.  A state change triggers routing or configuration changes, allowing agents to transfer control【888862858458267†L145-L149】. | Multi‑stage processes where later steps depend on earlier results. |
| **Skills** | A single agent loads specialized knowledge or prompts on demand.  It retains control while “bringing in” skills as needed【888862858458267†L149-L151】. | On‑demand retrieval of domain‑specific context without building full subagents. |
| **Router** | A routing step classifies input and directs it to one or more specialized agents; results are combined【888862858458267†L150-L152】. | Large sets of specialists; classification of user queries. |
| **Custom workflow** | Build bespoke control flow using LangGraph’s graph API.  Mix deterministic logic and agentic behavior.  This is the most flexible pattern and underlies more complex designs【888862858458267†L153-L155】. | Hierarchical multi‑agent systems; advanced orchestration. |

You can mix patterns—e.g., a subagent architecture can embed custom workflows or router agents【888862858458267†L176-L179】.

## Multi‑Agent Network Example (Functional API)

The official tutorial demonstrates creating a **many‑to‑many network** where agents can hand control to each other【524036067177045†L173-L253】.  Two ReAct agents—a travel advisor and a hotel advisor—communicate via tools.

```python
from langchain_core.tools import tool
from langgraph.func import entrypoint, task
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

# Tools shared across agents
def get_travel_recommendations():
    return random.choice(["aruba", "turks and caicos"])

@tool(return_direct=True)
def transfer_to_hotel_advisor():
    return "Transfer to hotel advisor"

# Build ReAct agents for each domain
model = ChatAnthropic(model="claude-3-5-sonnet-latest")
travel_agent = create_react_agent(
    model,
    [get_travel_recommendations, transfer_to_hotel_advisor],
    prompt="You are a travel advisor. Suggest destinations and hand off when hotels are needed."
)

@task
def call_travel(messages):
    resp = travel_agent.invoke({"messages": messages})
    return resp["messages"]  # returns a list of messages

# Define analogous hotel advisor agent and call_hotel task...

# Orchestrate the hand‑off loop
def get_next_agent(messages):
    # Inspect last tool call to decide which agent runs next
    last_ai = next(m for m in reversed(messages) if m["role"] == "assistant")
    tool_calls = last_ai.get("tool_calls", [])
    if tool_calls and tool_calls[-1]["name"] == "transfer_to_hotel_advisor":
        return call_hotel
    return call_travel

@entrypoint()
def workflow(messages):
    call_active = call_travel
    while True:
        agent_messages = call_active(messages).result()
        messages = messages + agent_messages
        call_active = get_next_agent(messages)
        # stop when the agent’s last message doesn’t contain a tool call
        if not any(m.get("tool_calls") for m in agent_messages):
            break
    return messages
```

This example uses `@task` to wrap operations that may run multiple times, ensuring idempotency when resuming durable workflows.  The orchestrator uses a simple while‑loop to alternate between agents based on the tool call.

### Multi‑Agent Collaboration (Graph API)

The **multi‑agent collaboration** notebook shows how to build a research + chart generator system, where each agent decides when to stop or hand off.  The system uses the graph API and the `Command` class to instruct the graph where to go next【928806101369966†L168-L233】:

1. **Define specialized ReAct agents** (research and chart generator) using `create_react_agent` and custom system prompts【928806101369966†L168-L233】.
2. **Define node functions** `research_node` and `chart_node` that:
   - Invoke the respective agent using the shared message history.
   - Wrap the agent’s last AI message as a `HumanMessage` so providers accept it.
   - Return a `Command(update=..., goto=...)` indicating which node to run next (`chart_generator`, `researcher` or `END`) based on the agent’s response【928806101369966†L168-L233】.
3. **Build the graph** using `StateGraph(MessagesState)`, add both nodes, connect `START` to the first node and compile【928806101369966†L234-L248】.
4. **Invoke the graph** using `.stream()` to get streaming updates for each node execution【928806101369966†L259-L279】.

This pattern uses many features of LangGraph: message‑based state, ReAct agents, conditional routing via `Command`, streaming and subgraph context.

## Persistence and Durable Execution

LangGraph includes a built‑in persistence layer.  When you compile a graph with a **checkpointer**, each super‑step’s state is saved as a **checkpoint** in a **thread**【53599280320213†L101-L134】.  Persistence enables advanced features:

- **Durable execution** – you can pause and resume workflows without losing progress.  The framework saves the state of each step and can resume from the last checkpoint after an error or human pause【411954619897554†L83-L97】.
- **Thread IDs** – a thread is a unique identifier grouping checkpoints for a particular run.  When invoking a graph you must provide a `thread_id` via the `configurable` part of the config: `graph.invoke(inputs, {"configurable": {"thread_id": "my_thread"}})`【53599280320213†L116-L131】.  Reusing the same thread ID continues the previous run; a new ID creates a fresh session.
- **Durability modes** – choose how frequently to persist checkpoints.  Modes include `"exit"` (persist only when the graph exits), `"async"` (persist asynchronously) and `"sync"` (persist synchronously after each step)【411954619897554†L160-L187】.
- **Checkpointers** – built‑in checkpointers store checkpoints in memory or to a database.  You can implement custom back‑ends to persist state across processes.

**Using tasks in nodes:** non‑deterministic operations (API calls, random number generation) should be wrapped in a `@task` so that when the workflow is resumed, LangGraph reads the cached result instead of re‑executing the side effect【411954619897554†L191-L272】.

## Streaming

LangGraph surfaces real‑time updates through streaming.  The `graph.stream()` method yields intermediate data as the graph executes【882118390810672†L90-L107】.  You can choose from several **stream modes**【882118390810672†L110-L126】:

| Mode | Description |
| --- | --- |
| `values` | Yields the full state after each step. |
| `updates` | Yields only the state changes after each step.  Multiple updates in the same step are streamed separately. |
| `messages` | Yields LLM tokens and metadata from any node invoking an LLM. |
| `custom` | Streams arbitrary data sent from within node functions. |
| `debug` | Streams detailed trace information for debugging. |

To stream, call `for chunk in graph.stream(inputs, stream_mode="updates"):`.  You can also stream multiple modes by passing a list (e.g., `stream_mode=["updates", "messages"]`)【882118390810672†L187-L195】.

## Interrupts (Human‑in‑the‑Loop)

Interrupts let your workflow **pause and wait for external input**.  Inside a node, call `interrupt(value)` to save the current state and return `value` to the caller.  Execution halts until you resume by invoking the graph again with `Command(resume=<value>)`.  Key points【23223334674127†L92-L110】:

- You must compile the graph with a **checkpointer** and provide a `thread_id` so the interrupt can restore the correct state【23223334674127†L105-L115】.
- The payload passed to `interrupt()` must be JSON‑serializable.  It is returned in the `__interrupt__` field of the result【23223334674127†L95-L110】.
- Resuming requires calling `graph.invoke(Command(resume=<response>), config={"configurable": {"thread_id": <same id>}})`【23223334674127†L159-L183】.

Interrupts enable human approval, data injection or dynamic prompt editing mid‑run.

## Time Travel

Time travel lets you **resume execution from an earlier checkpoint**.  The process is:

1. Run the graph once to generate checkpoints.
2. Retrieve a checkpoint using `graph.get_state_history(thread_id)` to list past states or by using an interrupt placed before the node of interest【973921719565531†L97-L104】.
3. Optionally modify the state using `graph.update_state(thread_id, checkpoint_id, updates)`【973921719565531†L97-L108】.
4. Resume execution from that checkpoint by invoking the graph with input `None` and specifying both `thread_id` and `checkpoint_id`【973921719565531†L97-L110】.

This allows you to explore alternate execution paths or correct mistakes without starting over【973921719565531†L83-L96】.

## Memory

Memory refers to the ability of agents to recall information across interactions.  LangGraph supports:

- **Short‑term memory (thread‑scoped)** – conversation history and other stateful data are persisted with the thread, so the agent sees the full context for a session.  Short‑term memory is stored in the state and is updated on each graph step【898203229638584†L85-L118】.

- **Long‑term memory** – stores knowledge across sessions under custom namespaces.  Long‑term memory is implemented via **stores** and can be semantic (facts), episodic (experience) or procedural (instructions).  The docs liken the types to human memory and note that different applications require different update strategies【898203229638584†L141-L166】.

To manage conversation history efficiently, you may need to prune or summarize messages due to context‑window limits.  The memory guide discusses techniques such as removing stale messages or summarizing conversation chunks【898203229638584†L124-L135】.

## Subgraphs

A **subgraph** is a graph used as a node inside another graph.  Subgraphs are useful for multi‑agent systems, code reuse and modular development【375085071727617†L83-L91】.  There are two ways to integrate a subgraph:

1. **Invoke a graph from a node** – call the subgraph’s `.invoke()` inside the parent node.  This allows the subgraph to have its own schema and private state.  The parent node must translate the parent state into the subgraph’s state before invoking, then translate the result back【375085071727617†L121-L160】.

2. **Add a graph as a node** – embed the subgraph directly into the parent graph.  In this case, the subgraph shares state keys with the parent.  You define the subgraph with `StateGraph`, compile it and then insert it using `.add_node(subgraph)` on the parent.  The docs show examples where a subgraph processes its own schema and the parent transforms its state accordingly【375085071727617†L166-L204】.

Subgraphs support the same persistence, streaming and interrupt capabilities as top‑level graphs, and you can inspect subgraph states separately from the parent.

## Best Practices for SOTA Multi‑Agent Applications

1. **Design deterministic nodes** – wrap non‑deterministic code or side effects in `@task` so that durable execution can resume without repeating operations【411954619897554†L191-L272】.
2. **Use checkpointers and threads** – always compile graphs with a persistence backend and provide thread IDs.  This enables recovery from errors, human pauses and time travel【53599280320213†L116-L134】.
3. **Stream early and often** – streaming provides better user experience and helps debug.  Use `stream_mode="updates"` during development and add `"messages"` to observe token streams【882118390810672†L90-L107】.
4. **Leverage interrupts for human oversight** – call `interrupt()` when the agent needs approval or additional information.  Resume using `Command(resume=value)` to continue【23223334674127†L119-L183】.
5. **Modularize with subgraphs** – encapsulate complex logic or specialized agents in subgraphs.  This simplifies testing and allows teams to develop components independently【375085071727617†L83-L91】.
6. **Manage memory consciously** – maintain short‑term memory in the state and prune or summarize long message histories.  For long‑term knowledge, choose the appropriate store (semantic, episodic, procedural)【898203229638584†L141-L166】.
7. **Use LangSmith for observability** – send traces to LangSmith to visualize graphs, debug state transitions and evaluate agent outputs.  This is crucial for SOTA reliability.
8. **Combine patterns** – multi‑agent systems often mix subagents, router patterns and custom workflows.  Choose the pattern that matches your requirements (distributed development, parallelization, multi‑hop interactions, direct user access)【888862858458267†L143-L175】.
9. **Consider durability modes** – in production, choose `"sync"` for maximum safety, `"async"` for a good balance or `"exit"` for lightweight runs【411954619897554†L160-L187】.
10. **Test with recursion limits** – LangGraph tracks how many steps your graph has taken.  Use the `recursion_limit` argument in `.stream()` or `.invoke()` to avoid infinite loops and to set an upper bound on node executions【928806101369966†L259-L274】.

## Conclusion

LangGraph provides a flexible foundation for building sophisticated multi‑agent applications.  By modelling workflows as graphs, persisting state across steps and enabling streaming, durable execution, human‑in‑the‑loop interrupts, time travel and modular subgraphs, you can design reliable systems that go beyond simple prompt‑loop agents.  Whether you use the graph API or the functional API, the patterns and examples above demonstrate how to coordinate multiple specialized agents, manage stateful interactions and implement advanced capabilities such as memory and checkpointing.  With proper design, LangGraph allows AI engineers to build state‑of‑the‑art multi‑agent applications that are robust, modular and ready for production.
