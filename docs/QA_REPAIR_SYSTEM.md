# QA & Repair System Documentation

## Overview

The QA & Repair system provides comprehensive validation and automated fixing capabilities for generated LangGraph notebooks. It implements Phase 5 of the implementation plan with structured validation checks and bounded repair logic.

## Components

### 1. NotebookValidator (`src/qa/validators.py`)

The `NotebookValidator` class provides multiple validation checks that produce structured `QAReport` entries.

#### Available Validation Checks

##### `validate_json_structure(notebook_path)`
- Checks if the notebook JSON is valid and can be loaded
- Validates notebook structure using nbformat
- Returns: `QAReport` with pass/fail status

##### `check_no_placeholders(notebook_path)`
- Ensures no placeholder text remains in the notebook
- Detects: TODO, FIXME, PLACEHOLDER, ellipsis, "Your code here", etc.
- Returns: `QAReport` with details of found placeholders

##### `check_required_sections(notebook_path, required_sections=None)`
- Verifies notebook has all required sections
- Default sections: setup, config, graph, execution
- Custom sections can be specified
- Returns: `QAReport` with missing sections if any

##### `check_imports_present(notebook_path, required_imports=None)`
- Ensures necessary imports are present
- Default imports: langgraph, StateGraph, END
- Custom imports can be specified
- Returns: `QAReport` with missing imports if any

##### `check_graph_compiles(notebook_path)`
- Performs static syntax validation of code
- Checks for StateGraph construction
- Verifies .compile() call is present
- Returns: `QAReport` with compilation status

##### `validate_all(notebook_path)`
- Runs all validation checks in sequence
- Stops early if JSON validation fails
- Returns: List of `QAReport` objects

#### Example Usage

```python
from langgraph_system_generator.qa import NotebookValidator

validator = NotebookValidator()

# Run all validations
reports = validator.validate_all("generated_notebook.ipynb")

# Check results
for report in reports:
    print(f"{report.check_name}: {'PASS' if report.passed else 'FAIL'}")
    print(f"  {report.message}")
    if not report.passed:
        for suggestion in report.suggestions:
            print(f"  - {suggestion}")
```

### 2. NotebookRepairAgent (`src/qa/repair.py`)

The `NotebookRepairAgent` class provides automated repair capabilities with bounded retry logic.

#### Features

- **Bounded Retries**: Configurable maximum repair attempts (default: 3)
- **Safe Repairs**: Only modifies notebooks based on identified issues
- **Re-validation**: Automatically re-validates after repairs
- **Repair Summary**: Provides detailed summary of repair results

#### Repair Capabilities

##### Placeholder Removal
- Removes TODO, FIXME, PLACEHOLDER comments
- Cleans up ellipsis placeholders
- Removes "Your code here" markers
- Preserves actual code

##### Import Addition
- Adds missing langgraph imports
- Adds StateGraph and END imports
- Appends to first code cell

##### Section Addition
- Creates missing required sections
- Adds markdown headers
- Adds placeholder code cells

##### Compilation Fixes
- Adds missing StateGraph construction
- Adds missing .compile() calls
- Repairs graph-related code

#### Example Usage

```python
from langgraph_system_generator.qa import NotebookRepairAgent, NotebookValidator

# Initialize agent with custom max attempts
agent = NotebookRepairAgent(max_attempts=3)
validator = NotebookValidator()

# Validate notebook
notebook_path = "generated_notebook.ipynb"
qa_reports = validator.validate_all(notebook_path)

# Attempt repair if needed
if any(not r.passed for r in qa_reports):
    success, new_reports = agent.repair_notebook(
        notebook_path, 
        qa_reports,
        attempt=0
    )
    
    if success:
        print("All issues repaired!")
    else:
        print("Some issues could not be repaired:")
        for r in new_reports:
            if not r.passed:
                print(f"  - {r.check_name}: {r.message}")

# Get repair summary
summary = agent.get_repair_summary(new_reports)
print(f"Success rate: {summary['success_rate']*100:.1f}%")
print(f"Passed: {summary['passed']}/{summary['total_checks']}")
```

