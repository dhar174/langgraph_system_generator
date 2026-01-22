# LangGraph System Generator - Copilot Instructions

This is a Python-based repository that generates complete multi-agent LangGraph systems from natural language prompts. The project includes a web interface, CLI tool, pattern library, and RAG-powered documentation system.

## Code Standards

### Required Before Each Commit
- Run `black .` to format Python code
- Run `ruff check .` to lint code
- Run `mypy src/` for type checking
- These tools maintain consistent code style and catch issues early

### Development Flow
- **Install dependencies**: `pip install -r requirements.txt`
- **Build**: No separate build step required for Python
- **Test**: `pytest` or `python -m pytest` to run all tests
- **Test with coverage**: `pytest --cov=src --cov-report=html`
- **Format code**: `black .`
- **Lint**: `ruff check .`
- **Type check**: `mypy src/`
- **Run web interface**: `uvicorn langgraph_system_generator.api.server:app --host 0.0.0.0 --port 8000`
- **CLI usage**: `lnf generate "Create a chatbot" --output ./output/demo --mode stub`

### Python Version
- **Minimum**: Python 3.9
- **Recommended**: Python 3.10 or 3.11
- Use virtual environments: `python -m venv .venv`

## Repository Structure

- `src/langgraph_system_generator/`: Main package source code
  - `agents/`: LangGraph agent implementations (architecture selector, requirements analyst, etc.)
  - `api/`: FastAPI server for web interface
  - `cli.py`: Command-line interface
  - `patterns/`: Pattern library (Router, Subagents, Critique-Revise Loop)
  - `rag/`: RAG system for documentation retrieval
  - `notebook/`: Notebook generation, validation, and repair
  - `config.py`: Configuration management with Pydantic Settings
  - `models.py`: Pydantic models for data structures
- `tests/`: Test suite
  - `unit/`: Unit tests for individual components
  - `integration/`: Integration tests for end-to-end workflows
  - `patterns/`: Pattern library tests
  - `fixtures/`: Test fixtures and sample data
  - `conftest.py`: pytest configuration and shared fixtures
- `data/`: Data files
  - `cached_docs/`: Pre-cached LangGraph and LangChain documentation
  - `vector_store/`: FAISS vector store for RAG
- `examples/`: Example scripts demonstrating pattern usage
- `docs/`: Documentation
- `scripts/`: Utility scripts (e.g., `build_index.py` for building vector store)

## Key Guidelines

1. **Follow Python best practices**:
   - Use type hints for function parameters and return values
   - Follow PEP 8 style guide (enforced by black and ruff)
   - Write docstrings for public classes and functions
   - Use Pydantic models for data validation and configuration

2. **Testing requirements**:
   - Write unit tests for new functionality
   - Place tests in appropriate subdirectories under `tests/`
   - Use pytest fixtures defined in `conftest.py`
   - Aim for high test coverage (≥90% for pattern modules)
   - Use pytest marks for categorizing tests: `@pytest.mark.unit`, `@pytest.mark.integration`

3. **LangGraph and LangChain usage**:
   - Use LangGraph StateGraph for workflow orchestration
   - Follow LangGraph patterns: Router, Subagents, Critique-Revise Loop
   - Leverage the pattern library in `src/langgraph_system_generator/patterns/`
   - Use the RAG system for retrieving relevant documentation snippets

4. **Code organization**:
   - Keep agent logic in `src/langgraph_system_generator/agents/`
   - Pattern implementations go in `src/langgraph_system_generator/patterns/`
   - API endpoints in `src/langgraph_system_generator/api/`
   - Shared models in `src/langgraph_system_generator/models.py`

5. **Configuration management**:
   - Use Pydantic Settings for configuration (`config.py`)
   - Environment variables via `.env` file (see `.env.example`)
   - Required API keys: `OPENAI_API_KEY` for live mode
   - Optional: `ANTHROPIC_API_KEY`, `LANGSMITH_API_KEY`

6. **Web interface**:
   - FastAPI application in `src/langgraph_system_generator/api/server.py`
   - Static files (HTML/CSS/JS) in `src/langgraph_system_generator/api/static/`
   - Follow existing API patterns for new endpoints
   - Maintain backward compatibility with existing API contracts

7. **Notebook generation**:
   - Generated notebooks must be valid Jupyter notebooks (nbformat)
   - Include all required imports and dependencies
   - Ensure code cells are executable
   - Support export to multiple formats: IPYNB, HTML, DOCX, PDF, ZIP

8. **Documentation**:
   - Update relevant documentation in `docs/` when making significant changes
   - Keep README.md up to date with new features
   - Document new patterns in `docs/patterns.md`

## Custom Agents

This repository has specialized custom agents for different areas:
- **lnf-lead**: Lead architect for overall system design
- **lnf-generator**: Core generation logic and workflow
- **lnf-patterns**: Pattern library development
- **lnf-notebook**: Notebook generation and export
- **lnf-rag**: RAG system and documentation indexing
- **lnf-webui**: Web interface and API development
- **lnf-cli**: Command-line interface
- **lnf-docs**: Documentation updates
- **lnf-qa**: Quality assurance and testing
- **lnf-security**: Security review and vulnerability checks

When working on specific areas, consider using the relevant custom agent for domain expertise.

## Working with Dependencies

- **Core dependencies**: LangGraph, LangChain, OpenAI, Pydantic
- **Notebook generation**: nbformat, nbconvert, python-docx, reportlab
- **RAG system**: FAISS, sentence-transformers
- **Web interface**: FastAPI, uvicorn
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Dev tools**: black, ruff, mypy

When adding new dependencies:
1. Add to `requirements.txt` for production dependencies
2. Add to `setup.py` under appropriate `extras_require` section
3. Document why the dependency is needed
4. Check for security vulnerabilities
5. Prefer well-maintained, popular packages

## Common Patterns

1. **Agent implementation**: Extend base patterns, use StateGraph
2. **Testing**: Use fixtures from `conftest.py`, mock external API calls
3. **Error handling**: Use try-except blocks, log errors appropriately
4. **Logging**: Use Python logging module, not print statements
5. **Configuration**: Load from `Settings` class, support environment variables

## Stub vs Live Mode

The system supports two modes:
- **Stub mode**: Fast, no API keys required, generates mock data for testing
- **Live mode**: Uses LLMs to generate real content, requires `OPENAI_API_KEY`

When developing, test both modes to ensure functionality works correctly.
