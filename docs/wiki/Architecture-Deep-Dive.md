# Architecture Deep Dive

This guide explains the internal architecture of LangGraph System Generator and how the generation pipeline transforms prompts into complete multi-agent systems.

See also:

- **LangChain docs**: <https://docs.langchain.com>
- **LangChain Python API reference**: <https://reference.langchain.com/python>
- **LangGraph overview**: <https://docs.langchain.com/oss/python/langgraph/overview>

## Overview

LangGraph System Generator follows a **linear pipeline architecture** with conditional repair loops. Each stage processes and enriches the state, ultimately producing complete, runnable Jupyter notebooks.

For maintainer-focused visuals of stage writes, adjacent QA/RAG/notebook
components, and generated package/module/env relationships, see
[Repository visualizations](../diagrams/README.md).

## Generation Pipeline

```mermaid
graph TB
    Start([Prompt]) --> Intake
    Intake[Requirements] --> RAG
    RAG[RAG] --> ArchSelect
    ArchSelect[Architecture Select] --> GraphDesign
    GraphDesign[Plan Workflow] --> ToolPlan
    ToolPlan[Plan Tools] --> Compose
    Compose[Generate Notebook] --> StaticQA
    StaticQA[Static QA] --> RuntimeQA
    RuntimeQA[Runtime QA] --> Decision{QA Passed?}
    Decision -->|Yes| Package[Package Outputs]
    Decision -->|No, Attempts < Max| Repair[Repair Notebook]
    Decision -->|No, Max Attempts| Fail[Best Effort Package]
    Repair --> RuntimeQA
    Package --> End([Exported Artifacts])
    Fail --> End
```

### Pipeline Stages

#### 1. Requirements Analysis (Intake)
**Input**: User prompt  
**Output**: Structured constraints plus advisory requirements feedback

The Requirements Analyst extracts structured constraints from the natural language prompt:

```python
{
  "user_prompt": "Create a customer support chatbot with routing",
  "constraints": [
    {"type": "goal", "value": "Build a customer support chatbot", "priority": 5},
    {"type": "structure", "value": "Use routing between support flows", "priority": 3},
    {"type": "environment", "value": "Run in a notebook-friendly environment", "priority": 2}
  ],
  "requirements_feedback": {
    "fallback_used": false,
    "missing_inputs": [],
    "conflicts": [],
    "suggestions": []
  }
}
```

**Agent**: `RequirementsAnalyst`  
**LLM-Powered**: Yes (live mode) / Heuristics (stub mode)

#### 2. RAG Retrieval
**Input**: Constraints  
**Output**: Relevant documentation snippets

Retrieves relevant LangGraph/LangChain documentation based on the requirements:

```python
{
  "docs_context": [
    {
      "source": "langgraph/concepts/state",
      "heading": "State Management",
      "content": "LangGraph uses TypedDict for state...",
      "relevance_score": 0.92
    },
    {
      "source": "langgraph/patterns/router",
      "heading": "Router Pattern",
      "content": "Dynamic routing to specialized nodes...",
      "relevance_score": 0.89
    }
  ]
}
```

**Components**: `DocsRetriever`, `VectorStoreManager`  
**Vector Store**: FAISS; local fake embeddings are used for offline index
builds, and OpenAI embeddings are available when requested.

#### 3. Architecture Selection
**Input**: Constraints + Documentation context  
**Output**: Selected architecture, justification, and advisory architecture feedback

Selects the most appropriate multi-agent pattern:

```python
{
  "architecture_type": "router",
  "architecture_justification": "Router pattern selected for customer support routing based on classification requirements",
  "selected_patterns": {
    "primary": "router",
    "secondary": []
  },
  "architecture_feedback": {
    "confidence": 0.78,
    "fallback_used": false,
    "validation_errors": [],
    "tradeoffs": [
      "Router keeps coordination simple but offers less worker specialization than subagents."
    ]
  }
}
```

