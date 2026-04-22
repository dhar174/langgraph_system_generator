"""Notebook validation system for QA checks."""

from __future__ import annotations

import ast
import builtins
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import nbformat
from nbformat import NotebookNode

from langgraph_system_generator.generator.state import QAReport

_BUILTIN_NAMES = set(dir(builtins))


def _cell_source(cell: NotebookNode) -> str:
    """Return a normalized string source for an nbformat cell."""

    source = cell.source or ""
    if isinstance(source, str):
        return source
    return "".join(source)


def _call_name(node: ast.AST) -> str:
    """Return a dotted best-effort name for a call target."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _target_names(node: ast.AST) -> set[str]:
    """Collect assigned target names from a target node."""

    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for element in node.elts:
            names.update(_target_names(element))
    return names


def _node_is_symbol(node: ast.AST, symbol: str) -> bool:
    """Return True when an AST node refers to a target symbol or literal."""

    if isinstance(node, ast.Name):
        return node.id == symbol
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value == symbol
    return False


@dataclass(frozen=True)
class CodeCellMapping:
    """Line mapping from concatenated notebook code to an originating cell."""

    cell_index: int
    section: Optional[str]
    start_line: int
    end_line: int
    source: str


@dataclass
class NotebookValidationContext:
    """Resolved notebook context shared by validator rules."""

    path: Path
    notebook: NotebookNode
    code_cells: List[NotebookNode]
    code_content: str
    code_mappings: List[CodeCellMapping]
    _ast_tree: ast.Module | None = None
    _syntax_error: SyntaxError | None = None
    _ast_loaded: bool = False

    @classmethod
    def from_notebook(
        cls, notebook_path: str | Path, notebook: NotebookNode
    ) -> "NotebookValidationContext":
        """Build context from an already-loaded notebook."""

        code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
        parts: List[str] = []
        mappings: List[CodeCellMapping] = []
        current_line = 1

        for cell_index, cell in enumerate(code_cells):
            source = _cell_source(cell)
            parts.append(source)
            line_count = len(source.splitlines()) or 1
            mappings.append(
                CodeCellMapping(
                    cell_index=cell_index,
                    section=cell.metadata.get("section"),
                    start_line=current_line,
                    end_line=current_line + line_count - 1,
                    source=source,
                )
            )
            current_line += line_count + 1

        return cls(
            path=Path(notebook_path),
            notebook=notebook,
            code_cells=code_cells,
            code_content="\n\n".join(parts),
            code_mappings=mappings,
        )

    def ast_tree(self) -> ast.Module | None:
        """Return the parsed notebook AST, caching syntax failures."""

        if self._ast_loaded:
            return self._ast_tree

        self._ast_loaded = True
        try:
            self._ast_tree = ast.parse(self.code_content or "")
        except SyntaxError as exc:
            self._syntax_error = exc
            self._ast_tree = None
        return self._ast_tree

    @property
    def syntax_error(self) -> SyntaxError | None:
        """Return the cached syntax error, if parsing failed."""

        self.ast_tree()
        return self._syntax_error

    def resolve_line(self, lineno: int | None) -> Dict[str, object]:
        """Map a global AST line back to a notebook code cell."""

        if lineno is None:
            return {}

        for mapping in self.code_mappings:
            if mapping.start_line <= lineno <= mapping.end_line:
                source_lines = mapping.source.splitlines()
                line_in_cell = lineno - mapping.start_line + 1
                source_line = (
                    source_lines[line_in_cell - 1]
                    if 0 < line_in_cell <= len(source_lines)
                    else ""
                )
                return {
                    "line": lineno,
                    "cell_index": mapping.cell_index,
                    "cell_section": mapping.section,
                    "line_in_cell": line_in_cell,
                    "source_line": source_line,
                }

        return {"line": lineno}


class QAValidationRule:
    """Base class for registry-backed notebook validation rules."""

    rule_id = "qa_rule"
    check_name = "QA Rule"
    category = "general"
    failure_severity = "error"
    repairable = False

    def passed_report(
        self, message: str, *, evidence: Dict[str, object] | None = None
    ) -> QAReport:
        """Return a successful QA report."""

        return QAReport(
            check_name=self.check_name,
            passed=True,
            message=message,
            rule_id=self.rule_id,
            severity="info",
            category=self.category,
            repairable=self.repairable,
            evidence=evidence or {},
        )

    def failed_report(
        self,
        message: str,
        *,
        suggestions: Sequence[str] | None = None,
        evidence: Dict[str, object] | None = None,
    ) -> QAReport:
        """Return a failed QA report."""

        return QAReport(
            check_name=self.check_name,
            passed=False,
            message=message,
            rule_id=self.rule_id,
            severity=self.failure_severity,
            category=self.category,
            repairable=self.repairable,
            suggestions=list(suggestions or []),
            evidence=evidence or {},
        )

    def validate(self, context: NotebookValidationContext) -> Optional[QAReport]:
        """Validate the notebook and return a structured QA report."""

        raise NotImplementedError


class PlaceholderRule(QAValidationRule):
    """Detect placeholder text that should not ship in notebooks."""

    rule_id = "placeholder_content"
    check_name = "No Placeholders"
    category = "content"
    repairable = True

    def __init__(self, placeholder_patterns: Sequence[str]):
        self.placeholder_patterns = list(placeholder_patterns)

    def validate(self, context: NotebookValidationContext) -> QAReport:
        content = "\n".join(_cell_source(cell) for cell in context.notebook.cells)
        found_placeholders: List[str] = []
        evidence: Dict[str, object] = {"patterns": []}

        for pattern in self.placeholder_patterns:
            if pattern == "...":
                matches = re.findall(r"(?m)^\s*\.\.\.\s*$", content)
                count = len(matches)
            else:
                count = content.count(pattern)

            if count > 0:
                found_placeholders.append(f"{pattern} ({count}x)")
                evidence["patterns"].append({"pattern": pattern, "count": count})

        if found_placeholders:
            return self.failed_report(
                f"Found placeholders: {', '.join(found_placeholders)}",
                suggestions=[
                    "Replace TODO/FIXME markers with real implementation details.",
                    "Remove placeholder ellipsis and scaffold comments from code cells.",
                ],
                evidence=evidence,
            )

        return self.passed_report(
            "No placeholders found in notebook.",
            evidence={"patterns": []},
        )


class RequiredSectionsRule(QAValidationRule):
    """Ensure required notebook sections exist in cell metadata."""

    rule_id = "required_sections"
    check_name = "Required Sections"
    category = "structure"
    repairable = True

    def __init__(self, required_sections: Sequence[str]):
        self.required_sections = list(required_sections)

    def validate(self, context: NotebookValidationContext) -> QAReport:
        present_sections = {
            cell.metadata.get("section")
            for cell in context.notebook.cells
            if cell.metadata.get("section")
        }
        missing_sections = sorted(set(self.required_sections) - present_sections)

        if missing_sections:
            return self.failed_report(
                f"Missing required sections: {', '.join(missing_sections)}",
                suggestions=[
                    f"Add notebook cells tagged with section metadata for: {', '.join(missing_sections)}.",
                    "Ensure setup, config, graph, and execution sections are present.",
                ],
                evidence={
                    "present_sections": sorted(present_sections),
                    "missing_sections": missing_sections,
                },
            )

        return self.passed_report(
            f"All required sections present: {', '.join(sorted(present_sections))}.",
            evidence={"present_sections": sorted(present_sections)},
        )


class RequiredImportsRule(QAValidationRule):
    """Verify required LangGraph import symbols via parsed imports."""

    rule_id = "required_import_symbols"
    check_name = "Required Imports"
    category = "imports"
    repairable = True

    def __init__(self, required_symbols: Sequence[str]):
        self.required_symbols = list(required_symbols)

    def validate(self, context: NotebookValidationContext) -> QAReport:
        imported_modules: set[str] = set()
        imported_names: set[str] = set()

        for cell in context.code_cells:
            try:
                tree = ast.parse(_cell_source(cell))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imported_modules.add(alias.name)
                        imported_names.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imported_modules.add(module)
                    for alias in node.names:
                        imported_names.add(alias.asname or alias.name)

        missing_symbols: List[str] = []
        for symbol in self.required_symbols:
            if symbol == "langgraph":
                if not any(module.startswith("langgraph") for module in imported_modules):
                    missing_symbols.append(symbol)
            elif symbol not in imported_names:
                missing_symbols.append(symbol)

        if missing_symbols:
            return self.failed_report(
                f"Missing required imports: {', '.join(missing_symbols)}",
                suggestions=[
                    f"Add parsed import statements for: {', '.join(missing_symbols)}.",
                    "Import StateGraph and END from langgraph.graph before graph construction.",
                ],
                evidence={
                    "missing_symbols": missing_symbols,
                    "imported_modules": sorted(imported_modules),
                    "imported_names": sorted(imported_names),
                },
            )

        return self.passed_report(
            "All required imports are present via parsed import statements.",
            evidence={
                "imported_modules": sorted(imported_modules),
                "imported_names": sorted(imported_names),
            },
        )


class PythonSyntaxRule(QAValidationRule):
    """Parse notebook code as Python and surface precise syntax evidence."""

    rule_id = "python_syntax"
    check_name = "Python Syntax"
    category = "syntax"
    repairable = True

    def validate(self, context: NotebookValidationContext) -> QAReport:
        if not context.code_cells:
            return self.failed_report(
                "No code cells found in notebook.",
                suggestions=["Add code cells implementing the workflow graph."],
                evidence={"code_cell_count": 0},
            )

        if context.ast_tree() is None:
            syntax_error = context.syntax_error
            line_evidence = context.resolve_line(getattr(syntax_error, "lineno", None))
            return self.failed_report(
                (
                    f"Syntax error in notebook code: {syntax_error.msg} at line "
                    f"{syntax_error.lineno}"
                ),
                suggestions=[
                    "Fix Python syntax errors before attempting execution.",
                    "Check colons, parentheses, and indentation in code cells.",
                ],
                evidence={
                    "syntax_error": {
                        "message": syntax_error.msg,
                        "offset": syntax_error.offset,
                        **line_evidence,
                    }
                },
            )

        return self.passed_report(
            "Notebook code parses as valid Python.",
            evidence={"code_cell_count": len(context.code_cells)},
        )


class UndefinedNameRule(QAValidationRule):
    """Detect likely undefined-name typos in common top-level notebook code paths."""

    rule_id = "undefined_names"
    check_name = "Undefined Names"
    category = "symbols"
    repairable = True
    failure_severity = "warning"

    def validate(self, context: NotebookValidationContext) -> Optional[QAReport]:
        tree = context.ast_tree()
        if tree is None:
            return None

        class _TopLevelLoadNameVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.load_names: List[ast.Name] = []

            def visit_Name(self, node: ast.Name) -> None:
                if isinstance(node.ctx, ast.Load):
                    self.load_names.append(node)

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: ARG002
                return

            def visit_AsyncFunctionDef(
                self, node: ast.AsyncFunctionDef  # noqa: ARG002
            ) -> None:
                return

            def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: ARG002
                return

            def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: ARG002
                return

            def visit_ListComp(self, node: ast.ListComp) -> None:  # noqa: ARG002
                return

            def visit_SetComp(self, node: ast.SetComp) -> None:  # noqa: ARG002
                return

            def visit_DictComp(self, node: ast.DictComp) -> None:  # noqa: ARG002
                return

            def visit_GeneratorExp(
                self, node: ast.GeneratorExp  # noqa: ARG002
            ) -> None:
                return

        defined_names: set[str] = set()
        undefined_names: List[Dict[str, object]] = []

        for statement in tree.body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    defined_names.add(alias.asname or alias.name.split(".")[0])
                continue

            if isinstance(statement, ast.ImportFrom):
                for alias in statement.names:
                    defined_names.add(alias.asname or alias.name)
                continue

            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined_names.add(statement.name)
                continue

            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    defined_names.update(_target_names(target))
            elif isinstance(statement, ast.AnnAssign):
                defined_names.update(_target_names(statement.target))
            elif isinstance(statement, ast.AugAssign):
                defined_names.update(_target_names(statement.target))

            visitor = _TopLevelLoadNameVisitor()
            visitor.visit(statement)
            for node in visitor.load_names:
                name = node.id
                if name in defined_names or name in _BUILTIN_NAMES:
                    continue
                if name in {"True", "False", "None"}:
                    continue
                suggestion = difflib.get_close_matches(
                    name, sorted(defined_names), n=1, cutoff=0.75
                )
                undefined_names.append(
                    {
                        "name": name,
                        "suggestion": suggestion[0] if suggestion else None,
                        **context.resolve_line(getattr(node, "lineno", None)),
                    }
                )

            if isinstance(statement, ast.With):
                for item in statement.items:
                    if item.optional_vars is not None:
                        defined_names.update(_target_names(item.optional_vars))
            elif isinstance(statement, ast.For):
                defined_names.update(_target_names(statement.target))

        if undefined_names:
            first_issue = undefined_names[0]
            name = str(first_issue["name"])
            suggestion = first_issue.get("suggestion")
            suggestion_text = (
                f" Did you mean '{suggestion}'?" if isinstance(suggestion, str) else ""
            )
            return self.failed_report(
                f"Likely undefined name '{name}' detected in notebook code.{suggestion_text}",
                suggestions=[
                    f"Define or import '{name}' before it is used.",
                    "Check for small naming typos between graph objects and execution cells.",
                ],
                evidence={"undefined_names": undefined_names},
            )

        return self.passed_report(
            "No likely undefined-name issues were detected in top-level notebook code.",
            evidence={"defined_names": sorted(defined_names)},
        )


class GraphStructureRule(QAValidationRule):
    """Validate graph construction using parsed AST call structure, not substring search."""

    rule_id = "graph_structure"
    check_name = "Graph Compilation"
    category = "graph_structure"
    repairable = True

    def validate(self, context: NotebookValidationContext) -> Optional[QAReport]:
        if not context.code_cells:
            return self.failed_report(
                "No code cells found in notebook.",
                suggestions=["Add code cells to implement the graph."],
                evidence={"code_cell_count": 0},
            )

        tree = context.ast_tree()
        if tree is None:
            return None

        stategraph_calls: List[Dict[str, object]] = []
        compile_calls: List[Dict[str, object]] = []
        entrypoint_calls: List[Dict[str, object]] = []
        terminal_calls: List[Dict[str, object]] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            call_name = _call_name(node.func)
            call_evidence = {
                "call_name": call_name,
                **context.resolve_line(getattr(node, "lineno", None)),
            }

            if call_name.endswith("StateGraph"):
                stategraph_calls.append(call_evidence)
            elif call_name.endswith(".compile"):
                compile_calls.append(call_evidence)
            elif call_name.endswith(".set_entry_point"):
                entrypoint_calls.append(call_evidence)
            elif call_name.endswith(".add_edge") and len(node.args) >= 2:
                if _node_is_symbol(node.args[0], "START"):
                    entrypoint_calls.append(call_evidence)
                if _node_is_symbol(node.args[1], "END"):
                    terminal_calls.append(call_evidence)
            elif call_name.endswith(".set_finish_point"):
                terminal_calls.append(call_evidence)
            elif call_name.endswith(".add_conditional_edges"):
                for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                    if isinstance(argument, ast.Dict):
                        for value in argument.values:
                            if _node_is_symbol(value, "END"):
                                terminal_calls.append(call_evidence)
                                break

        if not stategraph_calls:
            return self.failed_report(
                "No StateGraph construction found in notebook.",
                suggestions=[
                    "Add StateGraph construction code.",
                    "Instantiate a StateGraph before wiring nodes and edges.",
                ],
                evidence={"stategraph_calls": [], "compile_calls": compile_calls},
            )

        if not compile_calls:
            return self.failed_report(
                "Graph compilation step (.compile()) not found.",
                suggestions=[
                    "Add graph.compile() or workflow.compile() before execution.",
                    "Ensure the built graph is compiled before invoking it.",
                ],
                evidence={
                    "stategraph_calls": stategraph_calls,
                    "compile_calls": [],
                },
            )

        if not entrypoint_calls:
            return self.failed_report(
                "Graph entry point wiring not found (set_entry_point() or START edge).",
                suggestions=[
                    "Configure the graph entry point with set_entry_point() or START routing.",
                ],
                evidence={
                    "stategraph_calls": stategraph_calls,
                    "compile_calls": compile_calls,
                    "entrypoint_calls": [],
                },
            )

        if not terminal_calls:
            return self.failed_report(
                "No terminal path to END found in notebook.",
                suggestions=[
                    "Wire at least one graph path to END or use set_finish_point().",
                ],
                evidence={
                    "stategraph_calls": stategraph_calls,
                    "compile_calls": compile_calls,
                    "entrypoint_calls": entrypoint_calls,
                    "terminal_calls": [],
                },
            )

        return self.passed_report(
            "Notebook code contains parsed StateGraph construction, entry wiring, and compilation.",
            evidence={
                "stategraph_calls": stategraph_calls,
                "compile_calls": compile_calls,
                "entrypoint_calls": entrypoint_calls,
                "terminal_calls": terminal_calls,
            },
        )


class ValidatorRegistry:
    """Simple ordered registry for built-in and future validation rules."""

    def __init__(self, rules: Optional[Iterable[QAValidationRule]] = None):
        self._rules: Dict[str, QAValidationRule] = {}
        for rule in rules or []:
            self.register(rule)

    def register(self, rule: QAValidationRule) -> None:
        """Register a validation rule."""

        self._rules[rule.rule_id] = rule

    def get(self, rule_id: str) -> QAValidationRule:
        """Return a registered validation rule."""

        return self._rules[rule_id]

    def rules(self) -> List[QAValidationRule]:
        """Return the ordered list of registered validation rules."""

        return list(self._rules.values())

    def clone(self) -> "ValidatorRegistry":
        """Return a shallow clone of the current registry."""

        return ValidatorRegistry(self.rules())


class NotebookValidator:
    """Validates generated notebooks for quality and correctness."""

    PLACEHOLDER_PATTERNS = [
        "TODO",
        "FIXME",
        "PLACEHOLDER",
        "...",
        "# Your code here",
        "pass  # implement",
    ]
    REQUIRED_SECTIONS = ["setup", "config", "graph", "execution"]
    REQUIRED_IMPORTS = ["langgraph", "StateGraph", "END"]

    def __init__(self, registry: ValidatorRegistry | None = None):
        self.registry = registry.clone() if registry else self._build_default_registry()

    def _build_default_registry(self) -> ValidatorRegistry:
        """Create the default ordered validation registry."""

        return ValidatorRegistry(
            [
                PlaceholderRule(self.PLACEHOLDER_PATTERNS),
                RequiredSectionsRule(self.REQUIRED_SECTIONS),
                RequiredImportsRule(self.REQUIRED_IMPORTS),
                PythonSyntaxRule(),
                UndefinedNameRule(),
                GraphStructureRule(),
            ]
        )

    def _load_notebook(self, notebook_path: str | Path) -> NotebookNode:
        """Load a notebook from disk as v4."""

        path = Path(notebook_path)
        with path.open("r", encoding="utf-8") as handle:
            return nbformat.read(handle, as_version=4)

    def _context_from_path(
        self, notebook_path: str | Path
    ) -> NotebookValidationContext:
        """Load a notebook and build a reusable validation context."""

        notebook = self._load_notebook(notebook_path)
        return NotebookValidationContext.from_notebook(notebook_path, notebook)

    def validate_json_structure(self, notebook_path: str | Path) -> QAReport:
        """Check that notebook JSON is valid and can be loaded."""

        try:
            path = Path(notebook_path)
            if not path.exists():
                return QAReport(
                    check_name="JSON Validity",
                    passed=False,
                    message=f"Notebook file not found: {notebook_path}",
                    rule_id="json_structure",
                    severity="error",
                    category="serialization",
                    repairable=False,
                    suggestions=[
                        "Ensure the notebook was generated and saved correctly."
                    ],
                    evidence={"path": str(path)},
                )

            notebook = self._load_notebook(path)
            nbformat.validate(notebook)
            return QAReport(
                check_name="JSON Validity",
                passed=True,
                message="Notebook JSON is valid and properly structured.",
                rule_id="json_structure",
                severity="info",
                category="serialization",
                repairable=False,
                evidence={"path": str(path)},
            )
        except json.JSONDecodeError as exc:
            return QAReport(
                check_name="JSON Validity",
                passed=False,
                message=f"Invalid JSON: {exc}",
                rule_id="json_structure",
                severity="error",
                category="serialization",
                repairable=False,
                suggestions=[
                    "Check for malformed JSON syntax in the notebook file.",
                    "Ensure the file is encoded as UTF-8 and fully written.",
                ],
                evidence={"error_type": "json", "message": str(exc)},
            )
        except nbformat.ValidationError as exc:
            return QAReport(
                check_name="JSON Validity",
                passed=False,
                message=f"Invalid notebook structure: {exc}",
                rule_id="json_structure",
                severity="error",
                category="serialization",
                repairable=False,
                suggestions=[
                    "Verify all required notebook fields and cell metadata are present.",
                ],
                evidence={"error_type": "nbformat", "message": str(exc)},
            )
        except Exception as exc:
            return QAReport(
                check_name="JSON Validity",
                passed=False,
                message=f"Error reading notebook: {exc}",
                rule_id="json_structure",
                severity="error",
                category="serialization",
                repairable=False,
                suggestions=["Check file permissions and notebook path resolution."],
                evidence={"error_type": type(exc).__name__, "message": str(exc)},
            )

    def check_no_placeholders(self, notebook_path: str | Path) -> QAReport:
        """Ensure no placeholder text remains in the notebook."""

        try:
            context = self._context_from_path(notebook_path)
            return self.registry.get("placeholder_content").validate(context) or QAReport(
                check_name="No Placeholders",
                passed=True,
                message="No placeholders found in notebook.",
                rule_id="placeholder_content",
                severity="info",
                category="content",
                repairable=True,
            )
        except Exception as exc:
            return QAReport(
                check_name="No Placeholders",
                passed=False,
                message=f"Error checking placeholders: {exc}",
                rule_id="placeholder_content",
                severity="error",
                category="content",
                repairable=True,
                suggestions=["Verify the notebook file is readable before validation."],
                evidence={"error_type": type(exc).__name__},
            )

    def check_required_sections(
        self, notebook_path: str | Path, required_sections: Optional[List[str]] = None
    ) -> QAReport:
        """Verify that notebook has all required sections."""

        try:
            context = self._context_from_path(notebook_path)
            rule = RequiredSectionsRule(required_sections or self.REQUIRED_SECTIONS)
            return rule.validate(context) or rule.passed_report(
                "All required sections present."
            )
        except Exception as exc:
            return QAReport(
                check_name="Required Sections",
                passed=False,
                message=f"Error checking sections: {exc}",
                rule_id="required_sections",
                severity="error",
                category="structure",
                repairable=True,
                suggestions=["Verify notebook structure and section metadata."],
                evidence={"error_type": type(exc).__name__},
            )

    def check_imports_present(
        self, notebook_path: str | Path, required_imports: Optional[List[str]] = None
    ) -> QAReport:
        """Ensure necessary imports are present in the notebook."""

        try:
            context = self._context_from_path(notebook_path)
            rule = RequiredImportsRule(required_imports or self.REQUIRED_IMPORTS)
            return rule.validate(context) or rule.passed_report(
                "All required imports are present."
            )
        except Exception as exc:
            return QAReport(
                check_name="Required Imports",
                passed=False,
                message=f"Error checking imports: {exc}",
                rule_id="required_import_symbols",
                severity="error",
                category="imports",
                repairable=True,
                suggestions=["Verify notebook code cells can be parsed for import analysis."],
                evidence={"error_type": type(exc).__name__},
            )

    def check_graph_compiles(self, notebook_path: str | Path) -> QAReport:
        """Check if the graph construction code compiles and is structurally valid."""

        try:
            context = self._context_from_path(notebook_path)
            syntax_report = PythonSyntaxRule().validate(context)
            if syntax_report is not None and not syntax_report.passed:
                return QAReport(
                    check_name="Graph Compilation",
                    passed=False,
                    message=syntax_report.message,
                    rule_id=syntax_report.rule_id,
                    severity=syntax_report.severity,
                    category=syntax_report.category,
                    repairable=syntax_report.repairable,
                    suggestions=syntax_report.suggestions,
                    evidence=syntax_report.evidence,
                )

            graph_report = GraphStructureRule().validate(context)
            return graph_report or QAReport(
                check_name="Graph Compilation",
                passed=True,
                message="Notebook code compiles and contains proper graph construction.",
                rule_id="graph_structure",
                severity="info",
                category="graph_structure",
                repairable=True,
            )
        except Exception as exc:
            return QAReport(
                check_name="Graph Compilation",
                passed=False,
                message=f"Error checking graph compilation: {exc}",
                rule_id="graph_structure",
                severity="error",
                category="graph_structure",
                repairable=True,
                suggestions=["Verify notebook structure and graph code cells."],
                evidence={"error_type": type(exc).__name__},
            )

    def validate_all(self, notebook_path: str | Path) -> List[QAReport]:
        """Run all validation checks on a notebook."""

        reports: List[QAReport] = []
        json_report = self.validate_json_structure(notebook_path)
        reports.append(json_report)

        if not json_report.passed:
            return reports

        context = self._context_from_path(notebook_path)
        syntax_report: QAReport | None = None
        for rule in self.registry.rules():
            if isinstance(rule, PythonSyntaxRule):
                report = rule.validate(context)
                syntax_report = report
                if report is not None:
                    reports.append(report)
                continue

            if isinstance(rule, (UndefinedNameRule, GraphStructureRule)) and (
                syntax_report is not None and not syntax_report.passed
            ):
                continue
            report = rule.validate(context)
            if report is not None:
                reports.append(report)

        return reports
