# LangGraph System Generator - Context for Google Gemini

## Project Overview

**Purpose:** Generate complete, production-ready multi-agent LangGraph systems from natural language prompts. This tool transforms a simple text description into fully functional Jupyter notebooks with working code, comprehensive documentation, and multiple export formats.

**Core Workflow:**
```
User Prompt → Requirements Analysis → Architecture Selection → RAG Context Retrieval 
→ Workflow Design → Tool Planning → Notebook Composition → QA/Repair → Multi-Format Export
```

**Key Features:**
- **Web Interface:** Modern, responsive UI (FastAPI + HTML/CSS/JS) for browser-based system generation
- **CLI Tool:** `lnf` command-line interface for scripted and CI/CD workflows
- **RAG-Powered:** Precached LangGraph/LangChain documentation (19+ pages, ~300KB) for offline intelligent generation
- **Pattern Library:** Router, Subagents, and Critique-Revise Loop patterns for common multi-agent architectures
- **Multi-Format Export:** `.ipynb`, `.html`, `.docx`, `.pdf`, `.zip` bundles with JSON artifacts
- **Dual Modes:** `stub` (fast, no API key) and `live` (full LLM-powered generation)

---

## Tech Stack

### Primary Languages
- **Python:** 49.3% - Main implementation language
- **Jupyter Notebooks:** 37.5% - Output artifacts and examples
- **HTML/CSS/JavaScript:** 10%+ - Web UI and visualization

### Core Dependencies
```
LangGraph & LangChain:
- langgraph >= 0.2.0, < 1.0.0
- langchain >= 0.3.0, < 1.0.0
- langchain-openai >= 0.2.0
- langchain-community >= 0.3.0

Notebook Generation:
- nbformat >= 5.9.0
- nbconvert >= 7.14.0

Document Export:
- python-docx >= 1.1.0
- reportlab >= 4.0.0

RAG & Vector Store:
- faiss-cpu >= 1.7.4
- chromadb >= 0.4.0
- sentence-transformers >= 2.2.0

Web API:
- fastapi >= 0.115.0
- uvicorn >= 0.30.0
- httpx >= 0.28.0

Testing:
- pytest >= 7.4.0
- pytest-asyncio >= 0.21.0
- pytest-cov >= 4.1.0

Formatting & Linting:
- black >= 23.0.0
- ruff >= 0.1.0
- mypy >= 1.7.0
```

### Architecture Components
- **Pydantic v2:** All state management and data validation
- **StateGraph (LangGraph):** Orchestration of generation workflow
- **FAISS/ChromaDB:** Vector storage for RAG retrieval
- **FastAPI:** REST API and web interface server
- **Docker:** Optional containerization support

---

## Project Structure

