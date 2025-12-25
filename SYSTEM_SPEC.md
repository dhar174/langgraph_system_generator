
## Spec Sheet: LangGraph Notebook Foundry (LNF)

### 1) Purpose

Create a LangGraph-based “agentic generator” that takes a user request (e.g., “build me a multi-agent scifi novel pipeline with constraints X/Y/Z”) and outputs a **fully implemented, runnable, production-grade LangGraph workflow** as a **complete Jupyter/Colab notebook**, including:

* architecture choice (router vs subagents, critique/revise loops, map-reduce, etc.)
* full state schema + reducers
* nodes, conditional edges, retries, checkpointing
* tools + integrations
* end-to-end execution path that produces final artifacts (manuscript + formatting + marketing outputs)
* packaging into a downloadable folder/zip (and optionally Drive save)

LangGraph workflow patterns should be selected using **RAG over official docs** so the generator stays aligned with current best practices (e.g., using `create_agent` where recommended). ([LangChain Docs][1])

---

### 2) Inputs

**Primary input:** a single “project prompt” from the user:

* goal + deliverables (e.g., “full scifi novel + print-ready PDF + marketing kit”)
* constraints (tone, length, structure, banned tropes, style guides, etc.)
* runtime constraints (budget, max iterations, model choices, time limits)
* environment constraints (Colab, drive paths, allowed libraries, etc.)

**Optional inputs:**

* uploaded files (outlines, style guides, sample chapters)
* target format requirements (DOCX vs PDF, trim size, fonts, headings, etc.)
* policy constraints / allowed tool allowlist

---

### 3) Outputs

**Primary output:** a folder in the runtime containing:

* `generated_workflow.ipynb` (the complete notebook)
* `src/` (optional extracted Python modules for cleanliness)
* `artifacts/` (outputs produced when the notebook runs)
* `README.md` (how to run + configure)
* `requirements.txt` + `pip_freeze.txt` (reproducibility)

**Notebook must be runnable end-to-end** and include a smoke-test cell that compiles and runs the graph.

---

### 4) High-level Architecture

LNF itself is a LangGraph app that runs a *generation pipeline* (“outer graph”) to produce a *target workflow* (“inner graph code”) inside an ipynb.

#### 4.1 Outer Graph (the generator)

Use a **StateGraph**-based workflow with explicit stages and quality gates (compile/run checks). LangGraph Graph API concepts like conditional edges, loops, and `Command`/`Send` are used to implement branching and map-reduce style fan-out where needed. ([LangChain Docs][2])

**Recommended outer-graph nodes:**

1. **Intake & Constraint Extraction**
2. **Docs RAG Retrieval**
3. **Pattern Selection & Architecture Plan**
4. **State Schema Design**
5. **Tooling Plan & Integration Design**
6. **Notebook Assembly (nbformat)**
7. **Static QA (lint/type checks/structure validation)**
8. **Runtime QA (smoke execute: build graph + run minimal sample)**
9. **Repair Loop (if QA fails, patch & re-test)**
10. **Package Outputs (zip + optional nbconvert exports)**

#### 4.2 Inner Graph (the generated workflow)

This is what the notebook builds. It can be:

* **Subagents architecture** (a supervisor agent calls subagents as tools; subagents are stateless, supervisor holds memory/context). ([LangChain Docs][3])
* **Router architecture** (a routing step classifies/decomposes and dispatches via `Command` or parallel fan-out via `Send`, then synthesizes). ([LangChain Docs][4])
* Hybrid patterns (router → subagent supervisor inside a vertical, etc.)

---

### 5) RAG over “Latest Docs”

#### 5.1 Sources to index (minimum)

* LangGraph Graph API (state, nodes, edges, `Command`, `Send`) ([LangChain Docs][2])
* Multi-agent patterns: Router, Subagents ([LangChain Docs][4])
* Agent runtime guidance (`create_agent`) and migration notes (avoid deprecated patterns) ([LangChain Docs][5])
* Checkpointing/persistence choices (Memory/SQLite/Postgres) ([LangChain Docs][6])
* Notebook generation APIs (nbformat) ([nbformat][7])
* Notebook export (nbconvert pdf/webpdf) ([Nbconvert][8])
* Manuscript generation libraries (python-docx + reportlab, if required) ([python-docx][9])

#### 5.2 Retrieval behavior

* Build an indexed “Docs KB” (chunk + embed + vector store).
* Each outer-graph stage can query the KB with targeted queries (“how to do parallel fan-out with Send”, “recommended agent factory create_agent”, etc.).
* Store retrieved snippets + source URLs in state so the notebook can include a **“Why this design”** section with citations.

---

### 6) Outer State Schema (Generator State)

Use a typed state (TypedDict or pydantic) with reducers where aggregation is needed.

**Core keys:**

* `user_prompt: str`
* `constraints: dict` (parsed requirements)
* `selected_patterns: dict` (router/subagents/critique loops/etc.)
* `docs_context: list[Snippet]` (RAG outputs w/ citations)
* `notebook_plan: NotebookPlan` (sections/cells outline)
* `generated_cells: list[CellSpec]`
* `qa_reports: list[QAReport]`
* `artifacts_manifest: dict` (paths to produced files)
* `repair_attempts: int`

---

### 7) Agent Roles inside the Outer Graph