**Available Architectures**:
- `router`: Dynamic routing pattern
- `subagents`: Supervisor-subagent coordination
- `hybrid`: Combination of multiple patterns
- `autoagent`: Planner/executor/critic loop for autonomous multi-step execution
- `deepagents`: Experimental opt-in Deep Agents SDK harness with lazy optional
  `create_deep_agent(...)` usage and deterministic fallback cells

**Agent**: `ArchitectureSelector`  
**LLM-Powered**: Yes (live mode) / Heuristics (stub mode)

#### 4. Workflow Design
**Input**: Architecture + Constraints + Docs  
**Output**: Detailed workflow specification plus advisory graph-design feedback and exports

Designs the specific graph structure, nodes, and edges:

```python
{
  "workflow_design": {
    "architecture_type": "router",
    "state_schema": {
      "messages": "Conversation state",
      "route": "Selected route"
    },
    "nodes": [
      {"name": "router", "purpose": "Route to appropriate handler"},
      {"name": "technical_support", "purpose": "Handle technical queries"},
      {"name": "billing_support", "purpose": "Handle billing queries"},
      {"name": "general_support", "purpose": "Handle general queries"}
    ],
    "edges": [
      {"from": "technical_support", "to": "finish"},
      {"from": "billing_support", "to": "finish"},
      {"from": "general_support", "to": "finish"}
    ],
    "conditional_edges": [
      {
        "from": "router",
        "condition": "route == 'technical' | 'billing' | 'general'",
        "branches": {
          "technical": "technical_support",
          "billing": "billing_support",
          "general": "general_support"
        }
      }
    ],
    "entry_point": "router",
    "checkpointing": false,
    "graph_exports": {
      "mermaid": "flowchart TD ...",
      "schema": {
        "entry_point": "router",
        "terminal_nodes": ["finish"],
        "validation_summary": {"errors": [], "warnings": []}
      }
    }
  },
  "graph_design_feedback": {
    "fallback_used": false,
    "validation_errors": [],
    "warnings": [],
    "composition_strategy": "router_direct"
  }
}
```

**Agent**: `GraphDesigner`  
**LLM-Powered**: Yes (live mode) / Deterministic registry-backed fallback (stub mode and recovery)

#### 5. Tool Planning
**Input**: Workflow design + Constraints  
**Output**: Tool specifications + advisory planning feedback

Plans any tools/functions needed by the agents:

```python
{
  "tools_plan": [
    {
      "tool_id": "web_search",
      "name": "Web Docs Search",
      "purpose": "Search documentation relevant to the workflow",
      "configuration": {"backend": "duckduckgo"},
      "status": "ready"
    }
  ],
  "tool_planning_feedback": {
    "fallback_used": false,
    "environment_notes": [],
    "dependency_conflicts": []
  }
}
```

**Agent**: `ToolchainEngineer`  
**LLM-Powered**: Yes (live mode) / Registry-backed deterministic fallbacks and validation (stub mode and recovery)

#### 6. Notebook Composition
**Input**: All previous context  
**Output**: Complete notebook cells

Generates the actual notebook structure:

```python
{
  "notebook_plan": {
    "title": "Customer Support Router System",
    "sections": [
      "Setup & Configuration",
      "State Definition",
      "Node Implementation",
      "Graph Construction",
      "Execution & Testing"
    ],
    "cell_count_estimate": 12,
    "architecture_type": "router",
    "patterns_used": ["router"]
  },
  "generated_cells": [
    {
      "cell_type": "markdown",
      "section": "Setup & Configuration",
      "content": "# Customer Support Router System\n\n..."
    },
    {
      "cell_type": "code",
      "section": "Setup & Configuration",
      "content": "!pip install langgraph langchain langchain-openai\nimport os\n..."
    },
    # ... more cells
  ]
}
```

**Agent**: `NotebookComposer`  
**LLM-Powered**: Yes (live mode) / Template-based (stub mode)

#### 7. Static QA
**Input**: Generated cells  
**Output**: QA reports

Validates notebook structure without execution:

