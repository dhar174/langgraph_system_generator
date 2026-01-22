# Copilot Instructions for LangGraph System Generator

## Repository Overview

**What it does**: LangGraph System Generator (LangGraph Notebook Foundry) is a Python tool that generates complete multi-agent systems from simple text prompts. It creates production-ready Jupyter notebooks with LangGraph/LangChain workflows, supporting three core patterns (Router, Subagents, Critique-Revise Loop).

**Size & Scope**: ~7GB total (includes .venv), ~6,800 lines of Python code across ~40 source files
**Languages**: Python 3.9+ (tested with 3.12.3)
**Key Frameworks**: LangGraph ≥0.2.0, LangChain ≥0.3.0, FastAPI ≥0.115.0, Pytest ≥7.4.0
**Output Formats**: Jupyter notebooks (.ipynb), HTML, DOCX, PDF, ZIP bundles

## Build & Environment Setup

### Initial Setup (CRITICAL - Follow This Order)

**ALWAYS** use a virtual environment to avoid dependency conflicts:

```bash
# 1. Create virtual environment (REQUIRED)
python3 -m venv .venv

# 2. Install dependencies (takes 3-5 minutes)
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 3. Install package in editable mode
.venv/bin/pip install -e .

# 4. Copy environment template (optional for development)
cp .env.example .env
# Edit .env to add API keys if testing live mode
```

**IMPORTANT**: All subsequent commands MUST use `.venv/bin/python` or `.venv/bin/<tool>` prefix, or activate the venv with `source .venv/bin/activate`.

### Environment Variables

Required only for "live mode" (LLM-powered generation):
- `OPENAI_API_KEY` - OpenAI API key for LLM calls
- `ANTHROPIC_API_KEY` - Alternative LLM provider (optional)
- `LANGSMITH_API_KEY` - LangSmith tracing (optional)

**Stub mode** (default) requires NO API keys and generates placeholder content for testing.

## Testing

### Run Tests (Expected Results)

```bash
# Run all tests (expect some failures - see Known Issues below)
.venv/bin/pytest tests/ -v

# Run specific test suites
.venv/bin/pytest tests/unit/ -v              # Unit tests (~149 pass, 14 fail)
.venv/bin/pytest tests/integration/ -v       # Integration tests
.venv/bin/pytest tests/patterns/ -v          # Pattern generation tests

# Run with coverage
.venv/bin/pytest tests/ --cov=src/langgraph_system_generator --cov-report=html
```

**Known Test Failures** (not your responsibility to fix):
- 14 unit tests fail with `NameError: name 'MODEL' is not defined` in templates.py line 90
- 1 test fails with assertion about `llm_with_tools.invoke(` in generated code
- These are pre-existing issues unrelated to most development tasks

### Testing Time Requirements
- Unit tests: ~6-10 seconds
- Full test suite: ~30-60 seconds
- Integration tests may timeout if system is slow; if tests timeout, re-run individually

## Code Quality & Linting

### Formatting & Style

```bash
# Check formatting (EXPECT failures - code needs reformatting)
.venv/bin/black --check src/ tests/

# Auto-format code
.venv/bin/black src/ tests/

# Run linter (EXPECT some warnings)
.venv/bin/ruff check src/

# Type checking (may take 30-60 seconds, can be slow)
.venv/bin/mypy src/ --ignore-missing-imports
```

**Known Linting Issues**:
- Black would reformat ~29 files (normal - run `black` to fix before committing)
- Ruff reports unused imports in `generator/utils.py` and undefined `MODEL` in `notebook/templates.py`
- DO NOT run mypy unless necessary (very slow, 30+ seconds)

## CLI Usage

### Command Structure

The CLI is accessible via the `lnf` command after installation:

```bash
.venv/bin/lnf --help                    # Show main help
.venv/bin/lnf generate --help           # Show generate command help
.venv/bin/lnf build-index --help        # Show index building help
```

### Generate Notebooks (Stub Mode - No API Key Needed)

```bash
# Basic generation (creates all formats)
.venv/bin/lnf generate "Create a customer support chatbot" \
    --mode stub \
    --output ./output/demo

# Generate specific formats only
.venv/bin/lnf generate "Create a data analysis workflow" \
    --mode stub \
    --output ./output/analysis \
    --formats ipynb html docx

# Available formats: ipynb, html, docx, pdf, zip
```

**IMPORTANT**: Stub mode may fail with template errors (MODEL undefined) but this is a known issue. Generated artifacts should still be created in most cases.

### Build Vector Index

```bash
# Build index from precached docs (no API key needed, uses fake embeddings)
.venv/bin/lnf build-index \
    --cache ./data/cached_docs \
    --store ./data/vector_store
```

