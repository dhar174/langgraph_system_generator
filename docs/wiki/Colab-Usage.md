# Google Colab Usage Guide

This guide shows you how to use LangGraph System Generator notebooks in Google Colab for cloud-based development and execution.

## Why Use Colab?

Google Colab provides several advantages:

- **No Local Setup**: Run notebooks without installing anything locally
- **Free GPU/TPU**: Access to accelerated computing resources
- **Cloud Storage**: Integration with Google Drive
- **Collaboration**: Share notebooks with team members
- **Persistence**: Notebooks save automatically to Drive

## Quick Start

### 1. Generate a Notebook

First, generate a notebook using any method:

**Option A: Using the Web Interface**
1. Go to your local LNF instance: `http://localhost:8000`
2. Enter your prompt and generate
3. Download the `.ipynb` file

**Option B: Using the CLI**
```bash
lnf generate "Create a customer support chatbot" \
  --output ./colab_notebook \
  --formats ipynb
```

**Option C: Using the API**
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a chatbot", "formats": ["ipynb"]}' \
  -o manifest.json
```

### 2. Upload to Google Drive

1. Go to [Google Drive](https://drive.google.com)
2. Create a folder (e.g., "LNF_Notebooks")
3. Upload your `.ipynb` file

### 3. Open in Colab

1. Right-click the notebook file in Drive
2. Select "Open with" → "Google Colaboratory"
3. If you don't see Colaboratory, click "Connect more apps" and search for it

### 4. Install Dependencies

Add this cell at the beginning of your notebook (if not already present):

```python
# Install LangGraph dependencies
!pip install -q langgraph langchain langchain-openai langchain-community

# Verify installation
import langgraph
import langchain
print(f"LangGraph version: {langgraph.__version__}")
print(f"LangChain version: {langchain.__version__}")
```

### 5. Configure API Keys

Add your OpenAI API key (required for execution):

```python
import os
from google.colab import userdata

# Option 1: Use Colab Secrets (recommended)
try:
    os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY')
    print("✓ API key loaded from Colab secrets")
except:
    # Option 2: Direct input (less secure)
    from getpass import getpass
    os.environ["OPENAI_API_KEY"] = getpass("Enter your OpenAI API key: ")
    print("✓ API key set")

# Verify
assert os.environ.get("OPENAI_API_KEY"), "API key not set!"
print("✓ Ready to run")
```

### 6. Run the Notebook

Execute cells sequentially using **Shift+Enter** or the play button. The notebook will:
1. Set up the environment
2. Define the agent state
3. Implement nodes
4. Construct the graph
5. Run example queries

## Using Colab Secrets (Recommended)

Store API keys securely using Colab's secret management:

### Setting Up Secrets

1. In your Colab notebook, click the **key icon** 🔑 in the left sidebar
2. Click "Add new secret"
3. Name: `OPENAI_API_KEY`
4. Value: Your OpenAI API key (e.g., `sk-...`)
5. Toggle on "Notebook access"

### Accessing Secrets in Code

```python
from google.colab import userdata
import os

# Load secret
os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY')

# Use in your code
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4-mini")
```

**Benefits:**
- ✅ Keys never visible in notebook
- ✅ Safe to share notebooks
- ✅ No accidental commits

## Colab-Specific Features

### GPU/TPU Acceleration

While LangGraph doesn't require GPU, you can enable it for other ML tasks:

1. Click "Runtime" → "Change runtime type"
2. Select "GPU" or "TPU" under Hardware accelerator
3. Click "Save"

### Mounting Google Drive

Access files from your Drive:

```python
from google.colab import drive
drive.mount('/content/drive')

# Access files
import sys
sys.path.append('/content/drive/MyDrive/my_modules')

# Save outputs
output_dir = '/content/drive/MyDrive/LNF_Outputs'
```

### Installing Additional Packages

Install any additional dependencies:

```python
# Vector stores
!pip install -q faiss-cpu chromadb

# Document loaders
!pip install -q pypdf unstructured

# Visualization
!pip install -q matplotlib graphviz

# Alternative LLM providers
!pip install -q langchain-anthropic langchain-groq
```

### Downloading Results

Save and download generated outputs:

```python
from google.colab import files

# Generate some output
with open('output.txt', 'w') as f:
    f.write(result)