```
langgraph_system_generator/
├── src/langgraph_system_generator/     # Main source code
│   ├── api/                             # FastAPI server and web UI
│   │   ├── server.py                    # Main API endpoints and web interface
│   │   └── static/                      # Web UI assets (HTML, CSS, JS)
│   ├── cli.py                           # Command-line interface entry point
│   ├── generator/                       # Core generation logic
│   │   ├── graph.py                     # Main generator StateGraph assembly
│   │   ├── state.py                     # Pydantic state models (GeneratorState, CellSpec, etc.)
│   │   ├── nodes.py                     # Graph node implementations
│   │   └── agents/                      # Individual agent implementations
│   │       ├── requirements_analyst.py  # Constraint extraction from prompts
│   │       ├── architecture_selector.py # Pattern/architecture selection
│   │       ├── graph_designer.py        # Workflow design
│   │       ├── toolchain_engineer.py    # Tool planning
│   │       ├── notebook_composer.py     # Cell generation
│   │       └── qa_repair_agent.py       # Quality assurance and repair
│   ├── notebook/                        # Notebook building and export
│   │   ├── builder.py                   # Constructs NotebookNode from CellSpecs
│   │   ├── exporter.py                  # Multi-format export (HTML, DOCX, PDF, ZIP)
│   │   ├── templates.py                 # Notebook templates and patterns
│   │   ├── manuscript_docx.py           # DOCX generation logic
│   │   └── manuscript_pdf.py            # PDF generation logic
│   ├── patterns/                        # Reusable LangGraph patterns
│   │   ├── router.py                    # Router pattern code generator
│   │   ├── subagents.py                 # Subagents/supervisor pattern
│   │   └── critique_loops.py            # Critique-revise loop pattern
│   ├── qa/                              # Quality assurance system
│   │   ├── validators.py                # Notebook validation checks
│   │   └── repair.py                    # Automated repair agent
│   ├── rag/                             # RAG and documentation retrieval
│   │   ├── indexer.py                   # Document scraping and indexing
│   │   ├── retriever.py                 # Vector search interface
│   │   ├── cache.py                     # Document caching utilities
│   │   └── embeddings.py                # Embedding management
│   └── utils/                           # Configuration and utilities
│       └── config.py                    # Settings via pydantic-settings
├── data/                                # Data files
│   ├── cached_docs/                     # Precached LangGraph/LangChain docs
│   │   ├── documents.json               # Cached documentation (2.6MB)
│   │   └── README.md                    # Documentation cache info
│   └── vector_store/                    # FAISS/ChromaDB indices (generated)
├── tests/                               # Test suite
│   ├── unit/                            # Unit tests
│   ├── integration/                     # Integration tests
│   ├── patterns/                        # Pattern library tests
│   └── conftest.py                      # Pytest configuration
├── examples/                            # Runnable examples
│   ├── router_pattern_example.py
│   ├── subagents_pattern_example.py
│   └── critique_revise_pattern_example.py
├── scripts/                             # Utility scripts
│   ├── build_index.py                   # Build vector index from cached docs
│   └── demo_*.py                        # Demonstration scripts
├── docs/                                # Additional documentation
│   ├── patterns.md                      # Pattern library guide
│   ├── WEB_UI_VISUAL_GUIDE.md          # Web interface documentation
│   └── NOTEBOOK_OUTPUT_GUIDE.md        # Output format guide
├── requirements.txt                     # Python dependencies
├── setup.py                             # Package setup and entry points
├── Dockerfile                           # Docker containerization
└── .env.example                         # Environment variable template
```

---

## Coding Conventions & Style

### Python Code Style

