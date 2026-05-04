# Repository Visualizations

This folder holds maintainer-focused visual documentation for the generator
pipeline and repository-level code relationships.

## Current Visualizations

- [Generator stage and state map](generator-stage-state-map.md): a
  hand-maintained Mermaid map of generator stages, shared state writes, and
  adjacent QA/RAG/notebook components.
- [Repo architecture visualizer bundle](repo-architecture-visualizer/2026-04-30/repo-knowledge.md):
  a docs-owned generated snapshot with editable Mermaid, DOT, JSON, and
  Figma-layout JSON sources for package, module, and environment-variable
  relationships.

## Regeneration Notes

### Generator stage/state map

When the generator flow changes, refresh the diagram by re-reading the
evidence files below and updating the Markdown source in this folder:

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

The `generator-stage-state-map.md` Markdown file is the source of truth for the
stage/state map, so no separate generator script is required to keep that
diagram current.

### Repo architecture visualizer bundle

The `repo-architecture-visualizer/2026-04-30/` bundle is a generated, editable
diagram snapshot. Refresh it with the local `repo-architecture-visualizer` skill
when package, module, or environment-variable relationships change.

The bundle was emitted with:

```powershell
python <repo-architecture-visualizer-skill>/scripts/generate_repo_diagram.py
```

Replace `<repo-architecture-visualizer-skill>` with the installed skill
directory on your machine.

Keep refreshed outputs under `docs/diagrams/repo-architecture-visualizer/` so
they remain checked in with the rest of the documentation. If Graphviz `dot` is
available locally, SVG files may also be rendered from the DOT sources; Mermaid,
DOT, JSON, and Figma-layout JSON are the portable sources to keep in version
control.
