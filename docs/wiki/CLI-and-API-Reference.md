# CLI & API Reference

Complete reference for the LangGraph System Generator command-line interface and REST API.

## Command-Line Interface (CLI)

The `lnf` command provides access to all generation features from the terminal.

### Installation

The CLI is installed automatically with the package:

```bash
pip install -e ".[full]"
```

Verify installation:
```bash
lnf --help
```

### Commands

#### `lnf generate`

Generate a multi-agent system from a text prompt.

**Syntax:**
```bash
lnf generate PROMPT [OPTIONS]
```

**Arguments:**
- `PROMPT`: Natural language description of the desired system (required)

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output DIR` | path | `./output` | Output directory for artifacts |
| `--mode MODE` | choice | `stub` | Generation mode: `stub` or `live` |
| `--formats FORMAT [FORMAT ...]` | list | all | Output formats: `ipynb`, `html`, `docx`, `pdf`, `zip` |
| `--model MODEL` | string | from config | LLM model (e.g., `gpt-4`, `gpt-3.5-turbo`) |
| `--temperature FLOAT` | float | 0.7 | LLM temperature (0.0-2.0) |
| `--max-tokens INT` | int | 4096 | Maximum tokens for LLM response |
| `--agent-type TYPE` | string | auto | Agent architecture: `router`, `subagents`, `hybrid` |
| `--memory-config CONFIG` | string | `none` | Memory configuration: `none`, `short`, `long`, `full` |
| `--graph-style STYLE` | string | auto | Graph style: `sequential`, `parallel`, `conditional`, `cyclic` |
| `--retriever-type TYPE` | string | `vector` | Retriever type: `vector`, `keyword`, `hybrid`, `mmr` |
| `--document-loader LOADER` | string | `text` | Loader type: `text`, `pdf`, `web`, `markdown`, `json`, `csv` |

**Examples:**

Basic generation (stub mode):
```bash
lnf generate "Create a customer support chatbot" --output ./my_chatbot
```

Full generation with live mode:
```bash
lnf generate "Build a research assistant with multiple agents" \
  --output ./research_assistant \
  --mode live \
  --model gpt-4
```

Specific formats only:
```bash
lnf generate "Create a data analyzer" \
  --output ./analyzer \
  --formats ipynb html
```

Advanced options:
```bash
lnf generate "Complex multi-agent system" \
  --output ./complex_system \
  --mode live \
  --model gpt-4 \
  --temperature 0.8 \
  --max-tokens 8192 \
  --agent-type subagents \
  --memory-config long \
  --graph-style conditional
```

#### `lnf build-index`

Build the FAISS vector index from cached documentation.

**Syntax:**
```bash
lnf build-index [OPTIONS]
```

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--cache DIR` | path | `./data/cached_docs` | Cached documentation directory |
| `--store DIR` | path | `./data/vector_store` | Vector store output directory |
| `--fake-embeddings` | flag | False | Use fake embeddings (no API key needed) |

**Examples:**

Build with OpenAI embeddings:
```bash
export OPENAI_API_KEY='sk-...'
lnf build-index
```

Build with fake embeddings (testing):
```bash
lnf build-index --fake-embeddings
```

Custom paths:
```bash
lnf build-index \
  --cache ./my_docs \
  --store ./my_vector_store
```

### Environment Variables

The CLI respects these environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication | None |
| `ANTHROPIC_API_KEY` | Anthropic API authentication | None |
| `LANGSMITH_API_KEY` | LangSmith tracing | None |
| `LANGSMITH_PROJECT` | LangSmith project name | `langgraph-notebook-foundry` |
| `VECTOR_STORE_TYPE` | Vector store backend | `faiss` |
| `VECTOR_STORE_PATH` | Vector store location | `./data/vector_store` |
| `DEFAULT_MODEL` | Default LLM model | `gpt-4-turbo-preview` |
| `MAX_REPAIR_ATTEMPTS` | QA repair attempts | `3` |
| `DEFAULT_BUDGET_TOKENS` | Token budget | `100000` |
| `LNF_OUTPUT_BASE` | Base output directory | `.` |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Generation failed |
| 2 | Invalid arguments |
| 3 | Configuration error |

## REST API

The FastAPI server exposes HTTP endpoints for programmatic access.

### Starting the Server

**Development:**
```bash
uvicorn langgraph_system_generator.api.server:app --reload
```

**Production:**
```bash
uvicorn langgraph_system_generator.api.server:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4
```

**Docker:**
```bash
docker build -t lnf .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -v $(pwd)/output:/app/output \
  lnf
```

### Endpoints

#### `GET /`

Serves the web interface.

**Response:** HTML page

**Example:**
```bash
curl http://localhost:8000/
```

#### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.1"
}
```

**Example:**
```bash
curl http://localhost:8000/health
```

#### `POST /generate`

Generate a multi-agent system from a prompt.

**Request Body:**
```json
{
  "prompt": "string (required)",
  "mode": "stub | live (optional, default: stub)",
  "output_dir": "string (optional, default: ./output/api)",
  "formats": ["ipynb", "html", "docx", "pdf", "zip"] (optional),
  
  // Advanced options
  "model": "string (optional)",
  "temperature": "float (optional, 0.0-2.0)",
  "max_tokens": "int (optional, 1-32768)",
  "agent_type": "string (optional)",
  "memory_config": "string (optional)",
  "graph_style": "string (optional)",
  "retriever_type": "string (optional)",
  "document_loader": "string (optional)",
  "custom_endpoint": "string (optional)",
  "preset": "string (optional)"
}
```

**Response (Success):**
```json
{
  "success": true,
  "mode": "stub",
  "prompt": "Create a customer support chatbot",
  "output_dir": "./output/api",
  "manifest_path": "./output/api/manifest.json",
  "manifest": {
    "notebook_path": "./output/api/notebook.ipynb",
    "html_path": "./output/api/notebook.html",
    "docx_path": "./output/api/notebook.docx",
    "pdf_path": "./output/api/notebook.pdf",
    "zip_path": "./output/api/notebook_bundle.zip",
    "plan_path": "./output/api/notebook_plan.json",
    "cells_path": "./output/api/generated_cells.json"
  }
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Error message describing what went wrong",
  "mode": "stub",
  "prompt": "User's prompt"
}
```

**Status Codes:**

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Invalid request |
| 500 | Server error |

**Examples:**

Basic request (stub mode):
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a customer support chatbot",
    "mode": "stub"
  }'
```

Full request with options:
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Build a research assistant",
    "mode": "live",
    "output_dir": "./output/research",
    "formats": ["ipynb", "html", "docx"],
    "model": "gpt-4",
    "temperature": 0.8,
    "max_tokens": 8192,
    "agent_type": "subagents",
    "memory_config": "long"
  }'
```

Python client:
```python
import requests

response = requests.post(
    "http://localhost:8000/generate",
    json={
        "prompt": "Create a data analysis agent",
        "mode": "stub",
        "output_dir": "./output/analyzer",
        "formats": ["ipynb", "html"]
    }
)

result = response.json()
if result["success"]:
    print(f"Notebook: {result['manifest']['notebook_path']}")
else:
    print(f"Error: {result['error']}")
```

JavaScript client:
```javascript
const response = await fetch('http://localhost:8000/generate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    prompt: 'Create a chatbot',
    mode: 'stub',
    formats: ['ipynb', 'html']
  })
});