## Web Server

### Starting the Server

```bash
# Start development server
.venv/bin/uvicorn langgraph_system_generator.api.server:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload

# Access at: http://localhost:8000
```

**Features**:
- Modern web UI for system generation
- REST API at `/generate` endpoint
- Health check at `/health`
- Serves static files from `src/langgraph_system_generator/api/static/`

### Docker Deployment

```bash
# Build image
docker build -t lnf .

# Run container
docker run -p 8000:8000 \
    -e OPENAI_API_KEY=sk-... \
    -v $(pwd)/output:/app/output \
    lnf
```

## Project Structure

### Key Directories

```
.
├── src/langgraph_system_generator/     # Main source code
│   ├── api/                            # FastAPI web server & REST API
│   │   ├── server.py                   # Main FastAPI application
│   │   └── static/                     # Web UI (HTML, CSS, JS)
│   ├── cli.py                          # Command-line interface (lnf command)
│   ├── generator/                      # Core generation logic
│   │   ├── agents/                     # LLM-powered agents
│   │   ├── graph.py                    # LangGraph workflow definition
│   │   └── state.py                    # GeneratorState & data models
│   ├── notebook/                       # Notebook building & export
│   │   ├── composer.py                 # Notebook assembly
│   │   ├── exporters.py                # Format conversion (HTML, PDF, etc.)
│   │   └── templates.py                # Code cell templates
│   ├── patterns/                       # Pattern library
│   │   ├── router.py                   # Router pattern
│   │   ├── subagents.py                # Subagents pattern
│   │   └── critique_loops.py           # Critique-revise pattern
│   ├── qa/                             # Quality assurance & validation
│   │   ├── validators.py               # Notebook validators
│   │   └── repair.py                   # Repair agent
│   ├── rag/                            # Documentation retrieval
│   │   ├── indexer.py                  # Doc scraping & indexing
│   │   ├── cache.py                    # Document cache management
│   │   └── retriever.py                # Vector search
│   └── utils/                          # Shared utilities
│       └── config.py                   # Settings (pydantic)
├── tests/                              # Test suite
│   ├── unit/                           # Unit tests
│   ├── integration/                    # Integration tests
│   ├── patterns/                       # Pattern-specific tests
│   └── conftest.py                     # Pytest configuration
├── data/                               # Cached documentation & indices
│   ├── cached_docs/                    # Precached LangGraph/LangChain docs
│   │   └── documents.json              # ~300KB, 19+ documents
│   └── vector_store/                   # FAISS vector index (auto-generated)
├── docs/                               # Documentation
├── examples/                           # Pattern usage examples
│   ├── router_pattern_example.py
│   ├── subagents_pattern_example.py
│   └── critique_revise_pattern_example.py
├── scripts/                            # Utility scripts
│   ├── build_index.py                  # Build vector index
│   └── demo_retrieval.py               # Demo RAG retrieval
├── requirements.txt                    # Python dependencies
├── setup.py                            # Package configuration
├── Dockerfile                          # Container definition
└── .env.example                        # Environment template
```

### Configuration Files

- **requirements.txt**: All Python dependencies (~38 packages)
- **setup.py**: Package metadata, entry points, extras (api, full, dev)
- **.gitignore**: Excludes .venv/, output/, data/cached_docs/documents.json, etc.
- **.env.example**: Environment variable template
- **Dockerfile**: Python 3.11-slim base, exposes port 8000

### Important Files to Review

