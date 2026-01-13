# Phase 3: Outer Graph Architecture - Implementation Summary

This document describes the implementation of Phase 3 of the LangGraph Notebook Foundry.

## Overview

Phase 3 implements the outer generator graph that orchestrates the meta-agent notebook foundry and coordinates subagents for requirements analysis, architecture selection, planning, and QA.

## Components Implemented

### 1. State Schema (`src/generator/state.py`)

Defines the complete state schema with Pydantic models:

- **Constraint**: User constraint specification (type, value, priority)
- **DocSnippet**: Retrieved documentation snippet with relevance score
- **NotebookPlan**: Notebook structure plan with sections and architecture
- **CellSpec**: Individual notebook cell specification (markdown or code)
- **QAReport**: Quality assurance check results
- **GeneratorState**: Complete TypedDict for the workflow state

### 2. Subagent Roles (`src/generator/agents/`)

Six specialized agents handle different aspects of generation:

#### RequirementsAnalyst
- Extracts structured constraints from user prompts
- Categorizes constraints: goal, tone, length, structure, runtime, environment
- Uses LLM to parse natural language requirements into structured format

#### ArchitectureSelector
- Evaluates router vs subagents vs hybrid patterns
- Retrieves pattern-specific documentation
- Provides detailed justification for architecture choice
- Considers task complexity, state management, and execution patterns

#### GraphDesigner
- Designs the inner workflow structure
- Specifies state schema, nodes, edges, and conditional logic
- Defines entry points and checkpointing requirements
- Creates architecture-specific graph designs

#### ToolchainEngineer
- Identifies tools needed for the workflow
- Categorizes tools: search, file I/O, data processing, APIs, etc.
- Specifies tool configuration requirements

#### NotebookComposer
- Generates complete notebook cell specifications
- Creates: intro cells, installation cells, configuration, state definitions
- Implements tool cells, node cells, and graph construction cells
- Produces execution and output cells

#### QARepairAgent
- Validates generated notebooks
- Checks for placeholders, structure, and required imports
- Identifies issues and suggests repairs
- Attempts automatic fixes for common problems

### 3. Graph Nodes (`src/generator/nodes.py`)

Ten nodes implement the complete workflow pipeline:

1. **intake_node**: Requirements extraction
2. **rag_retrieval_node**: Documentation retrieval
3. **architecture_selection_node**: Pattern selection (router/subagents/hybrid)
4. **graph_design_node**: Workflow design and notebook planning
5. **tooling_plan_node**: Tool selection
6. **notebook_assembly_node**: Cell generation
7. **static_qa_node**: Static quality checks
8. **runtime_qa_node**: Runtime quality checks (placeholder)
9. **repair_node**: Automated repair with attempt tracking
10. **package_outputs_node**: Artifact manifest generation

### 4. Graph Assembly (`src/generator/graph.py`)

Complete workflow orchestration:

- Linear pipeline from intake through packaging
- Conditional repair loop with capped attempts (max 3 by default)
- Decision functions:
  - `should_repair()`: Determines if repair is needed based on QA results
  - `check_repair_success()`: Evaluates repair outcomes

## Workflow Pipeline

```
intake → rag_retrieval → architecture_selection → graph_design → 
tooling_plan → notebook_assembly → static_qa → runtime_qa →
[repair loop] → package_outputs
```

### Repair Loop Behavior

- After `runtime_qa`, system evaluates QA reports
- If failures exist and attempts < max: enter repair loop
- Repair node increments attempt counter
- After repair, returns to `static_qa` for re-validation
- If max attempts reached: exit to END or proceed with best effort

## Testing

### Unit Tests (`tests/unit/test_generator.py`)
- Graph compilation verification
- Pydantic model validation
- State structure tests

### Integration Tests (`tests/integration/test_generator_workflow.py`)
- Complete workflow structure validation
- State initialization tests
- Model creation tests

### Stub Run (`tests/stub_run.py`)
- Demonstrates complete pipeline without API keys
- Uses mocked LLM responses
- Produces NotebookPlan and CellSpecs
- Validates end-to-end flow

## Running Tests

```bash
# Run unit tests
pytest tests/unit/test_generator.py -v

# Run integration tests
pytest tests/integration/test_generator_workflow.py -v

# Run stub demonstration
python tests/stub_run.py
```

## Example Output

The stub run demonstrates:
- ✓ Extraction of 2+ constraints from user prompt
- ✓ Architecture selection (e.g., "router" pattern)
- ✓ NotebookPlan with title, sections, and cell estimates
- ✓ Generation of 100+ cells (markdown and code)
- ✓ QA reports showing validation results
- ✓ Complete artifacts manifest

## Quality Gates

All quality gates met:
- ✅ Generator graph compiles successfully
- ✅ Minimal stub run produces NotebookPlan
- ✅ Stub run produces CellSpecs (100+ cells)
- ✅ Architecture selection explicitly evaluates patterns
- ✅ Graph supports repair loops with capped attempts
- ✅ All unit tests pass
- ✅ Integration tests validate structure

## Architecture Selection

The system evaluates three patterns:

1. **Router**: Single classifier routing to specialists
   - Best for: Simple classification tasks
   - State: Shared message state with route selection
   - Execution: Sequential routing based on classification

2. **Subagents**: Supervisor coordinating workers
   - Best for: Complex tasks needing specialized contexts
   - State: Per-agent context with supervisor coordination
   - Execution: Dynamic delegation by supervisor

3. **Hybrid**: Combined router and subagents
   - Best for: Multi-stage workflows with both routing and specialization
   - State: Hierarchical with shared and agent-specific contexts
   - Execution: Mixed routing and delegation

## Hard Boundaries Respected

- ❌ No notebook exporters implemented (delegated to lnf-notebook)
- ❌ No nbformat writing (interfaces defined only)
- ❌ No CLI implementation (delegated to lnf-cli)
- ✅ Cell specifications ready for notebook export layer
- ✅ Clean interfaces for downstream components

## Next Steps

Phase 3 is complete. Remaining phases:
- Phase 4: Inner graph pattern library (router, subagents, critique loops)
- Phase 5: Notebook generation engine (actual nbformat writing)
- Phase 6: QA & testing infrastructure
- Phase 7: Integration & deployment (CLI, API)

## Dependencies

Core dependencies used:
- `langgraph`: Graph construction and execution
- `langchain`: LLM orchestration
- `langchain-openai`: OpenAI model integration
- `pydantic`: Data validation and settings
- `langchain-community`: Vector store integration (FAISS)

## Configuration

Settings via environment variables or `.env` file:
- `OPENAI_API_KEY`: Required for LLM calls
- `VECTOR_STORE_PATH`: RAG documentation index location
- `DEFAULT_MODEL`: LLM model (default: gpt-5-mini)
- `MAX_REPAIR_ATTEMPTS`: Repair loop limit (default: 3)

## Notes

- All agent LLM calls are async for efficiency
- State uses `operator.add` annotations for list accumulation
- Repair loop prevents infinite loops with attempt tracking
- Fallback behaviors ensure system continues on LLM parsing errors
- Documentation retrieval is optional (continues without RAG if unavailable)