const result = await response.json();
if (result.success) {
  console.log('Generated:', result.manifest.notebook_path);
} else {
  console.error('Error:', result.error);
}
```

#### `GET /static/*`

Serves static assets for the web interface (CSS, JavaScript, images).

**Example:**
```bash
curl http://localhost:8000/static/styles.css
```

### API Request Validation

All requests are validated using Pydantic models:

**Validation Rules:**
- `prompt`: Required, max 5000 characters
- `mode`: Must be "stub" or "live"
- `temperature`: Must be 0.0-2.0
- `max_tokens`: Must be 1-32768
- `formats`: Must be valid format names

**Validation Error Response:**
```json
{
  "detail": [
    {
      "loc": ["body", "temperature"],
      "msg": "ensure this value is less than or equal to 2.0",
      "type": "value_error.number.not_le"
    }
  ]
}
```

### Rate Limiting

The API does not currently implement rate limiting. For production deployments, consider:

1. **Reverse Proxy**: Use nginx/Caddy with rate limiting
2. **API Gateway**: AWS API Gateway, Kong, etc.
3. **Application-Level**: Add rate limiting middleware

Example nginx configuration:
```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/m;

server {
    location /generate {
        limit_req zone=api burst=5 nodelay;
        proxy_pass http://localhost:8000;
    }
}
```

### Authentication

The API does not include built-in authentication. For production:

1. **API Keys**: Add middleware to check `X-API-Key` header
2. **OAuth**: Integrate OAuth2/OIDC provider
3. **JWT**: Use JWT tokens for authentication

Example API key middleware:
```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.getenv("API_SECRET_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

@app.post("/generate", dependencies=[Depends(verify_api_key)])
async def generate_endpoint(request: GenerationRequest):
    # ...
```

## SDK Usage

For programmatic access from Python, use the CLI functions directly:

```python
from langgraph_system_generator.cli import generate_artifacts

# Generate in stub mode
result = generate_artifacts(
    prompt="Create a customer support chatbot",
    mode="stub",
    output_dir="./output/my_system",
    formats=["ipynb", "html", "docx"]
)

print(f"Success: {result['success']}")
print(f"Notebook: {result['manifest']['notebook_path']}")
```

Or use the generator graph directly:

```python
from langgraph_system_generator.generator.graph import create_generator_graph

# Create the graph
graph = create_generator_graph()
app = graph.compile()

# Run generation
initial_state = {
    "user_prompt": "Create a research assistant",
    "uploaded_files": None,
    "constraints": [],
    # ... other state fields ...
}

result = app.invoke(initial_state)
print(f"Generated {len(result['generated_cells'])} cells")
```

## Output Formats

### Generated Artifacts

Every successful generation produces:

| File | Format | Description |
|------|--------|-------------|
| `notebook.ipynb` | Jupyter | Runnable notebook |
| `notebook.html` | HTML | Web-viewable export |
| `notebook.docx` | DOCX | Word document |
| `notebook.pdf` | PDF | Print-ready (optional) |
| `notebook_bundle.zip` | ZIP | Complete package |
| `manifest.json` | JSON | Generation metadata |
| `notebook_plan.json` | JSON | Notebook structure plan |
| `generated_cells.json` | JSON | Raw cell specifications |

### Manifest Structure

The `manifest.json` contains complete generation metadata:

```json
{
  "prompt": "User's original prompt",
  "mode": "stub | live",
  "architecture": "router | subagents | hybrid",
  "patterns": ["router"],
  "timestamp": "2024-01-17T18:00:00Z",
  "version": "0.1.1",
  
  "artifacts": {
    "notebook": "./notebook.ipynb",
    "html": "./notebook.html",
    "docx": "./notebook.docx",
    "pdf": "./notebook.pdf",
    "zip": "./notebook_bundle.zip",
    "plan": "./notebook_plan.json",
    "cells": "./generated_cells.json"
  },
  
  "qa_status": {
    "passed": true,
    "checks_performed": 5,
    "checks_passed": 5,
    "checks_failed": 0,
    "repair_attempts": 0
  },
  
  "metadata": {
    "cells_generated": 12,
    "sections": [
      "Setup & Configuration",
      "State Definition",
      "Node Implementation",
      "Graph Construction",
      "Execution & Testing"
    ],
    "generation_time_ms": 850,
    "model_used": "gpt-4-turbo-preview",
    "tokens_used": 15432
  },
  
  "qa_reports": [
    {
      "check_name": "json_structure",
      "passed": true,
      "message": "Notebook structure is valid"
    },
    {
      "check_name": "required_sections",
      "passed": true,
      "message": "All required sections present"
    }
  ]
}
```

## Advanced Usage

### Custom Pipeline Stages

Modify the generation pipeline:

```python
from langgraph_system_generator.generator.graph import create_generator_graph

# Create base graph
workflow = create_generator_graph()

# Add custom node
def custom_validation_node(state):
    # Your custom validation logic
    return {"custom_validated": True}

workflow.add_node("custom_validation", custom_validation_node)
workflow.add_edge("static_qa", "custom_validation")
workflow.add_edge("custom_validation", "runtime_qa")

# Compile and use
app = workflow.compile()
```

### Custom Exporters

Add new export formats:

```python
from langgraph_system_generator.notebook.exporters import NotebookExporter

class CustomExporter(NotebookExporter):
    @staticmethod
    def export_to_custom_format(notebook, output_path):
        # Your export logic
        with open(output_path, 'w') as f:
            f.write(convert_to_custom_format(notebook))
        return str(output_path)

# Use in generation
exporter = CustomExporter()
custom_path = exporter.export_to_custom_format(notebook, "./output/custom.ext")
```

### Pattern Integration

Use patterns in API/CLI generation:

```python
from langgraph_system_generator.patterns import RouterPattern, SubagentsPattern

# Pre-generate pattern code
router_code = RouterPattern.generate_complete_example(
    routes=["tech", "billing", "general"]
)

# Use in custom node
def custom_composition_node(state):
    # Inject pattern code into cells
    cells = [
        {"cell_type": "markdown", "content": "# Router System"},
        {"cell_type": "code", "content": router_code}
    ]
    return {"generated_cells": cells}
```

## Troubleshooting

### Common Issues

**Issue**: API returns 500 error  
**Solution**: Check server logs and ensure all dependencies installed

**Issue**: Generated notebook missing  
**Solution**: Check `manifest.json` for actual paths and QA status

**Issue**: Rate limit exceeded (OpenAI)  
**Solution**: Add delays between requests or use stub mode

**Issue**: CORS errors in browser  
**Solution**: The API includes CORS middleware; ensure Origin header is set

### Debug Mode

Enable debug logging:

```bash
# CLI
export LOG_LEVEL=DEBUG
lnf generate "test prompt" --output ./debug

# API
uvicorn langgraph_system_generator.api.server:app --log-level debug
```

### Validation

Test your installation:

```bash
# Health check
curl http://localhost:8000/health

# Test generation
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test", "mode": "stub"}'

# Check output
ls -la output/api/
cat output/api/manifest.json
```

## Examples

Complete examples available in repository:

- **CLI Examples**: See `README.md` for CLI usage
- **API Examples**: Check `docs/WEB_UI_ENHANCEMENTS.md` for API usage
- **Pattern Examples**: Explore `examples/` directory
- **Integration Tests**: Review `tests/integration/` for advanced usage

---

**Next**: [Back to Home](Home.md) | [Getting Started](Getting-Started.md)