1. **src/langgraph_system_generator/cli.py**: CLI entry point, generation orchestration
2. **src/langgraph_system_generator/generator/graph.py**: Main LangGraph workflow
3. **src/langgraph_system_generator/patterns/*.py**: Pattern code generators
4. **src/langgraph_system_generator/api/server.py**: Web server & API
5. **tests/conftest.py**: Pytest setup (adds src/ to path)

## CI/CD & Validation

### GitHub Workflows

All workflows are currently **COMMENTED OUT** (python-app.yml is disabled). Active workflows:
- **diagram.yml**: Auto-generates repo visualization on push to main
- **wiki-*.yml**: Wiki page generation workflows
- **summary.yml**: Repository summary generation

**No active CI/CD for code validation** - you must test locally before pushing.

### Pre-Commit Checklist

Before committing code changes:

```bash
# 1. Format code
.venv/bin/black src/ tests/

# 2. Run linter (fix critical issues only)
.venv/bin/ruff check src/

# 3. Run relevant tests
.venv/bin/pytest tests/unit/ -v

# 4. Test CLI if changed
.venv/bin/lnf generate "test" --mode stub --output /tmp/test --formats ipynb

# 5. Test web server if changed
timeout 5 .venv/bin/uvicorn langgraph_system_generator.api.server:app --port 8001 || true
```

## Common Issues & Solutions

### Issue: Import Errors After Fresh Clone
**Solution**: ALWAYS create venv and install with `pip install -e .` before running any code.

### Issue: `NameError: name 'MODEL' is not defined`
**Status**: Known bug in `notebook/templates.py` line 90
**Workaround**: Some tests and stub mode generation will fail. Not blocking for most development.

### Issue: Tests Timeout or Hang
**Solution**: Run with increased timeout or skip slow tests. Some integration tests may be flaky.

### Issue: Black Reports Many Files Need Reformatting
**Status**: Expected - code style not enforced in repo
**Solution**: Run `black src/ tests/` before committing to auto-format.

### Issue: Mypy Takes Forever
**Solution**: Skip mypy unless explicitly required. It's very slow (30-60+ seconds) and not enforced.

### Issue: Missing API Key Errors in Live Mode
**Solution**: Use `--mode stub` (default) for testing without API keys.

### Issue: Vector Index Not Found
**Solution**: Either (1) run `lnf build-index` to create it, or (2) use stub mode which doesn't need it.

## Development Workflow

### Making Code Changes

1. **Understand the area**: Review related files in `src/langgraph_system_generator/`
2. **Make minimal changes**: Keep modifications surgical and focused
3. **Test locally**: Run relevant test suite after changes
4. **Format code**: Run `black` on changed files
5. **Verify functionality**: Test CLI/API if those areas were modified
6. **Commit with descriptive message**

### Adding New Features

1. **Patterns**: Add to `src/langgraph_system_generator/patterns/`
2. **Tests**: Add to `tests/unit/` or `tests/integration/`
3. **Examples**: Add to `examples/` with README update
4. **Documentation**: Update `docs/` and relevant READMEs

### Testing Strategies

- **Unit tests**: Fast, test individual functions/classes
- **Integration tests**: Test full workflows, may need API keys
- **Pattern tests**: Validate code generation quality
- **Stub run**: Use stub mode for quick validation without API

## Key Dependencies

### Runtime (Core)
- **langgraph** ≥0.2.0: Multi-agent workflow framework
- **langchain** ≥0.3.0, **langchain-openai**, **langchain-community**: LLM integrations
- **nbformat** ≥5.9.0, **nbconvert** ≥7.14.0: Notebook handling
- **faiss-cpu** ≥1.7.4: Vector similarity search
- **fastapi** ≥0.115.0, **uvicorn** ≥0.30.0: Web server
- **pydantic** ≥2.5.0: Data validation & settings

### Development
- **pytest** ≥7.4.0, **pytest-asyncio**, **pytest-cov**: Testing
- **black** ≥23.0.0: Code formatting
- **ruff** ≥0.1.0: Fast linting
- **mypy** ≥1.7.0: Type checking (slow, optional)

### Document Generation
- **python-docx** ≥1.1.0: DOCX export
- **reportlab** ≥4.0.0: PDF export

## Architecture Overview

**Generation Flow**:
1. User provides prompt (CLI, API, or Web UI)
2. `RequirementsAnalyst` extracts constraints from prompt
3. `ArchitectureSelector` chooses pattern (router/subagents/critique-revise)
4. `GraphDesigner` creates workflow structure
5. `NotebookComposer` generates code cells
6. `QARepairAgent` validates & fixes issues
7. Export to formats (IPYNB, HTML, DOCX, PDF, ZIP)

**Modes**:
- **Stub Mode** (default): Fast, no API keys, placeholder content
- **Live Mode**: Full LLM generation, requires OPENAI_API_KEY

## Search & Navigation Tips

**Finding code**:
- Pattern implementations: `src/langgraph_system_generator/patterns/`
- Agent logic: `src/langgraph_system_generator/generator/agents/`
- Notebook assembly: `src/langgraph_system_generator/notebook/`
- CLI commands: `src/langgraph_system_generator/cli.py`
- API endpoints: `src/langgraph_system_generator/api/server.py`

**Finding tests**:
- Unit: `tests/unit/test_*.py`
- Integration: `tests/integration/test_*.py`
- Pattern-specific: `tests/patterns/test_*.py`

**Finding documentation**:
- User guides: `README.md`, `docs/*.md`
- Examples: `examples/README.md`
- Cached docs: `data/cached_docs/README.md`

## Trust These Instructions

These instructions were created by thoroughly exploring the codebase, running all build/test commands, and documenting actual results. Only search for additional information if:
- These instructions are incomplete for your specific task
- You encounter errors not documented here
- You need implementation details not covered here

**When in doubt**: Follow the build steps exactly as written, use stub mode for testing, and run relevant tests after changes.
