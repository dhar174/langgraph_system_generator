## Project Scope

- `langgraph_system_generator` is a Python package for turning a natural-language
  prompt into scaffolded LangGraph system artifacts, primarily as runnable
  Jupyter notebooks plus companion export files.
- The repository supports three main usage surfaces:
  - a CLI (`lnf generate`, `lnf build-index`)
  - a FastAPI/web interface
  - a reusable pattern library for generating common LangGraph architectures

## Primary Goals

- Generate notebook-based multi-agent system scaffolds from simple user prompts.
- Support an offline-friendly deterministic `stub` mode and a `live` mode that
  invokes the full LangGraph generator workflow.
- Package outputs into practical artifacts such as `.ipynb`, `.html`, `.docx`,
  `.pdf`, `.zip`, and JSON metadata files.
- Provide reusable pattern generators for router, supervisor/subagents, and
  critique-revise workflows.

## Repository Boundaries

- The repo is focused on scaffolding and artifact generation, not on hosting a
  long-running production agent runtime.
- Live generation currently depends on external LLM credentials; offline stub
  generation exists so core flows can work without remote model calls.
- Retrieval is built around precached LangGraph/LangChain documentation and a
  local vector index rather than live web scraping during generation.