Implement as subagents (supervisor + subagents-as-tools) because it keeps contexts clean and makes the generator easier to extend. ([LangChain Docs][3])

**Suggested subagents:**

* **Requirements Analyst** → extracts constraints into structured JSON
* **Docs Researcher (RAG)** → retrieves authoritative snippets for patterns/APIs
* **Architecture Selector** → chooses router vs subagents vs hybrid and justifies
* **Graph Designer** → defines inner workflow state/nodes/edges/loops
* **Toolchain Engineer** → picks tools (files, Drive, exports, eval)
* **Notebook Composer** → emits nbformat cell objects + metadata
* **QA & Repair Agent** → runs checks; patches notebook until it passes

---

### 8) Inner Workflow Pattern Library

The generator should maintain a “pattern palette” it can snap to, driven by docs:

**Core patterns to support (v1):**

* **Router multi-source** with `Command` (single) and `Send` (parallel) ([LangChain Docs][4])
* **Subagents supervisor** orchestration ([LangChain Docs][3])
* **Critique → Revise loops** (conditional edges until acceptance)
* **Map-reduce content expansion** (outline → chapters in parallel → merge)
* **Human-in-the-loop interrupts** (approval gates for expensive steps)
* **Persistence/checkpointing** (MemorySaver for dev; SQLite/Postgres for prod) ([LangChain Docs][6])

**Implementation note:** prefer the recommended agent factory (`create_agent`) and keep a migration-aware compatibility layer so notebooks don’t ship deprecated scaffolding. ([LangChain Docs][1])

---

### 9) Notebook Generation Requirements

Use `nbformat` to build notebooks programmatically:

* `new_notebook`, `new_markdown_cell`, `new_code_cell`, then `nbformat.write()` ([nbformat][7])
* Enforce a consistent structure:

  1. Title + “What this notebook generates”
  2. Install & environment cells
  3. Configuration cell (paths/models/budgets)
  4. Core implementation (state/tools/graph)
  5. Run/demo cells
  6. Export + packaging cells
  7. Troubleshooting section

**Export support:**

* `nbconvert --to pdf` (LaTeX) or `--to webpdf` (Chromium via Playwright) depending on fidelity needs ([Nbconvert][8])

---

### 10) Manuscript / “Print-ready” Output Module (when requested)

When the user wants *real* formatting control:

* **DOCX pipeline** via python-docx styles (heading/body styles, fonts, spacing) ([python-docx][9])
* **PDF pipeline** via ReportLab for precise PDF/font control (embed/register fonts, consistent typography) ([ReportLab Docs][10])

The inner workflow should generate:

* `manuscript.docx`
* `manuscript.pdf`
* `marketing/` (blurbs, logline, synopsis, character sheets, ad copy)
* `metadata.json` (title, word count, version hash, run settings)

---

### 11) Quality Gates (must-pass for “production-ready”)

**Static gates:**

* notebook JSON validity
* no placeholder TODOs in required sections
* deterministic config cell + reproducible installs

**Runtime gates (smoke test):**

* graph compiles
* minimal run executes through at least one full loop
* outputs are created in expected folders
* checkpointing configured (at least MemorySaver in dev; optional SQLite/Postgres in prod) ([LangChain Docs][6])

If a gate fails, outer graph enters a **Repair Loop** (bounded attempts).

---

### 12) Safety / Guardrails

Because this system generates executable notebooks:

* tool allowlist + network access policy
* dependency allowlist / version pinning
* budget caps (iterations, tokens, parallel fan-out size)
* file write sandboxing under a single workspace folder
* explicit opt-in for any destructive actions

---

If you want, I can also write a **“prompt-to-implementer” version** of this spec (with exact state typings, tool signatures, and a concrete outer-graph node list + conditional routing), so you can drop it straight into your build model.

[1]: https://docs.langchain.com/oss/python/migrate/langgraph-v1?utm_source=chatgpt.com "LangGraph v1 migration guide - Docs by LangChain"
[2]: https://docs.langchain.com/oss/python/langgraph/use-graph-api?utm_source=chatgpt.com "Use the graph API - Docs by LangChain"
[3]: https://docs.langchain.com/oss/python/langchain/multi-agent/subagents?utm_source=chatgpt.com "Subagents - Docs by LangChain"
[4]: https://docs.langchain.com/oss/javascript/langchain/multi-agent/router?utm_source=chatgpt.com "Router - Docs by LangChain"
[5]: https://docs.langchain.com/oss/python/langchain/agents?utm_source=chatgpt.com "Agents - Docs by LangChain"
[6]: https://docs.langchain.com/oss/javascript/langgraph/persistence?utm_source=chatgpt.com "Persistence - Docs by LangChain"
[7]: https://nbformat.readthedocs.io/en/5.6.0/api.html?utm_source=chatgpt.com "Python API for working with notebook files — nbformat 5.6 documentation"
[8]: https://nbconvert.readthedocs.io/en/v7.14.0/usage.html?utm_source=chatgpt.com "Using as a command line tool — nbconvert 7.14.0 documentation"
[9]: https://python-docx.readthedocs.io/en/latest/dev/analysis/features/styles/paragraph-style.html?utm_source=chatgpt.com "Paragraph Style — python-docx 1.2.0 documentation"
[10]: https://docs.reportlab.com/reportlab/userguide/ch3_fonts/?utm_source=chatgpt.com "Chapter 3: Fonts - ReportLab Docs"
