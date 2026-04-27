# Generator Stage and State Map

This maintainer-focused diagram traces the outer generator pipeline, the shared
`GeneratorState` writes, and the adjacent QA, RAG, notebook, and export
components that the workflow touches.

## Stage Flow

```mermaid
flowchart LR
    classDef stage fill:#1f2937,stroke:#334155,color:#f8fafc;
    classDef decision fill:#7c2d12,stroke:#fb923c,color:#fff7ed;
    classDef support fill:#0f172a,stroke:#64748b,color:#e2e8f0;
    classDef note fill:#fafafa,stroke:#cbd5e1,color:#0f172a;

    start([Prompt + optional config]):::note --> intake["intake_node<br/>writes: constraints, requirements_feedback"]:::stage
    intake --> rag["rag_retrieval_node<br/>writes: docs_context"]:::stage
    rag --> arch["architecture_selection_node<br/>writes: selected_patterns, architecture_type, architecture_justification, architecture_feedback"]:::stage
    arch --> design["graph_design_node<br/>writes: workflow_design, graph_design_feedback, graph_exports, notebook_plan"]:::stage
    design --> tools["tooling_plan_node<br/>writes: tools_plan, tool_planning_feedback"]:::stage
    tools --> assemble["notebook_assembly_node<br/>writes: generated_cells, notebook_composition_feedback, notebook_dependency_plan"]:::stage
    assemble --> staticqa["static_qa_node<br/>writes: qa_reports, qa_history, qa_repair_feedback"]:::stage
    staticqa --> runtimeqa["runtime_qa_node<br/>writes: qa_reports, qa_history, qa_repair_feedback"]:::stage
    runtimeqa --> qa_decision{"should_repair()"}:::decision

    qa_decision -->|no failures| package["package_outputs_node<br/>writes: artifacts_manifest, generation_complete, error_message"]:::stage
    package -. manifest consumed by .-> cli_api["CLI / API export layer"]:::support
    cli_api -. writes files via .-> exporter["NotebookExporter"]:::support
    package --> end([Graph end / workflow exit]):::note

    qa_decision -->|failures and repair budget left| repair["repair_node<br/>writes: generated_cells, qa_reports, qa_history, repair_attempts, qa_repair_feedback"]:::stage
    repair --> retry_decision{"should_retry_after_repair()"}:::decision
    retry_decision -->|retry QA| staticqa
    retry_decision -->|success| package
    retry_decision -->|fail| package
    qa_decision -->|failures and budget exhausted| package
```

## State Semantics

- Merge/accumulate: `constraints`, `docs_context`.
- Replace: `generated_cells`, `qa_reports`.
- Append history: `qa_history`.
- Advisory single-writer feedback: `requirements_feedback`,
  `architecture_feedback`, `graph_design_feedback`, `tool_planning_feedback`,
  `notebook_composition_feedback`, `notebook_dependency_plan`,
  `qa_repair_feedback`.
- Increment: `repair_attempts`.
- Finalize: `artifacts_manifest`, `generation_complete`, `error_message`.
- Inputs/config: `user_prompt`, `uploaded_files`, `generation_config`,
  `generation_mode`.

## State Write Ledger

| State field(s) | Written by | Semantics |
| --- | --- | --- |
| `constraints`, `requirements_feedback` | `intake_node` | Extracted requirements plus advisory intake feedback. |
| `docs_context` | `rag_retrieval_node` | Retrieved snippets; falls back to `[]` when RAG fails. |
| `selected_patterns`, `architecture_type`, `architecture_justification`, `architecture_feedback` | `architecture_selection_node` | Single-writer architecture decision, rationale, and selector feedback. |
| `workflow_design`, `graph_design_feedback`, `graph_exports`, `notebook_plan` | `graph_design_node` | Typed graph design unpacked into backward-compatible workflow payload plus Mermaid/schema exports. |
| `tools_plan`, `tool_planning_feedback` | `tooling_plan_node` | Registry-normalized tool inventory plus validation, environment, and dependency notes. |
| `generated_cells`, `notebook_composition_feedback`, `notebook_dependency_plan` | `notebook_assembly_node` | Authoritative cell list plus composer fallback/dependency metadata. |
| `qa_reports`, `qa_history`, `qa_repair_feedback` | `static_qa_node`, `runtime_qa_node` | Current QA snapshot, attempt history, and user/developer repair guidance. |
| `generated_cells`, `qa_reports`, `qa_history`, `repair_attempts`, `qa_repair_feedback` | `repair_node` | Deterministic repair result; repaired cells replace prior cells only when accepted. |
| `artifacts_manifest`, `generation_complete`, `error_message` | `package_outputs_node` | Final packaging state for CLI/API consumers. |

## Adjacent Components

| Component | Why it matters |
| --- | --- |
| `rag.retriever.DocsRetriever` / `rag.embeddings.VectorStoreManager` | Power docs retrieval for `rag_retrieval_node` and architecture selection. |
| `generator.architecture_registry` | Normalizes architecture registrations, aliases, doc queries, and weights. |
| `generator.graph_design_registry` | Owns graph design registrations, normalization, validation, and Mermaid/schema exports. |
| `generator.tool_registry` | Owns canonical tools, aliases, environment compatibility, package/env defaults, and plugin loading. |
| `generator.agents.NotebookComposer` | Produces the `CellSpec` list, dependency plan, and notebook composition feedback. |
| `notebook.composer.NotebookComposer` | Builds a validated `nbformat` notebook for static QA and file export. |
| `notebook.runtime.run_notebook_smoke_test` | Supplies the runtime QA smoke test. |
| `qa.validators.NotebookValidator` | Runs registry-backed static notebook checks. |
| `qa.registry.QARepairRegistry` | Registers validators and deterministic repair routines, including internal plugins. |
| `qa.repair.NotebookRepairAgent` | Applies bounded in-memory repairs and accepts only non-regressive candidates. |
| `generator.agents.QARepairAgent` | Runtime-facing facade over the shared QA/repair engine. |
| `notebook.exporters.NotebookExporter` | Writes `.ipynb`, `.html`, `.md`, `.docx`, optional `.pdf`, and `.zip` files after the manifest handoff. |

## Source Files To Recheck

- `src/langgraph_system_generator/generator/nodes.py`
- `src/langgraph_system_generator/generator/state.py`
- `src/langgraph_system_generator/generator/architecture_registry.py`
- `src/langgraph_system_generator/generator/graph_design_registry.py`
- `src/langgraph_system_generator/generator/tool_registry.py`
- `src/langgraph_system_generator/generator/agents/`
- `src/langgraph_system_generator/rag/retriever.py`
- `src/langgraph_system_generator/rag/embeddings.py`
- `src/langgraph_system_generator/notebook/composer.py`
- `src/langgraph_system_generator/notebook/exporters.py`
- `src/langgraph_system_generator/notebook/runtime.py`
- `src/langgraph_system_generator/qa/validators.py`
- `src/langgraph_system_generator/qa/registry.py`
- `src/langgraph_system_generator/qa/repair.py`

When one of those files changes, update the stage labels, state write ledger,
and component notes together so the diagram stays aligned with the code.
