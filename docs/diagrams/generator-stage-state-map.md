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

    start([Prompt + optional files/config]):::note --> intake["intake_node<br/>writes: constraints"]:::stage
    intake --> rag["rag_retrieval_node<br/>writes: docs_context"]:::stage
    rag --> arch["architecture_selection_node<br/>writes: selected_patterns, architecture_type, architecture_justification"]:::stage
    arch --> design["graph_design_node<br/>writes: workflow_design, notebook_plan"]:::stage
    design --> tools["tooling_plan_node<br/>writes: tools_plan"]:::stage
    tools --> assemble["notebook_assembly_node<br/>writes: generated_cells"]:::stage
    assemble --> staticqa["static_qa_node<br/>writes: qa_reports"]:::stage
    staticqa --> runtimeqa["runtime_qa_node<br/>writes: qa_reports"]:::stage
    runtimeqa --> qa_decision{"should_repair()"}:::decision

    qa_decision -->|no failures| package["package_outputs_node<br/>writes: artifacts_manifest, generation_complete, error_message"]:::stage
    package -. manifest consumed by .-> cli_api["CLI / API export layer"]:::support
    cli_api -. writes files via .-> exporter["NotebookExporter"]:::support
    package --> end([Graph end / workflow exit]):::note

    qa_decision -->|failures and repair budget left| repair["repair_node<br/>writes: generated_cells, qa_reports, repair_attempts"]:::stage
    repair --> retry_decision{"should_retry_after_repair()"}:::decision
    retry_decision -->|retry QA| staticqa
    retry_decision -->|success| package
    retry_decision -->|fail| end
    qa_decision -->|failures and budget exhausted| end
```

## State Semantics

- Merge/accumulate: `constraints`, `docs_context`, `qa_reports`
- Replace: `generated_cells`
- Increment: `repair_attempts`
- Finalize: `artifacts_manifest`, `generation_complete`, `error_message`
- Inputs only: `user_prompt`, `uploaded_files`, `generation_config`

## State Write Ledger

| State field(s) | Written by | Semantics |
| --- | --- | --- |
| `constraints` | `intake_node` | Append/merge list of extracted requirements. |
| `docs_context` | `rag_retrieval_node` | Append/merge list of retrieved snippets; falls back to `[]` when RAG fails. |
| `selected_patterns`, `architecture_type`, `architecture_justification` | `architecture_selection_node` | Single-writer architecture decision and rationale. |
| `workflow_design`, `notebook_plan` | `graph_design_node` | Planning outputs that shape the generated notebook. |
| `tools_plan` | `tooling_plan_node` | Tool inventory for the workflow. |
| `generated_cells` | `notebook_assembly_node`, `repair_node` | Authoritative notebook cell list; repair replaces it rather than appending to it. |
| `qa_reports` | `static_qa_node`, `runtime_qa_node`, `repair_node` | Accumulated validation history across QA and repair. |
| `repair_attempts` | `repair_node` | Incremented counter used to bound the repair loop. |
| `artifacts_manifest`, `generation_complete`, `error_message` | `package_outputs_node` | Final packaging state for CLI/API consumers. |

## Adjacent Components

| Component | Why it matters |
| --- | --- |
| `rag.retriever.DocsRetriever` / `rag.embeddings.VectorStoreManager` | Power the docs retrieval path used by `rag_retrieval_node` and the architecture selector. |
| `generator.agents.NotebookComposer` | Produces the `CellSpec` list that becomes `generated_cells`. |
| `notebook.composer.NotebookComposer` | Builds a validated `nbformat` notebook for static QA and repair rehydration. |
| `notebook.runtime.run_notebook_smoke_test` | Supplies the runtime QA smoke test. |
| `qa.validators.NotebookValidator` | Runs the static notebook checks. |
| `qa.repair.NotebookRepairAgent` | Applies bounded repairs when QA fails. |
| `generator.agents.QARepairAgent` | Companion API for notebook validation/repair; currently separate from the `create_generator_graph()` repair path. |
| `notebook.exporters.NotebookExporter` | Writes the final `.ipynb`, `.html`, `.md`, `.docx`, `.pdf`, and `.zip` files after the manifest handoff in the CLI/API layer. |

## Source Files To Recheck

- `src/langgraph_system_generator/generator/nodes.py`
- `src/langgraph_system_generator/generator/state.py`
- `src/langgraph_system_generator/rag/retriever.py`
- `src/langgraph_system_generator/rag/embeddings.py`
- `src/langgraph_system_generator/notebook/composer.py`
- `src/langgraph_system_generator/notebook/exporters.py`
- `src/langgraph_system_generator/notebook/runtime.py`
- `src/langgraph_system_generator/qa/validators.py`
- `src/langgraph_system_generator/qa/repair.py`
- `src/langgraph_system_generator/generator/agents/notebook_composer.py`
- `src/langgraph_system_generator/generator/agents/qa_repair_agent.py`

When one of those files changes, update the stage labels, state write ledger,
and component notes together so the diagram stays aligned with the code.