```python
{
  "qa_reports": [
    {
      "check_name": "json_structure",
      "passed": true,
      "message": "Notebook structure is valid"
    },
    {
      "check_name": "required_sections",
      "passed": true,
      "message": "All required sections present"
    },
    {
      "check_name": "no_placeholders",
      "passed": true,
      "message": "No placeholder text found"
    }
  ]
}
```

**Checks**:
- JSON structure validity
- Required sections presence
- No placeholder text
- Required imports present

**Component**: `NotebookValidator`

#### 8. Runtime QA
**Input**: Notebook file  
**Output**: Additional QA reports

Validates the generated notebook by executing the built notebook artifact. In
`live` mode, missing notebook runtime support is a real gate failure; in `stub`
mode it is recorded as non-blocking runtime evidence.

```python
{
  "qa_reports": [
    # ... previous static QA reports ...
    {
      "check_name": "Runtime Check",
      "passed": true,
      "stage": "runtime",
      "message": "Generated notebook executed successfully using the 'python3' kernel.",
      "evidence": {
        "preflight": {"kernel_name": "python3"},
        "execution": {"executed_cells": 4}
      }
    }
  ]
}
```

**Component**: notebook runtime helpers (`inspect_notebook_runtime_support`,
`execute_notebook`)

#### 9. Repair Loop
**Input**: Notebook + Failed QA reports  
**Output**: Repaired notebook

If QA fails, the shared QA/repair engine applies registered deterministic repair
routines in memory, revalidates the candidate notebook, and persists the repair
only when validation is non-regressive:

```python
{
  "repair_attempts": 1,
  "qa_reports": [
    # ... updated reports after repair ...
  ],
  "qa_history": [
    # ... prior static/runtime reports ...,
    {"check_name": "Repair Attempt", "stage": "repair", "passed": false}
  ],
  "qa_repair_feedback": {
    "repair_attempts": 1,
    "rollback_used": true,
    "unrepaired_failures": ["Python Syntax: invalid syntax"],
    "next_steps": ["Inspect the QA and Repair Summary cell before retrying."]
  }
}
```

**Repair Strategy**:
1. Identify specific failures
2. Select matching routines from `QARepairRegistry`
3. Apply fixes to an in-memory notebook candidate
4. Re-run QA validation and accept only non-regressive candidates
5. Record rollback/no-op outcomes in `qa_history` and `qa_repair_feedback`

**Component**: `NotebookRepairAgent`  
**LLM-Powered**: No; repair is deterministic and registry-backed in both stub
and live-compatible paths

#### 10. Package Outputs
**Input**: Final notebook  
**Output**: Multiple formats + manifest

Exports the notebook to various formats:

```python
{
  "artifacts_manifest": {
    "notebook_path": "./output/system/notebook.ipynb",
    "html_path": "./output/system/notebook.html",
    "docx_path": "./output/system/notebook.docx",
    "pdf_path": "./output/system/notebook.pdf",  # optional
    "zip_path": "./output/system/notebook_bundle.zip",
    "manifest_path": "./output/system/manifest.json",
    "plan_path": "./output/system/notebook_plan.json",
    "cells_path": "./output/system/generated_cells.json"
  },
  "generation_complete": true
}
```

**Component**: `NotebookExporter`

## State Management

The entire pipeline operates on a single `GeneratorState` object that flows through each node:

The [Generator stage state map diagram](../diagrams/generator-stage-state-map.md)
keeps that state contract aligned with the code paths that write each field.

