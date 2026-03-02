# Project Brief

## Purpose
- Generate complete LangGraph-based multi-agent systems from a single prompt, producing runnable notebooks and associated artifacts.

## Goals
- Provide offline-friendly generation (stub mode) and live LLM-backed generation (live mode).
- Offer multiple interfaces: CLI, REST API, and web UI.
- Ship production-ready outputs: notebook, HTML, DOCX, ZIP (optional PDF) plus JSON manifests (plan, cells, manifest).
- Maintain reusable pattern library (Router, Subagents, Critique-Revise) with high test coverage and QA/repair loop.

## Scope
- Input: user prompt plus optional constraints (formats, mode, model, tools, memory, output dir).
- Output: artifacts written under configurable output base (`LNF_OUTPUT_BASE`), including notebook and export formats.
- Supports cached docs retrieval (LangGraph/LangChain) and FAISS vector store for RAG.

## Non-Goals
- Running generated workflows in production environments directly from this repo.
- Maintaining external connectors beyond documented tools.

## Success Criteria
- Users can generate notebooks via CLI/API/web without editing code manually.
- Outputs compile and pass basic QA/validation; repair loop addresses common issues.
- Pattern examples remain runnable; tests pass locally.

## Stakeholders / Users
- Developers needing agentic system scaffolds.
- Notebook-first workflows (Jupyter/Colab) consumers.
- API/web UI users generating artifacts for downstream customization.
