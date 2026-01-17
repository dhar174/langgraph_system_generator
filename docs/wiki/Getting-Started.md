# Getting Started

This guide will help you install LangGraph System Generator and run your first generation.

## Prerequisites

- **Python**: Version 3.9 or higher
- **OpenAI API Key**: Required for live mode (optional for stub mode)
- **Operating System**: Linux, macOS, or Windows with WSL

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/dhar174/langgraph_system_generator.git
cd langgraph_system_generator
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

Choose the appropriate installation based on your needs:

#### Minimal Installation (Core only)
```bash
pip install -e .
```

#### Full Installation (All features)
```bash
pip install -e ".[full]"
```

#### Development Installation (Includes testing tools)
```bash
pip install -e ".[full,dev]"
```

### 4. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```bash
# Required for live mode
OPENAI_API_KEY=sk-your-openai-key-here

# Optional: Alternative LLM providers
ANTHROPIC_API_KEY=your-anthropic-key-here

# Optional: LangSmith tracing
LANGSMITH_API_KEY=your-langsmith-key-here
LANGSMITH_PROJECT=langgraph-notebook-foundry

# Vector Store Configuration (defaults work fine)
VECTOR_STORE_TYPE=faiss
VECTOR_STORE_PATH=./data/vector_store

# Generation Settings
DEFAULT_MODEL=gpt-4-turbo-preview
MAX_REPAIR_ATTEMPTS=3
DEFAULT_BUDGET_TOKENS=100000
```

### 5. (Optional) Build the Vector Index

The repository includes precached documentation in `data/cached_docs/`. To enable semantic search:

```bash
python scripts/build_index.py
```

This creates a FAISS index at `./data/vector_store`. Requires an OpenAI API key for embeddings.

**Note**: Vector search is optional. Stub mode works without it.

### 6. Verify Installation

Run the test suite to verify everything is working:

```bash
pytest tests/ -v
```

## Your First Generation

Let's generate a simple multi-agent system using the CLI in stub mode (no API key needed).

### Using the CLI (Stub Mode)

```bash
lnf generate "Create a customer support chatbot with routing" \
  --output ./output/first_system \
  --mode stub
```

This generates:
- `notebook.ipynb`: Runnable Jupyter notebook
- `notebook.html`: HTML documentation
- `notebook.docx`: Word document
- `notebook_bundle.zip`: Complete package
- `manifest.json`: Metadata about generated files

**Output:**
```
✓ Requirements analysis complete
✓ Architecture selected: router
✓ Workflow design complete
✓ Tool planning complete
✓ Notebook composed (12 cells)
✓ QA validation passed
✓ Artifacts packaged

Generated artifacts in ./output/first_system:
  - notebook.ipynb
  - notebook.html
  - notebook.docx
  - notebook_bundle.zip
  - manifest.json
```

### Using the CLI (Live Mode)

For full LLM-powered generation (requires API key):

```bash
lnf generate "Create a research assistant with multiple specialized agents" \
  --output ./output/research_system \
  --mode live
```

Live mode uses LLMs to:
- Analyze your requirements in detail
- Select optimal architectures
- Generate contextual code
- Create comprehensive documentation

### Using the Web Interface

Start the web server:

```bash
uvicorn langgraph_system_generator.api.server:app --reload
```

Then open your browser to `http://localhost:8000`.

The web interface provides:
- **Interactive form** for entering requirements
- **Mode selection** (stub/live)
- **Advanced options** (model, temperature, agent type, etc.)
- **Progress tracking** with real-time updates
- **Download buttons** for all generated artifacts
- **Theme toggle** (dark/light mode)

### Using the REST API

For programmatic access:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a data analysis agent with report generation",
    "mode": "stub",
    "output_dir": "./output/api_test",
    "formats": ["ipynb", "html", "docx"]
  }'
```

Response:
```json
{
  "success": true,
  "mode": "stub",
  "prompt": "Create a data analysis agent with report generation",
  "manifest": {
    "notebook_path": "./output/api_test/notebook.ipynb",
    "html_path": "./output/api_test/notebook.html",
    "docx_path": "./output/api_test/notebook.docx",
    "plan_path": "./output/api_test/notebook_plan.json",
    "cells_path": "./output/api_test/generated_cells.json"
  }
}
```

## Understanding the Generated Notebook

Open the generated notebook in Jupyter:

```bash
jupyter notebook output/first_system/notebook.ipynb
```

The notebook includes:

1. **Installation & Setup**: Dependencies and imports
2. **Configuration**: API keys and settings
3. **State Schema**: TypedDict defining agent state
4. **Agent Nodes**: Individual agent implementations
5. **Graph Construction**: LangGraph workflow assembly
6. **Execution Logic**: Running the system
7. **Example Usage**: Sample inputs and outputs

You can run the notebook cells sequentially to execute the system.

## Next Steps

### Exploring Patterns

The Pattern Library provides reusable templates:

```python
from langgraph_system_generator.patterns import RouterPattern

# Generate a complete router system
routes = ["support", "sales", "technical"]
code = RouterPattern.generate_complete_example(routes)
print(code)
```

See [Pattern Library Guide](Pattern-Library-Guide.md) for details.

### Customizing Generation

Control generation with advanced options:

```bash
lnf generate "Create a chatbot" \
  --output ./output/custom \
  --mode live \
  --formats ipynb html \
  --agent-type router \
  --memory-config long \
  --graph-style conditional
```

### Running in Google Colab

Generated notebooks are Colab-ready. Upload to Google Drive and open with Colab:

1. Upload `notebook.ipynb` to Google Drive
2. Right-click → Open with → Google Colaboratory
3. Install dependencies in first cell:
   ```python
   !pip install langgraph langchain langchain-openai
   ```
4. Add your API key:
   ```python
   import os
   os.environ["OPENAI_API_KEY"] = "sk-..."
   ```
5. Run all cells

See detailed Colab instructions in [Colab Usage Guide](Colab-Usage.md).

### Developing Locally

For local development:

1. Install development dependencies:
   ```bash
   pip install -e ".[full,dev]"
   ```

2. Run tests:
   ```bash
   pytest tests/ --cov=src
   ```

3. Run linting:
   ```bash
   black src/ tests/
   ruff check src/ tests/
   mypy src/
   ```

See [Architecture Deep Dive](Architecture-Deep-Dive.md) for system internals.

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError: No module named 'langgraph_system_generator'`:

```bash
pip install -e ".[full]"
```

### Missing API Key

If generation fails with API errors in live mode:

1. Check `.env` file has valid `OPENAI_API_KEY`
2. Try stub mode instead: `--mode stub`

### Vector Store Errors

If you see FAISS errors:

1. Install FAISS: `pip install faiss-cpu`
2. Rebuild index: `python scripts/build_index.py`
3. Or use stub mode (doesn't need vector store)

### Notebook Execution Fails

If the generated notebook doesn't run:

1. Check you have all dependencies: `pip install -r requirements.txt`
2. Set your API key in the notebook
3. Check QA reports in the output directory

## Getting Help

- **Examples**: See `examples/` directory for comprehensive demos
- **Documentation**: Browse other Wiki pages for detailed guides
- **Issues**: Report problems on [GitHub Issues](https://github.com/dhar174/langgraph_system_generator/issues)
- **Tests**: Review `tests/` for usage patterns

---

**Next**: [Architecture Deep Dive →](Architecture-Deep-Dive.md) | [Pattern Library Guide →](Pattern-Library-Guide.md)
