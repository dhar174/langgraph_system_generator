# Pattern Library Examples

This directory contains comprehensive, runnable examples demonstrating the use of the LangGraph System Generator pattern library.

## Prerequisites

1. Install dependencies:
   ```bash
   pip install -r ../requirements.txt
   ```

2. Set your OpenAI API key:
   ```bash
   export OPENAI_API_KEY='your-key-here'
   ```

3. Install the package in development mode (from repository root):
   ```bash
   pip install -e .
   ```

## Available Examples

### 1. Router Pattern Example
**File**: `router_pattern_example.py`

Demonstrates the Router Pattern for creating multi-agent systems with dynamic routing.

**What it covers**:
- Complete router system generation
- Custom router configuration with additional state fields
- Individual component generation (state, router node, route handlers, graph)
- Integration patterns for custom workflows

**Usage**:
```bash
python examples/router_pattern_example.py
```

**Example scenarios**:
- Customer support routing (technical, billing, general)
- Content handling (search, analyze, summarize)
- Request classification systems

---

### 2. Subagents Pattern Example
**File**: `subagents_pattern_example.py`

Demonstrates the Subagents Pattern for supervisor-based agent coordination.

**What it covers**:
- Research team system with supervisor
- Custom supervisor configuration
- Collaborative content creation workflow
- Scalability with large agent teams (8+ agents)
- Tool integration for subagents

**Usage**:
```bash
python examples/subagents_pattern_example.py
```

**Example scenarios**:
- Research and analysis workflows
- Content creation pipelines
- Software development teams
- Data processing pipelines

---

### 3. Critique-Revise Loop Pattern Example
**File**: `critique_revise_pattern_example.py`

Demonstrates the Critique-Revise Loop Pattern for iterative quality improvement.

**What it covers**:
- Content refinement system
- Custom quality assurance configuration
- Iterative improvement workflow visualization
- Domain-specific quality criteria (technical docs, marketing, research, code)
- Advanced configurations (strict quality control, fast iteration, continuous improvement)

**Usage**:
```bash
python examples/critique_revise_pattern_example.py
```

**Example scenarios**:
- Technical documentation refinement
- Code generation with quality checks
- Content writing and editing
- Report generation and review

---

## Understanding the Output

Each example generates:

1. **Complete Working Code**: Full LangGraph workflow implementations
2. **Component Demonstrations**: Individual pattern components (state, nodes, graphs)
3. **Integration Patterns**: How to use patterns in custom workflows
4. **Best Practices**: Tips and recommendations for each pattern

### Example Output Structure

```
================================================================================
Pattern Example
================================================================================

Generated Code:
[Complete, runnable Python code for the pattern]

Key Components:
- State Schema
- Node Implementations
- Graph Construction
- Execution Logic

Integration Tips:
[How to use the generated code in your projects]
================================================================================
```

## Running Without API Key

The examples will run and generate code even without an API key. They demonstrate the code generation capabilities of the pattern library. However, to **execute** the generated workflows, you'll need a valid OpenAI API key.

When run without an API key, you'll see:
```
⚠️  WARNING: OPENAI_API_KEY not found in environment
The generated code requires an API key to run.
Set it with: export OPENAI_API_KEY='your-key-here'
```

## Customization

All examples show how to customize:

- **LLM Models**: Change from default `gpt-5-mini` to `gpt-4`, `gpt-3.5-turbo`, etc.
- **State Fields**: Add custom fields to state schemas
- **Agent Descriptions**: Customize agent roles and capabilities
- **Quality Criteria**: Define domain-specific evaluation criteria
- **Thresholds**: Adjust quality scores, max iterations, etc.

## Integration with Your Projects

To use the generated code in your projects:

1. **Run an example** to see the generated code
2. **Copy relevant sections** into your project files
3. **Customize as needed**:
   - Modify prompts for your domain
   - Add tools (web search, databases, APIs)
   - Adjust routing/coordination logic
   - Configure LLM parameters
4. **Test with sample inputs**
5. **Deploy to production**

## Example Workflow

```python
# 1. Generate code using pattern library
from langgraph_system_generator.patterns import RouterPattern

routes = ["support", "sales", "technical"]
code = RouterPattern.generate_complete_example(routes)

# 2. Save to file
with open("my_workflow.py", "w") as f:
    f.write(code)

# 3. Customize the generated code
# Edit my_workflow.py to add your domain logic

# 4. Run your custom workflow
# python my_workflow.py
```

## Pattern Selection Guide

| Use Case | Recommended Pattern | Example File |
|----------|---------------------|--------------|
| Input classification | Router | `router_pattern_example.py` |
| Task decomposition | Subagents | `subagents_pattern_example.py` |
| Quality improvement | Critique-Revise | `critique_revise_pattern_example.py` |
| Specialized handling | Router | `router_pattern_example.py` |
| Multi-step workflows | Subagents | `subagents_pattern_example.py` |
| Iterative refinement | Critique-Revise | `critique_revise_pattern_example.py` |

## Additional Resources

- **Pattern Documentation**: [../docs/patterns.md](../docs/patterns.md)
- **Test Suite**: [../tests/unit/test_patterns.py](../tests/unit/test_patterns.py)
- **Source Code**: [../src/langgraph_system_generator/patterns/](../src/langgraph_system_generator/patterns/)
- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/

## Troubleshooting

### Import Error: `ModuleNotFoundError: No module named 'langgraph_system_generator'`

Install the package in development mode:
```bash
cd ..  # Go to repository root
pip install -e .
```

### API Key Issues

Ensure your API key is set:
```bash
export OPENAI_API_KEY='sk-...'
python examples/router_pattern_example.py
```

### Pattern Import Issues

Make sure you're importing from the correct module:
```python
from langgraph_system_generator.patterns import RouterPattern
from langgraph_system_generator.patterns import SubagentsPattern
from langgraph_system_generator.patterns import CritiqueLoopPattern
```

## Contributing Examples

To add new examples:

1. Create a new example file following the naming convention
2. Include comprehensive demonstrations of pattern features
3. Add comments explaining key concepts
4. Test the example runs without errors
5. Update this README with the new example
6. Submit a pull request

## Support

For issues or questions:
- Review the generated code and comments
- Check [../docs/patterns.md](../docs/patterns.md) for detailed documentation
- Open an issue on GitHub
- Review test cases in [../tests/](../tests/) for usage patterns