```python
class GeneratorState(TypedDict):
    # Input
    user_prompt: str
    uploaded_files: Optional[List[str]]
    
    # Extracted requirements
    constraints: Annotated[List[Constraint], operator.add]
    requirements_feedback: RequirementsFeedback
    architecture_feedback: ArchitectureFeedback
    graph_design_feedback: GraphDesignFeedback
    graph_exports: GraphExportBundle
    selected_patterns: Dict[str, Any]
    
    # RAG Retrieval
    docs_context: Annotated[List[DocSnippet], operator.add]
    
    # Planning
    notebook_plan: Optional[NotebookPlan]
    architecture_justification: str
    architecture_type: Optional[str]
    generation_config: Optional[GenerationConfig]
    generation_mode: Literal["stub", "live"]

    # Workflow design
    workflow_design: Optional[Dict[str, Any]]
    tools_plan: Optional[List[Dict[str, Any]]]
    tool_planning_feedback: ToolPlanningFeedback
    notebook_composition_feedback: NotebookCompositionFeedback
    notebook_dependency_plan: NotebookDependencyPlan
    
    # Generation
    # No reducer: last-write-wins across repair iterations
    generated_cells: List[CellSpec]
    
    # QA & Repair
    qa_reports: List[QAReport]
    qa_history: List[QAReport]
    repair_attempts: int
    qa_repair_feedback: QARepairFeedback
    
    # Output
    artifacts_manifest: Dict[str, str]
    generation_complete: bool
    error_message: Optional[str]
```

**Key Features**:
- **Annotated Lists**: Fields like `constraints` and `docs_context` use `operator.add` to append values across nodes
- **Advisory Intake Feedback**: `requirements_feedback` captures fallback, conflict, and missing-input guidance without replacing `constraints` as the downstream planning contract
- **Advisory Graph Feedback**: `graph_design_feedback` captures validation and fallback details while `graph_exports` stores Mermaid/schema bundles for manifests and notebook overview cells
- **Advisory Tool Feedback**: `tool_planning_feedback` records fallback, validation, environment, and dependency warnings while `tools_plan` remains the downstream list
- **Notebook Composition Feedback**: `notebook_composition_feedback` and `notebook_dependency_plan` explain fallback and dependency decisions without replacing `generated_cells`
- **QA History**: `qa_reports` is the current snapshot; `qa_history` preserves attempt-by-attempt evidence across static QA, runtime QA, and repair
- **Last-write-wins cells**: `generated_cells` intentionally has no reducer, so each repair pass replaces prior cells
- **Immutability**: State updates create new state versions (LangGraph managed)
- **Type Safety**: TypedDict provides IDE autocomplete and validation

## Component Architecture

### Core Agents

Each pipeline stage has a dedicated agent:

| Agent | Responsibility | LLM? |
|-------|---------------|------|
| `RequirementsAnalyst` | Extract constraints from prompts | Live mode |
| `ArchitectureSelector` | Choose optimal pattern | Live mode |
| `GraphDesigner` | Design workflow structure | Live mode |
| `ToolchainEngineer` | Plan required tools | Live mode |
| `NotebookComposer` | Generate notebook cells | Live mode |
| `QARepairAgent` | Orchestrate deterministic QA repairs | No |

### Support Components

| Component | Purpose |
|-----------|---------|
| `DocsRetriever` | Semantic search over cached docs |
| `VectorStoreManager` | FAISS index management |
| `DocumentCache` | Cached documentation storage |
| `NotebookValidator` | Static & runtime validation |
| `QARepairRegistry` | Internal validator and repair routine registry |
| `NotebookExporter` | Multi-format export |
| `PatternLibrary` | Reusable pattern templates |

## Stub vs Live Mode

### Stub Mode
**Purpose**: Fast generation without API calls

**Characteristics**:
- ✅ No API key required
- ✅ Instant generation (< 1 second)
- ✅ Deterministic output
- ❌ Limited customization
- ❌ Template-based patterns only
- ❌ No context-aware generation

**Use Cases**:
- Quick prototyping
- Testing pipeline
- Offline development
- CI/CD integration

### Live Mode
**Purpose**: Full LLM-powered generation

**Characteristics**:
- ✅ Context-aware generation
- ✅ Highly customized output
- ✅ Intelligent pattern selection
- ✅ Detailed documentation
- ❌ Requires API key
- ❌ Slower (10-30 seconds)
- ❌ Non-deterministic

**Use Cases**:
- Production generation
- Complex requirements
- Custom architectures
- High-quality output

## RAG System

### Documentation Cache

Precached documentation includes:

