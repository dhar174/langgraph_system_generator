# Repository Visualizations

This folder holds maintainer-focused diagrams for the generator pipeline.

## Current Diagrams

- [Generator stage and state map](generator-stage-state-map.md)
- [Repo architecture visualizer bundle](repo-architecture-visualizer/2026-04-30/repo-knowledge.md)

## Regeneration Notes

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

The Markdown files here are the source of truth, so no separate generator
script is required to keep the documentation current.

The repo architecture visualizer bundle is a generated, editable diagram
snapshot. Refresh it with the local `repo-architecture-visualizer` skill when
package, module, or environment-variable relationships change.