# Download
files.download('output.txt')
```

## Example Notebooks for Colab

### Router Pattern Example

```python
# ====== SETUP ======
!pip install -q langgraph langchain langchain-openai

import os
from google.colab import userdata
os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY')

# ====== IMPORTS ======
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, add_messages

# ====== STATE ======
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    next_route: str

# ====== NODES ======
llm = ChatOpenAI(model="gpt-4-mini")

def router_node(state: AgentState):
    """Classify input and route to appropriate handler."""
    messages = state["messages"]
    
    prompt = f"""Given this user input, classify it as 'technical', 'billing', or 'general':
    
    Input: {messages[-1].content}
    
    Respond with only one word: technical, billing, or general."""
    
    response = llm.invoke([HumanMessage(content=prompt)])
    route = response.content.strip().lower()
    
    return {"next_route": route}

def technical_node(state: AgentState):
    """Handle technical support queries."""
    messages = state["messages"]
    prompt = f"As a technical support agent, respond to: {messages[-1].content}"
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"messages": [response]}

def billing_node(state: AgentState):
    """Handle billing queries."""
    messages = state["messages"]
    prompt = f"As a billing support agent, respond to: {messages[-1].content}"
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"messages": [response]}

def general_node(state: AgentState):
    """Handle general queries."""
    messages = state["messages"]
    prompt = f"As a general support agent, respond to: {messages[-1].content}"
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"messages": [response]}

# ====== GRAPH ======
workflow = StateGraph(AgentState)

workflow.add_node("router", router_node)
workflow.add_node("technical", technical_node)
workflow.add_node("billing", billing_node)
workflow.add_node("general", general_node)

workflow.set_entry_point("router")

workflow.add_conditional_edges(
    "router",
    lambda state: state["next_route"],
    {
        "technical": "technical",
        "billing": "billing",
        "general": "general"
    }
)

workflow.add_edge("technical", END)
workflow.add_edge("billing", END)
workflow.add_edge("general", END)

app = workflow.compile()

# ====== EXECUTION ======
# Test the system
queries = [
    "My internet is not working",
    "I was charged twice this month",
    "What are your business hours?"
]

for query in queries:
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}")
    
    result = app.invoke({
        "messages": [HumanMessage(content=query)],
        "next_route": ""
    })
    
    print(f"Route: {result['next_route']}")
    print(f"Response: {result['messages'][-1].content}")
```

### Subagents Pattern Example

```python
# ====== SETUP ======
!pip install -q langgraph langchain langchain-openai

import os
from google.colab import userdata
os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY')

# ====== IMPORTS ======
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, add_messages

# ====== STATE ======
class TeamState(TypedDict):
    messages: Annotated[list, add_messages]
    next_agent: str
    iterations: int

# ====== NODES ======
llm = ChatOpenAI(model="gpt-4-mini")

def supervisor_node(state: TeamState):
    """Coordinate team members."""
    messages = state["messages"]
    iterations = state.get("iterations", 0)
    
    if iterations >= 5:
        return {"next_agent": "FINISH"}
    
    prompt = f"""As a supervisor, decide the next agent to call or FINISH:
    - researcher: Gathers information
    - analyst: Analyzes data
    - writer: Creates reports
    - FINISH: Task complete
    
    Current task: {messages[-1].content}
    Iteration: {iterations}
    
    Respond with only the agent name."""
    
    response = llm.invoke([HumanMessage(content=prompt)])
    next_agent = response.content.strip()
    
    return {
        "next_agent": next_agent,
        "iterations": iterations + 1
    }

def researcher_node(state: TeamState):
    """Research information."""
    messages = state["messages"]
    prompt = f"As a researcher, gather information about: {messages[-1].content}"
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"messages": [response]}

def analyst_node(state: TeamState):
    """Analyze data."""
    messages = state["messages"]
    prompt = f"As an analyst, analyze: {messages[-1].content}"
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"messages": [response]}

def writer_node(state: TeamState):
    """Write report."""
    messages = state["messages"]
    prompt = f"As a writer, create a report about: {messages[-1].content}"
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"messages": [response]}

# ====== GRAPH ======
workflow = StateGraph(TeamState)