- **LangGraph Core**: State, graphs, nodes, edges
- **LangGraph Patterns**: Router, subagents, supervisor
- **LangChain Core**: Chains, runnables, prompts
- **LangChain Agents**: Tools, agent executors
- **LangChain RAG**: Retrievers, vector stores

**Statistics**:
- 19+ pages
- ~300KB text
- All redirects filtered
- Minimal pages excluded

### Vector Store

**Implementation**: FAISS. `lnf build-index` uses local fake embeddings by
default for offline/testing flows; `lnf build-index --use-openai` uses OpenAI
embeddings when credentials are configured.

**Index Structure**:
```
data/vector_store/
  ├── index.faiss       # FAISS index file
  └── index.pkl         # Document metadata
```

**Retrieval Process**:
1. Query embedding via the configured embedding implementation
2. Similarity search in FAISS (k=5 default)
3. Return top documents with relevance scores
4. Filter by minimum relevance threshold

## Pattern Library Integration

The Pattern Library provides code generation templates:

### Router Pattern
```python
# Generated code structure
1. State schema with routing field
2. Router node (LLM-based classification)
3. Route handler nodes (specialized processing)
4. Conditional edges (routing logic)
5. Graph compilation
```

### Subagents Pattern
```python
# Generated code structure
1. State schema with agent tracking
2. Supervisor node (delegation decisions)
3. Subagent nodes (specialized work)
4. Looping edges (supervisor ↔ agents)
5. Termination condition (FINISH signal)
```

### Critique-Revise Loop
```python
# Generated code structure
1. State schema with revision tracking
2. Generation node (initial output)
3. Critique node (quality assessment)
4. Revise node (improvement)
5. Conditional edges (quality threshold)
```

Generator-backed patterns are covered by focused unit tests and runnable
examples. The architecture selector and graph designer can currently target
`router`, `subagents`, `hybrid`, `autoagent`, and explicit experimental
`deepagents`; the pattern library also keeps the critique-revise loop available
for direct use and examples. Deep Agents support keeps the SDK optional at core
import time and adds notebook-facing optional install guidance only for Deep
Agents outputs, so offline fallback notebooks do not auto-install `deepagents`.

## Quality Assurance System

### Validation Checks

| Check | Type | Description |
|-------|------|-------------|
| `json_structure` | Static | Valid notebook JSON |
| `required_sections` | Static | All sections present |
| `placeholder_content` | Static | No TODO/placeholder text |
| `required_import_symbols` | Static | Required imports included |
| `python_syntax` | Static | Code syntax validation |
| `graph_structure` | Static | Parsed graph construction and terminal path validation |

### Repair Strategies

When QA fails, the repair agent:

1. **Analyzes failures**: Categorizes error types
2. **Selects routines**: Uses `QARepairRegistry` to find matching deterministic fixes
3. **Applies candidates**: Updates in-memory notebook cells first
4. **Validates**: Re-runs QA checks before accepting the candidate
5. **Rolls back safely**: Keeps the original cells if the candidate regresses

### Best-Effort Fallback

If repair fails after max attempts:
- Packages best available version
- Includes QA reports in manifest
- Logs warnings for manual review

## Export System

### Format Support

| Format | Extension | Use Case | Dependencies |
|--------|-----------|----------|--------------|
| Jupyter | `.ipynb` | Interactive execution | nbformat |
| HTML | `.html` | Viewing/sharing | nbconvert |
| DOCX | `.docx` | Editing/documentation | python-docx |
| PDF | `.pdf` | Print/archival | reportlab |
| ZIP | `.zip` | Bundle distribution | stdlib |

### Manifest Structure

Every generation produces a `manifest.json`:

```json
{
  "prompt": "Create a customer support chatbot with routing",
  "mode": "stub",
  "architecture_type": "router",
  "graph_design_feedback": {
    "fallback_used": false,
    "validation_errors": [],
    "warnings": []
  },
  "graph_exports": {
    "mermaid": "flowchart TD ...",
    "schema": {
      "entry_point": "router",
      "terminal_nodes": ["finish"],
      "validation_summary": {"errors": [], "warnings": []}
    }
  },
  "warnings": [],
  "export_results": {
    "ipynb": {"status": "completed", "path": "./notebook.ipynb"}
  },
  "phase_summary": [{"phase": "compose", "status": "completed"}]
}
```