**Formatter:** All Python code MUST use [Black](https://black.readthedocs.io/) formatting.
- Run: `black src/ tests/ examples/ scripts/`
- Line length: 100 characters (Black default: 88, but project may extend)
- String quotes: Double quotes preferred by Black

**Linter:** Use [Ruff](https://docs.astral.sh/ruff/) for fast linting.
- Run: `ruff check src/ tests/ examples/ scripts/`
- Fix auto-fixable issues: `ruff check --fix .`

**Type Hints:** Explicit type annotations are REQUIRED for all public functions, methods, and class attributes.
```python
# ✓ CORRECT
def analyze(prompt: str) -> List[Constraint]:
    """Analyze user prompt and extract constraints."""
    ...

# ✗ WRONG - Missing type hints
def analyze(prompt):
    ...
```

**Import Order:** Follow PEP 8 and Black conventions:
1. Standard library imports
2. Third-party imports (langchain, langgraph, pydantic, etc.)
3. Local application imports

```python
# ✓ CORRECT
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from langgraph_system_generator.generator.state import GeneratorState
```

### Pydantic Models

Use **Pydantic v2** for all data models:
```python
from pydantic import BaseModel, Field

class Constraint(BaseModel):
    """User constraint specification."""
    
    type: str = Field(description="Constraint type: 'goal', 'tone', 'length', etc.")
    value: str = Field(description="Constraint value or description")
    priority: int = Field(default=1, description="Priority level (1=low, 5=high)")
```

**Key Rules:**
- Always use `Field()` with descriptive `description` parameters
- Provide sensible defaults with `default=` or `default_factory=`
- Use `Optional[T]` for nullable fields
- Prefer `model_dump()` over deprecated `.dict()`

### Docstrings

**Required:** All public functions, classes, and methods must have docstrings.

**Format:** Use Google-style docstrings:
```python
def repair_notebook(
    notebook_path: str | Path,
    qa_reports: List[QAReport],
    attempt: int
) -> tuple[bool, List[QAReport]]:
    """Attempt to repair a notebook based on QA reports.
    
    Args:
        notebook_path: Path to the notebook file to repair
        qa_reports: List of QA reports identifying issues
        attempt: Current repair attempt number (1-indexed)
    
    Returns:
        Tuple of (success, updated_qa_reports):
            - success: True if all issues resolved, False otherwise
            - updated_qa_reports: Re-run QA reports after repair
    
    Raises:
        FileNotFoundError: If notebook_path does not exist
        ValueError: If attempt number exceeds MAX_ATTEMPTS
    """
    ...
```

### Notebook Code Style

**Cell Structure:**
- Begin notebooks with a Markdown cell explaining purpose and setup
- Group related code in logical sections with Markdown headers
- Include inline comments for complex logic
- End with a summary or next steps Markdown cell

**Imports:**
- Place all imports in the first code cell after introduction
- Follow the same import ordering as Python files

**Output Formats:**
- Prefer `.py` files for production code
- Use `.ipynb` for tutorials, examples, and generated artifacts
- Ensure notebooks are **Colab-friendly** (no local-only dependencies by default)

---

## Development Workflow

### Environment Setup

1. **Create Virtual Environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys (optional for stub mode)
   ```

4. **Build Vector Index (Optional):**
   ```bash
   python scripts/build_index.py
   # OR via CLI:
   lnf build-index --cache ./data/cached_docs --store ./data/vector_store
   ```

### Running the Application

#### CLI Usage
```bash
# Generate in stub mode (no API key required, fast)
lnf generate "Create a router-based chatbot" --output ./output/demo --mode stub

# Generate in live mode (requires OPENAI_API_KEY)
lnf generate "Create a customer support system" --mode live

# Specify output formats
lnf generate "Create a chatbot" --formats ipynb html docx zip

# Build vector index with fake embeddings (no API key)
lnf build-index --cache ./data/cached_docs --store ./data/vector_store
```

#### Web Interface
```bash
uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000 in your browser
```

#### Docker
```bash
docker build -t lnf .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -v $(pwd)/output:/app/output \
  lnf
```

### Testing

**Run All Tests:**
```bash
pytest
```

**Run Specific Test Suite:**
```bash
pytest tests/unit/                    # Unit tests only
pytest tests/integration/             # Integration tests
pytest tests/patterns/                # Pattern library tests
pytest tests/unit/test_validators.py  # Specific test file
```

**Run with Coverage:**
```bash
pytest --cov=langgraph_system_generator --cov-report=html
# View: open htmlcov/index.html
```

**Run Specific Test:**
```bash
pytest tests/unit/test_validators.py::test_check_imports_present -v
```

### Linting & Formatting

**Format Code:**
```bash
black src/ tests/ examples/ scripts/
```

**Lint Code:**
```bash
ruff check src/ tests/ examples/ scripts/
ruff check --fix .  # Auto-fix issues
```

**Type Checking:**
```bash
mypy src/
```

**CI Linting (Flake8):**
```bash
# The CI uses flake8 for basic checks:
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
```

---

## Core Workflows

### Generation Workflow

The generator uses a **LangGraph StateGraph** with the following nodes:

1. **intake_node:** Parse user prompt, initialize state
2. **rag_retrieval_node:** Retrieve relevant documentation from vector store
3. **architecture_selection_node:** Choose pattern (router/subagents/hybrid) based on prompt
4. **graph_design_node:** Design workflow structure and node relationships
5. **tooling_plan_node:** Plan tools and integrations needed
6. **notebook_assembly_node:** Generate notebook cells from design
7. **static_qa_node:** Validate notebook structure and content
8. **repair_node:** Fix issues identified by QA (up to 3 attempts)
9. **runtime_qa_node:** (Optional) Execute and validate runtime behavior
10. **package_outputs_node:** Export to multiple formats and bundle

**State Flow:**
```
START → intake → RAG retrieval → architecture selection → graph design
      → tooling plan → notebook assembly → static QA
      → [if issues] repair → static QA (loop max 3 times)
      → [if passed] package outputs → END
```

### Stub Mode vs. Live Mode

**Stub Mode (`--mode stub`):**
- **No API keys required**
- Uses heuristic-based architecture selection
- Generates template notebooks with placeholder patterns
- Fast execution (~1-5 seconds)
- Ideal for testing, CI/CD, and offline development

**Live Mode (`--mode live`):**
- **Requires OPENAI_API_KEY** (or other LLM provider)
- Full LLM-powered generation at each step
- Intelligent context-aware notebook creation
- Slower execution (~30-90 seconds depending on complexity)
- Production-quality outputs

### Pattern Library Usage

The pattern library provides **code generators** for common LangGraph architectures:

#### Router Pattern
```python
from langgraph_system_generator.patterns import RouterPattern

routes = ["search", "analyze", "summarize"]
route_purposes = {
    "search": "Search for information",
    "analyze": "Analyze data and identify patterns",
    "summarize": "Condense content into summaries",
}

# Generate complete, runnable code
code = RouterPattern.generate_complete_example(routes, route_purposes)

# Or generate individual components
state_code = RouterPattern.generate_state_code()
router_code = RouterPattern.generate_router_node_code(routes, "gpt-4")
graph_code = RouterPattern.generate_graph_code(routes)
```

#### Subagents Pattern
```python
from langgraph_system_generator.patterns import SubagentsPattern

subagents = ["researcher", "analyst", "writer"]
descriptions = {
    "researcher": "Gathers information from multiple sources",
    "analyst": "Analyzes data and identifies patterns",
    "writer": "Creates comprehensive reports",
}

code = SubagentsPattern.generate_complete_example(subagents, descriptions)
```

#### Critique-Revise Loop Pattern
```python
from langgraph_system_generator.patterns import CritiqueLoopPattern

code = CritiqueLoopPattern.generate_complete_example(
    task_description="Write technical documentation",
    criteria=["Technical accuracy", "Clarity", "Completeness"],
    max_revisions=3,
)
```

**See:** `docs/patterns.md` for comprehensive pattern documentation.

---

## RAG & Vector Store Operations

### Cached Documentation

**Location:** `data/cached_docs/documents.json`

**Contents:**
- 19+ pages of LangGraph and LangChain documentation
- Pre-scraped and filtered (no redirects or minimal content)
- ~300KB JSON file with document chunks
- Offline-ready for stub mode or environments without internet

**Coverage:**
- LangGraph core concepts (graphs, state, nodes, edges)
- LangGraph advanced patterns (subgraphs, human-in-the-loop, streaming)
- LangChain agents, chains, RAG, and memory
- LangChain document loaders, retrievers, and tools

### Vector Store Setup

**Build Index:**
```bash
# With OpenAI embeddings (requires API key)
python scripts/build_index.py

# With fake embeddings (no API key, fast, for testing)
lnf build-index --cache ./data/cached_docs --store ./data/vector_store
```

**Vector Store Types:**
- **FAISS (default):** Fast CPU-based vector search
- **ChromaDB:** Alternative with persistent storage

**Configuration (.env):**
```env
VECTOR_STORE_TYPE=faiss
VECTOR_STORE_PATH=./data/vector_store
```

### Retrieval Best Practices

1. **Privacy:** All RAG operations use local cached docs by default (no external API calls in stub mode)
2. **Performance:** FAISS index is loaded once and reused across requests
3. **Offline-Ready:** Cached docs enable full offline operation in stub mode
4. **Customization:** Add your own documentation by extending `DocsIndexer.DOCS_URLS` in `src/langgraph_system_generator/rag/indexer.py`

---

## Web API Reference

### Endpoints

**`GET /`** - Web Interface
- Returns HTML web UI for interactive system generation
- No authentication required

**`GET /health`** - Health Check
- Returns: `{"status": "ok"}`
- Use for monitoring and load balancer health checks

**`POST /generate`** - Generate System
- **Body:** JSON `GenerationRequest` (see below)
- **Returns:** JSON `GenerationResponse` with manifest and artifact paths

### Request Schema

```json
{
  "prompt": "Create a customer support chatbot with routing",
  "mode": "stub",  // or "live"
  "output_dir": "./output/my_system",
  "formats": ["ipynb", "html", "docx", "zip"],  // optional
  
  // Advanced options (all optional)
  "model": "gpt-4-turbo-preview",
  "temperature": 0.7,
  "max_tokens": 4096,
  "agent_type": "router",
  "memory_config": "short",
  "graph_style": "sequential",
  "retriever_type": "vector",
  "document_loader": "web"
}
```

### Response Schema

```json
{
  "success": true,
  "mode": "stub",
  "prompt": "Create a customer support chatbot with routing",
  "manifest": {
    "notebook_path": "./output/my_system/notebook.ipynb",
    "html_path": "./output/my_system/notebook.html",
    "docx_path": "./output/my_system/notebook.docx",
    "zip_path": "./output/my_system/notebook_bundle.zip",
    "plan_path": "./output/my_system/notebook_plan.json",
    "cells_path": "./output/my_system/generated_cells.json"
  },
  "manifest_path": "./output/my_system/manifest.json",
  "output_dir": "./output/my_system"
}
```

### Error Handling

**API Errors:**
- Return HTTP 400 for invalid requests (bad prompt, invalid mode, etc.)
- Return HTTP 500 for internal errors (generation failures, file I/O errors)
- Error responses include `{"success": false, "error": "Human-readable message"}`

**Error Messages:**
- Always surface **clear, actionable** error messages
- Avoid cryptic tracebacks in API responses
- Log full stack traces server-side for debugging

---

## Contribution Guidelines

### Modular Design

**Principles:**
- **Single Responsibility:** Each function/class has one clear purpose
- **Composability:** Small, reusable functions over monolithic implementations
- **Isolation:** Side effects (file I/O, API calls) isolated in specific modules
- **Testability:** All logic testable without external dependencies

**Example:**
```python
# ✓ GOOD - Composable, testable
def extract_constraints(prompt: str) -> List[Constraint]:
    """Extract constraints from prompt (pure logic)."""
    ...

def save_constraints(constraints: List[Constraint], path: Path) -> None:
    """Save constraints to file (isolated side effect)."""
    ...

# ✗ BAD - Mixed concerns, hard to test
def extract_and_save_constraints(prompt: str, path: Path) -> None:
    """Extract and save constraints (mixed logic and I/O)."""
    ...
```

### Documentation Requirements

**Required Documentation:**
- **Public functions/methods:** Docstrings with Args, Returns, Raises
- **Classes:** Docstring explaining purpose and key attributes
- **Modules:** Module-level docstring explaining scope
- **Notebooks:** Cell-level Markdown for context and explanations

**Optional but Recommended:**
- **Complex algorithms:** Inline comments explaining logic
- **Type aliases:** Comment explaining purpose
- **Configuration:** Document .env variables and their effects

### Extension Hooks

When adding new features:

1. **New Agent Types:** Add to `src/langgraph_system_generator/generator/agents/` and register in graph
2. **New Patterns:** Create module in `src/langgraph_system_generator/patterns/` with code generators
3. **New Export Formats:** Extend `NotebookExporter` in `src/langgraph_system_generator/notebook/exporter.py`
4. **New RAG Sources:** Add URLs to `DocsIndexer.DOCS_URLS` in `src/langgraph_system_generator/rag/indexer.py`

**Document All Extensions:** Update relevant docs (`patterns.md`, `README.md`, `GEMINI.md`) and add examples.

### Dependency Management

**Default Policy:** **DO NOT add dependencies without strong justification.**

**When Adding Dependencies:**
1. Explain why existing libraries are insufficient
2. Verify license compatibility (prefer MIT, Apache 2.0, BSD)
3. Check maintenance status (recent updates, active community)
4. Add to both `requirements.txt` AND `setup.py` (extras_require if optional)
5. Document in PR description and inline comments if non-obvious

**Example Justification:**
```python
# Using python-docx for DOCX generation because:
# 1. Standard library has no DOCX support
# 2. Well-maintained (last update: 2023-11)
# 3. Simple API for programmatic document creation
from docx import Document
```

---

## Anti-Patterns & What NOT to Do

### Security Anti-Patterns

❌ **DO NOT hardcode API keys or secrets**
```python
# ✗ WRONG
openai_api_key = "sk-..."

# ✓ CORRECT
from langgraph_system_generator.utils.config import settings
openai_api_key = settings.openai_api_key  # From .env
```

❌ **DO NOT bypass artifact validation**
```python
# ✗ WRONG - Skipping QA checks
notebook = build_notebook(cells)
export_notebook(notebook)  # No validation!

# ✓ CORRECT - Always validate
notebook = build_notebook(cells)
qa_reports = validator.validate_all(notebook_path)
if not all(r.passed for r in qa_reports):
    repair_notebook(notebook_path, qa_reports)
```

❌ **DO NOT log sensitive user data**
```python
# ✗ WRONG - User prompt may contain sensitive info
logger.info(f"Processing prompt: {user_prompt}")

# ✓ CORRECT - Sanitize or avoid logging
logger.info(f"Processing prompt of length {len(user_prompt)}")
```

### Code Quality Anti-Patterns

❌ **DO NOT use bare `except` clauses**
```python
# ✗ WRONG
try:
    result = call_llm(prompt)
except:
    return None

# ✓ CORRECT - Catch specific exceptions
try:
    result = call_llm(prompt)
except (TimeoutError, APIError) as e:
    logger.error(f"LLM call failed: {e}")
    raise
```

❌ **DO NOT mutate function arguments**
```python
# ✗ WRONG
def add_constraint(constraints: List[Constraint], new: Constraint) -> List[Constraint]:
    constraints.append(new)  # Mutates input!
    return constraints

# ✓ CORRECT
def add_constraint(constraints: List[Constraint], new: Constraint) -> List[Constraint]:
    return constraints + [new]  # Returns new list
```

❌ **DO NOT use `Any` type hints without justification**
```python
# ✗ WRONG - Lazy typing
def process(data: Any) -> Any:
    ...

# ✓ CORRECT - Specific types
def process(data: Dict[str, str]) -> List[CellSpec]:
    ...
```

### Notebook Generation Anti-Patterns

❌ **DO NOT generate notebooks with unresolved placeholders**
```python
# ✗ WRONG - Leaves TODO in generated code
code = "# TODO: Implement authentication\npass"

# ✓ CORRECT - Provide working implementation or clear instructions
code = "# Authentication configuration (add your keys in .env)\nauth = get_auth_from_env()"
```

❌ **DO NOT bypass stub/live mode logic**
```python
# ✗ WRONG - Calling LLM in stub mode
if mode == "stub":
    result = llm.invoke(prompt)  # Defeats purpose of stub mode!

# ✓ CORRECT - Respect mode
if mode == "stub":
    result = generate_stub_architecture(prompt)
else:
    result = llm.invoke(prompt)
```

❌ **DO NOT ignore QA repair suggestions**
```python
# ✗ WRONG - QA repair loop that doesn't actually repair
def repair_node(state: GeneratorState) -> GeneratorState:
    state["repair_attempts"] += 1
    return state  # No actual repair!

# ✓ CORRECT - Implement repair logic
def repair_node(state: GeneratorState) -> GeneratorState:
    qa_reports = state["qa_reports"]
    cells = state["generated_cells"]
    repaired_cells = qa_agent.repair(cells, qa_reports)
    state["generated_cells"] = repaired_cells
    state["repair_attempts"] += 1
    return state
```

### Workflow Anti-Patterns

❌ **DO NOT mix stub and live mode artifacts**
```python
# ✗ WRONG
if mode == "stub":
    architecture = stub_architecture()
    cells = llm_generate_cells(architecture)  # Still uses LLM!

# ✓ CORRECT - Consistent mode throughout
if mode == "stub":
    architecture = stub_architecture()
    cells = stub_generate_cells(architecture)
```

❌ **DO NOT skip vector index in live mode**
```python
# ✗ WRONG - Missing RAG context
if mode == "live":
    architecture = select_architecture(constraints, [])  # Empty docs!

# ✓ CORRECT - Retrieve relevant docs
if mode == "live":
    docs = retriever.retrieve(prompt)
    architecture = select_architecture(constraints, docs)
```

---

## Agent Behavior Guidelines

### Response Expectations

When assisting with this repository, the Gemini agent should:

1. **Propose System Architectures:**
   - Suggest router, subagents, or hybrid patterns based on user requirements
   - Justify architecture choices with clear reasoning
   - Consider scalability, maintainability, and performance trade-offs

2. **Write Code to Match Repository Style:**
   - Follow Black formatting (no manual adjustments needed, just follow conventions)
   - Use explicit type hints for all public interfaces
   - Write Google-style docstrings for all functions/classes
   - Prefer Pydantic models for data structures

3. **Provide Actionable Advice:**
   - Give specific commands and code snippets, not just general guidance
   - Reference actual files in the repo (`src/langgraph_system_generator/...`)
   - Explain *why* a change is recommended, not just *what* to change

4. **Generate Notebook Content:**
   - Create well-structured notebooks with clear Markdown sections
   - Include working code examples, not just skeleton implementations
   - Add inline comments for complex logic
   - Ensure Colab compatibility (avoid local-only dependencies)

5. **Debug and Troubleshoot:**
   - When diagnosing issues, check logs, QA reports, and validation output
   - Suggest specific fixes for common errors (import errors, type mismatches, etc.)
   - Consider both stub and live mode contexts when debugging

### Code Generation Guidelines

**When generating new nodes/agents:**
```python
# ✓ Include full type hints and docstrings
def new_node(state: GeneratorState) -> GeneratorState:
    """Node description and purpose.
    
    Args:
        state: Current generator state
    
    Returns:
        Updated generator state with new field populated
    """
    # Implementation with clear logic
    ...
    return state
```

**When generating patterns:**
```python
# ✓ Include complete, runnable examples
class NewPattern:
    """Pattern description and use case."""
    
    @staticmethod
    def generate_complete_example(
        param1: List[str],
        param2: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate complete pattern code.
        
        Args:
            param1: Description of param1
            param2: Description of param2 (optional)
        
        Returns:
            Fully functional Python code as string
        """
        # Implementation
        ...
```

**When suggesting modifications:**
- Propose minimal, surgical changes
- Provide before/after diffs when helpful
- Explain impact on existing functionality
- Suggest tests to validate changes

### Testing and Validation

When recommending changes:

1. **Suggest Test Cases:**
   - Unit tests for new functions/classes
   - Integration tests for workflow changes
   - Pattern tests for new patterns

2. **Provide Test Commands:**
   ```bash
   pytest tests/unit/test_new_feature.py -v
   pytest --cov=langgraph_system_generator.patterns.new_pattern
   ```

3. **Validate Backwards Compatibility:**
   - Consider impact on existing notebooks
   - Check if API changes break existing code
   - Suggest deprecation warnings if needed

---

## Common Use Cases & Examples

### Example User Prompts

**Router-Based System:**
```
Create a router-based chatbot that can search documentation, answer questions, 
and escalate to human support when needed.
```

**Subagents System:**
```
Build a research assistant with specialized agents for web search, data analysis, 
and report writing, coordinated by a supervisor.
```

**Critique-Revise System:**
```
Generate a content creation system that writes articles, critiques them for 
quality and accuracy, then revises them until they meet standards.
```

**Hybrid System:**
```
Create a customer support system that routes to specialized agents (billing, 
technical, general), with each agent having sub-agents for complex tasks.
```

### Expected Multi-Agent Invocations

**CLI:**
```bash
# Quick stub generation for testing
lnf generate "Create a chatbot" --mode stub --output ./test

# Full live generation with all formats
lnf generate "Create a research assistant" --mode live --formats ipynb html docx pdf zip

# Specific architecture and configuration
lnf generate "Build a router system" --mode live \
  --formats ipynb html \
  --output ./output/router_system
```

**API:**
```python
import httpx

response = httpx.post(
    "http://localhost:8000/generate",
    json={
        "prompt": "Create a data analysis pipeline",
        "mode": "live",
        "model": "gpt-4-turbo-preview",
        "temperature": 0.7,
        "agent_type": "subagents",
        "formats": ["ipynb", "html", "docx"]
    }
)

manifest = response.json()["manifest"]
print(f"Notebook: {manifest['notebook_path']}")
```

**Pattern Library:**
```python
from langgraph_system_generator.patterns import RouterPattern

# Generate and execute router code
code = RouterPattern.generate_complete_example(
    routes=["search", "analyze"],
    route_purposes={"search": "Search docs", "analyze": "Analyze data"}
)

# Save and execute
with open("router_system.py", "w") as f:
    f.write(code)

exec(code)  # Run the generated system
```

### Environment Variable Configuration

**Required for Live Mode:**
```env
OPENAI_API_KEY=sk-proj-...
```

**Optional:**
```env
ANTHROPIC_API_KEY=sk-ant-...  # For Claude models
LANGSMITH_API_KEY=lsv2_pt_...  # For tracing
LANGSMITH_PROJECT=my-project
VECTOR_STORE_TYPE=faiss
VECTOR_STORE_PATH=./data/vector_store
DEFAULT_MODEL=gpt-4-turbo-preview
MAX_REPAIR_ATTEMPTS=3
DEFAULT_BUDGET_TOKENS=100000
```

**Switching Modes:**
```bash
# Stub mode (no .env needed)
lnf generate "Create a chatbot" --mode stub

# Live mode (requires .env with API keys)
lnf generate "Create a chatbot" --mode live
```

---

## Tips for Effective Usage

### Prompt Engineering for Best Results

**Specific Prompts:**
```
✓ "Create a customer support system with routing to billing, technical, and 
   general support agents. Include memory for conversation context."

✗ "Make a chatbot"
```

**Architecture Hints:**
```
✓ "Build a research system with a supervisor coordinating researcher, analyst, 
   and writer subagents."

✗ "Create a research system"  (less clear architecture)
```

**Constraint Specification:**
```
✓ "Generate a minimal router system with 2-3 routes, prioritizing code clarity 
   over feature completeness."

✗ "Make it good"  (vague constraint)
```

### Performance Optimization

**Stub Mode for Development:**
- Use stub mode during development for fast iteration
- Switch to live mode only when validating final behavior

**Selective Format Generation:**
```bash
# Fast: Only notebook
lnf generate "prompt" --formats ipynb

# Slower: All formats
lnf generate "prompt" --formats ipynb html docx pdf zip
```

**Vector Index Caching:**
- Build index once, reuse across sessions
- Index is loaded once at server startup, shared across requests

### Debugging Tips

**Check QA Reports:**
```python
# After generation, inspect QA reports
with open("output/manifest.json") as f:
    manifest = json.load(f)

# Look for validation issues
if not manifest.get("success"):
    print(manifest.get("error"))
```

**Validate Notebook Manually:**
```bash
# Open in Jupyter to test execution
jupyter notebook output/notebook.ipynb

# Check for imports and basic structure
python -c "import nbformat; nb = nbformat.read('output/notebook.ipynb', 4); print(nb.cells[0])"
```

**Verbose Mode (if available):**
```bash
# Run with debug logging
export LOG_LEVEL=DEBUG
lnf generate "prompt" --mode live
```

---

## Additional Resources

### Documentation
- **README.md:** Project overview and quickstart
- **docs/patterns.md:** Comprehensive pattern library guide
- **docs/WEB_UI_VISUAL_GUIDE.md:** Web interface feature documentation
- **docs/NOTEBOOK_OUTPUT_GUIDE.md:** Output format specifications
- **data/cached_docs/README.md:** Cached documentation details

### Examples
- **examples/router_pattern_example.py:** Router pattern demonstration
- **examples/subagents_pattern_example.py:** Subagents pattern demonstration
- **examples/critique_revise_pattern_example.py:** Critique-revise pattern demonstration

### Key Files to Reference
- **src/langgraph_system_generator/api/server.py:** FastAPI endpoints and web UI
- **src/langgraph_system_generator/cli.py:** CLI implementation and entry points
- **src/langgraph_system_generator/generator/graph.py:** Main generation workflow
- **src/langgraph_system_generator/generator/state.py:** State models and schemas
- **src/langgraph_system_generator/patterns/:** Pattern code generators
- **src/langgraph_system_generator/notebook/exporter.py:** Multi-format export logic

---

## Current Development Context

**Version:** 0.1.1

**Recent Focus Areas:**
- Web UI enhancements and responsive design
- Multi-format notebook export (IPYNB, HTML, DOCX, PDF, ZIP)
- Pattern library refinement and documentation
- QA/repair system improvements
- RAG caching and offline mode optimization

**Known Limitations:**
- PDF export requires additional system dependencies (wkhtmltopdf or similar)
- Live mode requires external API keys (OpenAI by default)
- Maximum token limits depend on configured LLM model
- Repair system has 3-attempt maximum to prevent infinite loops

**Upcoming/Requested Features:**
- Additional pattern templates
- More LLM provider support (Anthropic, Cohere, local models)
- Enhanced validation and repair logic
- Streaming generation progress
- Multi-language notebook support

---

## Summary for Gemini Agent

**When working with this repository:**

1. **Respect the dual-mode design** - stub for fast testing, live for quality generation
2. **Follow Black + Ruff + type hints** - no exceptions for public APIs
3. **Use Pydantic v2 models** - consistent data validation and serialization
4. **Generate complete, working code** - not just sketches or TODOs
5. **Provide clear, actionable guidance** - specific commands and file references
6. **Test your suggestions** - consider unit, integration, and pattern tests
7. **Document new features** - update GEMINI.md, README.md, and relevant docs
8. **Check for anti-patterns** - hardcoded secrets, mutation, bare exceptions, etc.
9. **Leverage the pattern library** - reuse existing patterns when possible
10. **Be explicit about dependencies** - justify any new dependencies added

**This repository is about empowering users to generate sophisticated multi-agent systems from simple prompts. Your role is to help maintain code quality, extend functionality cleanly, and ensure generated artifacts are production-ready.**
