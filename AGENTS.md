# AGENTS.md

## Overview

This repository turns a plain-language prompt into a runnable LangGraph-based multi-agent system. It combines prompt analysis, architecture selection, workflow design, notebook generation, QA repair, export pipelines, and a FastAPI web UI, while also bundling cached LangGraph/LangChain docs for offline-friendly retrieval.

## Folder Structure

- `src/langgraph_system_generator/api/`: FastAPI server, request/response models, and web entrypoints.
- `src/langgraph_system_generator/generator/`: Core generation pipeline that analyzes prompts and plans the system.
- `src/langgraph_system_generator/patterns/`: Reusable LangGraph architecture patterns such as routers and supervisor/subagent flows.
- `src/langgraph_system_generator/notebook/`: Notebook composition plus HTML, DOCX, PDF, and ZIP export helpers.
- `src/langgraph_system_generator/qa/`: Validation and repair logic for generated notebooks and artifacts.
- `src/langgraph_system_generator/rag/`: Cached-doc indexing and retrieval logic used to ground generation.
- `examples/`: Small runnable pattern demos.
- `tests/`: Regression coverage for patterns, generation, and export behavior.
- `docs/`: Human-facing implementation notes and feature guides.
- `.github/skills/`: Repo-local agent skills. Prefer these first when a task matches one of them.
- `.github/agents/`, `.github/instructions/`, `.github/prompts/`: Additional repo-local agent guidance and prompt assets.

## Core Behaviors and Patterns

- Preserve the distinction between `stub` mode and `live` mode. Changes to generation flow should not accidentally force live LLM calls in offline/stub workflows.
- Prefer existing pattern modules and cached docs over inventing new graph structures from scratch.
- Treat the generator as a pipeline: prompt analysis, architecture selection, workflow design, tool planning, notebook composition, QA validation/repair, and export.
- When changing RAG or retrieval behavior, keep offline-friendly cached-doc behavior intact and avoid introducing unnecessary network assumptions.
- When changing generation or pattern code, think through downstream effects on notebook validation, exports, the CLI, and the FastAPI app.

## Conventions

- Use repo-local skills from `.github/skills/` before falling back to global skills.
- Do not edit vendored skill contents unless the task is specifically about maintaining or improving a skill.
- Prefer targeted changes in existing modules over adding parallel implementations.
- Keep docs in sync when behavior changes in generation, QA, exports, or skill usage.
- When adding new project skills, place them under `.github/skills/<skill-name>/` and make the description specific enough for auto-discovery.

## Skill Guide

Use these repo-local skills when the request matches their scope:

- [`langgraph-project-setup`](./.github/skills/langgraph-project-setup/SKILL.md): creating a new LangGraph project, configuring `langgraph.json`, wiring provider settings, or fixing project scaffolding/config issues.
- [`langgraph-agent-patterns`](./.github/skills/langgraph-agent-patterns/SKILL.md): choosing or implementing supervisor/subagent, router, orchestrator-worker, or handoff coordination patterns.
- [`langgraph-state-management`](./.github/skills/langgraph-state-management/SKILL.md): designing graph state, reducers, persistence, checkpointing, or debugging state merge/update behavior.
- [`langgraph-error-handling`](./.github/skills/langgraph-error-handling/SKILL.md): retries, recovery loops, interrupt/resume flows, escalation, or `ToolNode` failure handling.
- [`langgraph-testing-evaluation`](./.github/skills/langgraph-testing-evaluation/SKILL.md): unit/integration tests, mocked runs, trajectory evaluation, regression checks, or LangSmith-backed evaluation.
- [`deepagents-setup-configuration`](./.github/skills/deepagents-setup-configuration/SKILL.md): Deep Agents setup, migration, validation, or configuration for LangChain/LangGraph-based deep-agent workflows.
- [`deepagents-planning-todos`](./.github/skills/deepagents-planning-todos/SKILL.md): `write_todos` planning, task decomposition, todo lifecycle debugging, or trace-based todo analysis.
- [`langsmith-fetch`](./.github/skills/langsmith-fetch/SKILL.md): quickly debugging LangGraph/LangChain runs by pulling recent LangSmith traces into the terminal.
- [`langsmith-trace`](./.github/skills/langsmith-trace/SKILL.md): adding tracing to code, querying/exporting traces, or instrumenting runs for diagnosis.
- [`langsmith-evaluator`](./.github/skills/langsmith-evaluator/SKILL.md): evaluator design, offline/online evaluation setup, or grading model/graph behavior.
- [`langsmith-dataset`](./.github/skills/langsmith-dataset/SKILL.md): creating, curating, or updating LangSmith datasets used for testing and evaluation.

Supporting repo-local skills that are often useful alongside the LangGraph set:

- [`langchain`](./.github/skills/langchain/SKILL.md): framework-level LangChain guidance and agent/reference material.
- [`openai-docs`](./.github/skills/openai-docs/SKILL.md): current OpenAI API and product documentation workflows.
- [`jupyter-notebook`](./.github/skills/jupyter-notebook/SKILL.md): notebook creation or cleanup when generated notebook artifacts need hands-on edits.
- [`webapp-testing`](./.github/skills/webapp-testing/SKILL.md): browser-based verification for the FastAPI web UI.

## Working Agreements

- Start by checking whether an existing repo-local skill already fits the task before improvising a workflow.
- For LangGraph runtime bugs, prefer `langsmith-fetch` or `langsmith-trace` plus the relevant LangGraph skill instead of debugging blind.
- For architecture questions, consult `langgraph-agent-patterns` before changing pattern implementations in `src/langgraph_system_generator/patterns/`.
- For generation regressions, pair code changes with `langgraph-testing-evaluation` and the relevant tests under `tests/`.
- If a task changes how agents or skills should be used in this repo, update this file and the relevant docs in `.github/instructions/` or `docs/`.