## Configuration

Settings are managed via environment variables and Pydantic:

```python
class Settings(BaseSettings):
    # API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    langsmith_api_key: Optional[str] = None
    
    # Vector Store
    vector_store_type: str = "faiss"
    vector_store_path: str = "./data/vector_store"
    
    # Generation
    default_model: str = "gpt-5-mini"
    max_repair_attempts: int = 3
    default_budget_tokens: int = 100000
    graph_designer_plugin_modules: list[str] = []
    notebook_composer_plugin_modules: list[str] = []
    toolchain_engineer_plugin_modules: list[str] = []
    qa_repair_plugin_modules: list[str] = []
    
    # LangSmith
    langsmith_project: Optional[str] = None
```

Access via:
```python
from langgraph_system_generator.utils.config import settings

print(settings.default_model)  # "gpt-5-mini"
```

## Extension Points

### Adding New Patterns

1. Create pattern module in `src/langgraph_system_generator/patterns/`
2. Implement standard methods:
   - `generate_state_code()`
   - `generate_graph_code()`
   - `generate_complete_example()`
3. Add tests in `tests/unit/test_patterns.py`
4. Update documentation

### Custom Agents

Inject custom agents into the pipeline:

```python
from langgraph_system_generator.generator.graph import create_generator_graph

# Create graph
workflow = create_generator_graph()

# Add custom node
def custom_analysis_node(state):
    # Your custom logic
    return {"custom_field": "value"}

workflow.add_node("custom_analysis", custom_analysis_node)
workflow.add_edge("intake", "custom_analysis")
workflow.add_edge("custom_analysis", "rag_retrieval")

# Compile and run
app = workflow.compile()
```

### Internal QA/Repair Plugins

Register internal validation rules or repair routines without editing the core
QA modules by setting `QA_REPAIR_PLUGIN_MODULES` to one or more dotted module
paths. Each module should expose `register_qa_repair_plugins(registry)`:

```python
from langgraph_system_generator.qa.registry import RepairRoutineRegistration
from langgraph_system_generator.qa.validators import QAValidationRule


class CustomRule(QAValidationRule):
    rule_id = "custom_rule"
    check_name = "Custom Rule"
    category = "custom"

    def validate(self, context):
        return self.passed_report("Custom rule passed.")


def register_qa_repair_plugins(registry):
    registry.register_validator(CustomRule())
    registry.register_repair_routine(
        RepairRoutineRegistration(
            routine_id="custom_repair",
            handled_rule_ids=("custom_rule",),
            handler=lambda agent, notebook, report: [],
        )
    )
```

## Performance Characteristics

### Stub Mode
- **Generation time**: < 1 second
- **Memory usage**: ~50MB
- **API calls**: 0
- **Deterministic**: Yes

### Live Mode
- **Generation time**: 10-30 seconds
- **Memory usage**: ~200MB (includes LLM context)
- **API calls**: 5-10 (depending on complexity)
- **Deterministic**: No (LLM variability)

### Scalability
- **Concurrent generations**: Limited by API rate limits
- **Vector store**: Scales to 100K+ documents
- **Pattern library**: O(1) generation time
- **Export**: Linear with notebook size

## Troubleshooting

### Common Issues

**Issue**: Generation fails with timeout  
**Solution**: Increase timeout in settings or use stub mode

**Issue**: Vector store not found  
**Solution**: Run `lnf build-index` or use stub mode

**Issue**: QA validation fails  
**Solution**: Check QA reports in output directory, repair attempts logged

**Issue**: Export format not generated  
**Solution**: Check dependencies installed: `pip install -e ".[full]"`

---

**Next**: [Pattern Library Guide →](Pattern-Library-Guide.md) | [CLI & API Reference →](CLI-and-API-Reference.md)