#### Repair Loop Pattern

```python
from langgraph_system_generator.qa import NotebookRepairAgent, NotebookValidator

agent = NotebookRepairAgent(max_attempts=3)
validator = NotebookValidator()

notebook_path = "notebook.ipynb"
qa_reports = validator.validate_all(notebook_path)
attempt = 0

while agent.should_retry(qa_reports, attempt):
    success, qa_reports = agent.repair_notebook(
        notebook_path, 
        qa_reports, 
        attempt
    )
    
    if success:
        print("Repair successful!")
        break
    
    attempt += 1

if not all(r.passed for r in qa_reports):
    print("Could not fix all issues after max attempts")
```

## QAReport Structure

The `QAReport` model (defined in `generator/state.py`) contains:

```python
class QAReport(BaseModel):
    check_name: str          # Name of the QA check
    passed: bool             # Whether the check passed
    message: str             # Report message or error details
    suggestions: List[str]   # Suggested fixes (optional)
```

## Integration with Generator Graph

The QA & Repair system is designed to integrate with the generator workflow:

1. **After Notebook Generation**: Run validation checks
2. **QA Reports**: Collect structured reports
3. **Decision Node**: Determine if repair is needed
4. **Repair Node**: Apply fixes if within attempt limits
5. **Re-validation**: Run checks again after repair
6. **Loop or Exit**: Continue repair loop or finalize

## Testing

Comprehensive unit tests are provided:

- `tests/unit/test_validators.py`: 20 tests covering all validation checks
- `tests/unit/test_repair.py`: 18 tests covering repair logic

Run tests:
```bash
pytest tests/unit/test_validators.py -v
pytest tests/unit/test_repair.py -v
```

## Best Practices

1. **Always validate JSON first**: Other checks depend on valid notebook structure
2. **Use bounded retries**: Prevent infinite repair loops
3. **Review repair summaries**: Understand what was fixed and what wasn't
4. **Custom validations**: Extend validators for specific use cases
5. **Safe repairs**: Test repairs don't introduce new issues

## Extending the System

### Adding New Validators

```python
class NotebookValidator:
    def check_custom_requirement(self, notebook_path: str | Path) -> QAReport:
        """Add your custom validation logic."""
        try:
            # Your validation logic here
            return QAReport(
                check_name="Custom Check",
                passed=True,
                message="Check passed"
            )
        except Exception as e:
            return QAReport(
                check_name="Custom Check",
                passed=False,
                message=str(e),
                suggestions=["Fix suggestion"]
            )
```

### Adding New Repair Methods

```python
class NotebookRepairAgent:
    def _repair_custom_issue(self, nb: NotebookNode, report: QAReport) -> bool:
        """Add your custom repair logic."""
        repaired = False
        
        # Your repair logic here
        # Modify nb in place
        
        return repaired
```

## Error Handling

All validators and repair methods include comprehensive error handling:

- Invalid file paths
- Malformed JSON
- Read/write errors
- Validation errors

Errors are captured in QAReport objects with actionable suggestions.

## Performance Considerations

- **Validation**: Fast, operates on static analysis
- **Repair**: Bounded by max_attempts parameter
- **File I/O**: Reads and writes are optimized
- **Memory**: Efficient notebook manipulation

## Limitations

1. **Static Analysis Only**: Validators don't execute notebooks
2. **Pattern Matching**: Some checks use simple pattern matching
3. **Safe Repairs**: Only fixes low-risk issues automatically
4. **Bounded Attempts**: May not fix all issues in max attempts

For execution validation, consider:
- Using nbclient to execute notebooks
- Implementing runtime smoke tests
- Adding integration tests

## Future Enhancements

Potential additions to the QA & Repair system:

1. **Execution Validation**: Run notebooks in sandbox
2. **LLM-based Repairs**: Use LLM to suggest complex fixes
3. **Diff Reports**: Show before/after changes
4. **Repair Confidence Scores**: Indicate repair reliability
5. **Custom Repair Strategies**: User-defined repair logic
6. **Parallel Validation**: Run checks concurrently
7. **Incremental Repairs**: Fix one issue at a time
