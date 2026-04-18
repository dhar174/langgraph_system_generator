# Repository Visualizations

This folder holds maintainer-focused diagrams for the generator pipeline.

## Current Diagrams

- [Generator stage and state map](generator-stage-state-map.md)

## Regeneration Notes

When the generator flow changes, refresh the diagram by re-reading the
evidence files below and updating the Markdown source in this folder:

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

The Markdown files here are the source of truth, so no separate generator
script is required to keep the documentation current.