workflow.add_node("supervisor", supervisor_node)
workflow.add_node("researcher", researcher_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("writer", writer_node)

workflow.set_entry_point("supervisor")

workflow.add_conditional_edges(
    "supervisor",
    lambda state: state["next_agent"],
    {
        "researcher": "researcher",
        "analyst": "analyst",
        "writer": "writer",
        "FINISH": END
    }
)

for agent in ["researcher", "analyst", "writer"]:
    workflow.add_edge(agent, "supervisor")

app = workflow.compile()

# ====== EXECUTION ======
result = app.invoke({
    "messages": [HumanMessage(content="Research and analyze climate change trends")],
    "next_agent": "",
    "iterations": 0
})

print("Final Result:")
print(result["messages"][-1].content)
```

## Best Practices for Colab

### 1. Session Management

Colab sessions disconnect after inactivity:

```python
# Save checkpoints periodically
import pickle

checkpoint = {
    "state": current_state,
    "results": results
}

with open('/content/drive/MyDrive/checkpoint.pkl', 'wb') as f:
    pickle.dump(checkpoint, f)

# Restore from checkpoint
with open('/content/drive/MyDrive/checkpoint.pkl', 'rb') as f:
    checkpoint = pickle.load(f)
```

### 2. Cost Management

Monitor token usage to control costs:

```python
from langchain.callbacks import get_openai_callback

with get_openai_callback() as cb:
    result = app.invoke(state)
    print(f"Tokens used: {cb.total_tokens}")
    print(f"Estimated cost: ${cb.total_cost:.4f}")
```

### 3. Error Handling

Wrap execution in try-except blocks:

```python
try:
    result = app.invoke(state)
except Exception as e:
    print(f"Error: {e}")
    # Save partial results
    with open('error_state.json', 'w') as f:
        json.dump(state, f)
```

### 4. Long-Running Tasks

For long-running generations, use smaller batches:

```python
queries = ["query1", "query2", "query3", ...]

results = []
for i, query in enumerate(queries):
    print(f"Processing {i+1}/{len(queries)}")
    result = app.invoke({"messages": [HumanMessage(content=query)]})
    results.append(result)
    
    # Save intermediate results
    if i % 10 == 0:
        with open('partial_results.pkl', 'wb') as f:
            pickle.dump(results, f)
```

## Troubleshooting

### Common Issues

**Issue**: Runtime disconnected  
**Solution**: Enable background execution or save checkpoints frequently

**Issue**: Package installation fails  
**Solution**: Restart runtime and install packages one at a time

**Issue**: API key not found  
**Solution**: Verify secret name matches exactly: `OPENAI_API_KEY`

**Issue**: Out of memory  
**Solution**: Use smaller models (gpt-4-mini instead of gpt-4) or enable high-RAM runtime

**Issue**: Slow execution  
**Solution**: Colab free tier has usage limits; consider Colab Pro for better performance

### Getting Help

- **Colab FAQ**: https://research.google.com/colaboratory/faq.html
- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **GitHub Issues**: Report bugs or ask questions

## Sharing Notebooks

### Share via Drive

1. In Colab, click "Share" button (top right)
2. Set permissions (view/comment/edit)
3. Copy link and share

### Share on GitHub

1. Download notebook: File → Download → Download .ipynb
2. Commit to your repository
3. GitHub automatically renders notebooks

### Share as Colab Link

Direct Colab link format:
```
https://colab.research.google.com/drive/YOUR_FILE_ID
```

Or use badge in README:
```markdown
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/YOUR_FILE_ID)
```

## Advanced: Colab Pro Features

Colab Pro ($9.99/month) provides:

- **Longer runtimes**: Up to 24 hours
- **More memory**: Up to 32GB RAM
- **Better GPUs**: Access to V100, A100
- **Background execution**: Run while browser closed
- **Priority access**: Faster connection to resources

For heavy LangGraph development, Colab Pro can significantly improve experience.

## Alternatives to Colab

If Colab doesn't meet your needs:

- **Kaggle Notebooks**: Free, similar to Colab
- **Deepnote**: Collaborative notebooks
- **Amazon SageMaker**: AWS-hosted notebooks
- **Azure Notebooks**: Microsoft cloud notebooks
- **Gradient (Paperspace)**: GPU notebooks

All these platforms can run LangGraph notebooks with similar setup steps.

---

**Next**: [Back to Home](Home.md) | [Getting Started](Getting-Started.md) | [Architecture Deep Dive](Architecture-Deep-Dive.md)
