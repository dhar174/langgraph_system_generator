# langgraph_system_generator Codebase Knowledge

Generated: 2026-05-21

This docs-owned generated snapshot refreshes the repository architecture bundle
after the runtime reliability, generated-chat notebook contract, artifact
manifest truth, and canonical graph topology work that landed or was prepared
during the May 19-21 maintenance window.

Use `docs/diagrams/README.md` as the regeneration entry point when package,
module, or environment-variable relationships change.

## Evidence Sources

- `README.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/wiki/Architecture-Deep-Dive.md`
- `docs/diagrams/generator-stage-state-map.md`
- `memory-bank/activeContext.md`
- `memory-bank/systemPatterns.md`
- `memory-bank/techContext.md`
- `memory-bank/progress.md`
- `setup.py`
- `requirements.txt`
- `.github/workflows/python-app.yml`
- `src/langgraph_system_generator/generator/graph.py`
- `src/langgraph_system_generator/generator/nodes.py`
- `src/langgraph_system_generator/generator/state.py`
- `src/langgraph_system_generator/generator/agents/notebook_composer.py`
- `src/langgraph_system_generator/qa/validators.py`
- `src/langgraph_system_generator/api/server.py`
- `src/langgraph_system_generator/utils/config.py`
- `src/langgraph_system_generator/constants.py`

## Current Architecture Notes

- The product centers on a staged outer LangGraph workflow built by
  `create_generator_graph()` in `generator/graph.py`.
- `GeneratorState` is the shared integration contract. Accumulated constraints,
  docs context, and QA history are bounded so long-running repair and QA paths
  do not grow without limit.
- `GraphDesigner` preserves a canonical graph/spec alongside
  backward-compatible `workflow_design`. That schema carries node IDs, direct
  edges, conditional route labels, `Command` destinations, guarded cycles,
  terminal nodes, tool reachability, domain terms, and the compiled graph
  variable.
- `NotebookComposer` renders executable graph cells from the canonical schema
  when present and uses architecture pattern templates as fallback. Notebook
  pattern cells opt into `make_llm(...)`; standalone pattern snippets keep
  direct `ChatOpenAI(...)` initialization.
- `NotebookValidator` and the QA/repair stack validate notebooks in memory,
  compare generated graph code against embedded/exported graph contracts, and
  keep deterministic repairs non-regressive before persistence.
- The export layer writes truthful manifests: serialized notebook cell counts,
  raw generated cell-spec counts, standalone versus ZIP-only artifact members,
  and QA validation scope are represented separately.

## Generated Diagram Inventory

All generated diagrams in this folder were emitted from:

`<repo-architecture-visualizer-skill>\scripts\generate_repo_diagram.py`

| Diagram | Scope | Kind | Granularity | Nodes | Edges | Files |
| --- | --- | --- | --- | ---: | ---: | --- |
| `repo-package-map` | `src` | mixed imports/env | package | 24 | 26 | `.mmd`, `.dot`, `.json`, `.figma.json` |
| `generator-module-map` | `src/langgraph_system_generator/generator` | mixed imports/env | module | 8 | 7 | `.mmd`, `.dot`, `.json`, `.figma.json` |
| `env-usage-map` | `src` | env reads | file | 21 | 15 | `.mmd`, `.dot`, `.json`, `.figma.json` |

SVG rendering was not requested for this refresh. Mermaid, DOT, JSON, and
Figma-layout JSON sources are present and editable.

## Regeneration Commands

```powershell
python <repo-architecture-visualizer-skill>\scripts\generate_repo_diagram.py --repo . --scan-root src --kind mixed --granularity package --package-depth 2 --emit mermaid,dot,json,figma-json --name repo-package-map --output-dir docs\diagrams\repo-architecture-visualizer\2026-05-21
python <repo-architecture-visualizer-skill>\scripts\generate_repo_diagram.py --repo . --scan-root src\langgraph_system_generator\generator --kind mixed --granularity module --emit mermaid,dot,json,figma-json --name generator-module-map --output-dir docs\diagrams\repo-architecture-visualizer\2026-05-21
python <repo-architecture-visualizer-skill>\scripts\generate_repo_diagram.py --repo . --scan-root src --kind env --granularity file --emit mermaid,dot,json,figma-json --name env-usage-map --output-dir docs\diagrams\repo-architecture-visualizer\2026-05-21
```
