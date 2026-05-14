"""Notebook validation system for QA checks."""

from __future__ import annotations

import ast
import builtins
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, runtime_checkable

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


def _literal_string(node: ast.AST) -> str | None:
    """Return a string literal value when an AST node is a simple string."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dict_string_keys(node: ast.AST) -> set[str]:
    """Return literal string keys from a dictionary AST node."""

    if not isinstance(node, ast.Dict):
        return set()
    keys: set[str] = set()
    for key in node.keys:
        value = _literal_string(key) if key is not None else None
        if value:
            keys.add(value)
    return keys


def _dict_value_for_key(node: ast.AST, key_name: str) -> ast.AST | None:
    """Return a dictionary value for a literal string key."""

    if not isinstance(node, ast.Dict):
        return None
    for key, value in zip(node.keys, node.values):
        if key is not None and _literal_string(key) == key_name:
            return value
    return None


def _annotation_uses_annotated(node: ast.AST | None) -> bool:
    """Return True when a type annotation uses typing.Annotated."""

    if node is None:
        return False
    if isinstance(node, ast.Subscript):
        call_name = _call_name(node.value)
        return call_name.endswith("Annotated")
    return False


def _class_base_names(node: ast.ClassDef) -> set[str]:
    """Return dotted names for a class' base expressions."""

    return {_call_name(base) for base in node.bases if _call_name(base)}


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

        undefined_names: List[Dict[str, object]] = []

        def _record_undefined_from(
            node: ast.AST | None, currently_defined: set[str]
        ) -> None:
            if node is None:
                return

            visitor = _TopLevelLoadNameVisitor()
            visitor.visit(node)
            for load_name in visitor.load_names:
                name = load_name.id
                if name in currently_defined or name in _BUILTIN_NAMES:
                    continue
                if name in {"True", "False", "None"}:
                    continue
                suggestion = difflib.get_close_matches(
                    name, sorted(currently_defined), n=1, cutoff=0.75
                )
                undefined_names.append(
                    {
                        "name": name,
                        "suggestion": suggestion[0] if suggestion else None,
                        **context.resolve_line(getattr(load_name, "lineno", None)),
                    }
                )

        def _scan_block(
            statements: Sequence[ast.stmt], currently_defined: set[str]
        ) -> set[str]:
            scoped_names = set(currently_defined)
            for statement in statements:
                _scan_statement(statement, scoped_names)
            return scoped_names

        def _scan_statement(statement: ast.stmt, currently_defined: set[str]) -> None:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    currently_defined.add(alias.asname or alias.name.split(".")[0])
                return

            if isinstance(statement, ast.ImportFrom):
                for alias in statement.names:
                    currently_defined.add(alias.asname or alias.name)
                return

            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                currently_defined.add(statement.name)
                return

            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    _record_undefined_from(target, currently_defined)
                _record_undefined_from(statement.value, currently_defined)
                for target in statement.targets:
                    currently_defined.update(_target_names(target))
                return

            if isinstance(statement, ast.AnnAssign):
                _record_undefined_from(statement.target, currently_defined)
                _record_undefined_from(statement.annotation, currently_defined)
                _record_undefined_from(statement.value, currently_defined)
                currently_defined.update(_target_names(statement.target))
                return

            if isinstance(statement, ast.AugAssign):
                _record_undefined_from(statement.target, currently_defined)
                _record_undefined_from(statement.value, currently_defined)
                currently_defined.update(_target_names(statement.target))
                return

            if isinstance(statement, (ast.For, ast.AsyncFor)):
                _record_undefined_from(statement.iter, currently_defined)
                currently_defined.update(_target_names(statement.target))
                currently_defined.update(
                    _scan_block(statement.body, set(currently_defined))
                )
                currently_defined.update(
                    _scan_block(statement.orelse, set(currently_defined))
                )
                return

            if isinstance(statement, (ast.With, ast.AsyncWith)):
                for item in statement.items:
                    _record_undefined_from(item.context_expr, currently_defined)
                    _record_undefined_from(item.optional_vars, currently_defined)
                for item in statement.items:
                    if item.optional_vars is not None:
                        currently_defined.update(_target_names(item.optional_vars))
                currently_defined.update(
                    _scan_block(statement.body, set(currently_defined))
                )
                return

            if isinstance(statement, ast.If):
                _record_undefined_from(statement.test, currently_defined)
                currently_defined.update(
                    _scan_block(statement.body, set(currently_defined))
                )
                currently_defined.update(
                    _scan_block(statement.orelse, set(currently_defined))
                )
                return

            if isinstance(statement, ast.While):
                _record_undefined_from(statement.test, currently_defined)
                currently_defined.update(
                    _scan_block(statement.body, set(currently_defined))
                )
                currently_defined.update(
                    _scan_block(statement.orelse, set(currently_defined))
                )
                return

            if isinstance(statement, ast.Try):
                currently_defined.update(
                    _scan_block(statement.body, set(currently_defined))
                )
                for handler in statement.handlers:
                    handler_scope = set(currently_defined)
                    _record_undefined_from(handler.type, handler_scope)
                    if handler.name:
                        handler_scope.add(handler.name)
                    currently_defined.update(_scan_block(handler.body, handler_scope))
                currently_defined.update(
                    _scan_block(statement.orelse, set(currently_defined))
                )
                currently_defined.update(
                    _scan_block(statement.finalbody, set(currently_defined))
                )
                return

            _record_undefined_from(statement, currently_defined)

        defined_names = _scan_block(tree.body, set())

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


class CanonicalSectionOrderRule(QAValidationRule):
    """Ensure generated notebook sections follow the public execution contract."""

    rule_id = "canonical_section_order"
    check_name = "Canonical Section Order"
    category = "notebook_contract"
    failure_severity = "error"
    repairable = True

    CANONICAL_ORDER = [
        "intro",
        "setup",
        "config",
        "state",
        "tools",
        "nodes",
        "graph",
        "execution",
        "export",
        "troubleshooting",
    ]
    SECTION_ALIASES = {"state_definition": "state"}

    def validate(self, context: NotebookValidationContext) -> QAReport:
        section_positions = {
            section: index for index, section in enumerate(self.CANONICAL_ORDER)
        }
        seen_sections: list[dict[str, Any]] = []
        last_position = -1
        violations: list[dict[str, Any]] = []

        for cell_index, cell in enumerate(context.notebook.cells):
            raw_section = cell.metadata.get("section")
            section = self.SECTION_ALIASES.get(raw_section, raw_section)
            if section not in section_positions:
                continue
            position = section_positions[section]
            seen_sections.append(
                {
                    "section": raw_section,
                    "canonical_section": section,
                    "cell_index": cell_index,
                    "position": position,
                }
            )
            if position < last_position:
                violations.append(
                    {
                        "section": raw_section,
                        "canonical_section": section,
                        "cell_index": cell_index,
                    }
                )
            last_position = max(last_position, position)

        if violations:
            return self.failed_report(
                "Notebook sections are not in canonical order.",
                suggestions=[
                    "Render final notebooks in intro, setup, config, state, tools, nodes, graph, execution, export, troubleshooting order.",
                    "Preserve leading unsectioned preamble cells before canonical sections.",
                ],
                evidence={
                    "canonical_order": self.CANONICAL_ORDER,
                    "seen_sections": seen_sections,
                    "violations": violations,
                },
            )

        return self.passed_report(
            "Notebook sections follow the canonical execution order.",
            evidence={
                "canonical_order": self.CANONICAL_ORDER,
                "seen_sections": seen_sections,
            },
        )


class LangGraphTopologyRule(QAValidationRule):
    """Validate final notebook graph topology beyond basic compile presence."""

    rule_id = "langgraph_topology"
    check_name = "LangGraph Topology"
    category = "graph_structure"
    failure_severity = "error"
    repairable = False

    def validate(self, context: NotebookValidationContext) -> Optional[QAReport]:
        tree = context.ast_tree()
        if tree is None:
            return None

        function_defs: dict[str, list[dict[str, object]]] = {}
        node_registrations: list[dict[str, object]] = []
        edge_registrations: list[dict[str, object]] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_defs.setdefault(node.name, []).append(
                    context.resolve_line(getattr(node, "lineno", None))
                )
                continue

            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func)
            if call_name.endswith(".add_node") and node.args:
                node_id = _literal_string(node.args[0])
                if node_id:
                    handler_name = _call_name(node.args[1]) if len(node.args) > 1 else ""
                    node_registrations.append(
                        {
                            "node": node_id,
                            "handler": handler_name,
                            **context.resolve_line(getattr(node, "lineno", None)),
                        }
                    )
            elif call_name.endswith(".add_edge") and len(node.args) >= 2:
                source = _literal_string(node.args[0]) or _call_name(node.args[0])
                target = _literal_string(node.args[1]) or _call_name(node.args[1])
                edge_registrations.append(
                    {
                        "source": source,
                        "target": target,
                        **context.resolve_line(getattr(node, "lineno", None)),
                    }
                )
            elif call_name.endswith(".add_conditional_edges") and len(node.args) >= 3:
                source = _literal_string(node.args[0]) or _call_name(node.args[0])
                path_map = node.args[2]
                if isinstance(path_map, ast.Dict):
                    for value in path_map.values:
                        target = _literal_string(value) or _call_name(value)
                        if target:
                            edge_registrations.append(
                                {
                                    "source": source,
                                    "target": target,
                                    "conditional": True,
                                    **context.resolve_line(
                                        getattr(node, "lineno", None)
                                    ),
                                }
                            )

        issues: list[dict[str, object]] = []
        node_counts: dict[str, int] = {}
        for registration in node_registrations:
            node_id = str(registration["node"])
            node_counts[node_id] = node_counts.get(node_id, 0) + 1
        for node_id, count in sorted(node_counts.items()):
            if count > 1:
                issues.append(
                    {
                        "code": "duplicate_node_registration",
                        "message": f"Duplicate graph node registration for '{node_id}'.",
                        "node": node_id,
                        "count": count,
                    }
                )

        for function_name, occurrences in sorted(function_defs.items()):
            if len(occurrences) > 1 and (
                function_name.endswith("_node") or function_name in node_counts
            ):
                issues.append(
                    {
                        "code": "duplicate_node_function",
                        "message": f"Duplicate node function definition '{function_name}'.",
                        "function": function_name,
                        "locations": occurrences,
                    }
                )

        node_ids = set(node_counts)
        special_targets = {"START", "END", "__end__"}
        edge_pairs: dict[tuple[str, str], int] = {}
        for edge in edge_registrations:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if not source or not target:
                continue
            edge_pairs[(source, target)] = edge_pairs.get((source, target), 0) + 1
            if source == target and target not in special_targets:
                issues.append(
                    {
                        "code": "unguarded_self_loop",
                        "message": f"Unguarded self-loop '{source} -> {target}'.",
                        "source": source,
                        "target": target,
                    }
                )
            if source not in node_ids and source not in special_targets:
                issues.append(
                    {
                        "code": "unknown_edge_source",
                        "message": f"Edge source '{source}' is not a registered graph node.",
                        "source": source,
                    }
                )
            if target not in node_ids and target not in special_targets:
                issues.append(
                    {
                        "code": "unknown_edge_target",
                        "message": f"Edge target '{target}' is not a registered graph node or END.",
                        "target": target,
                    }
                )

        for (source, target), count in sorted(edge_pairs.items()):
            if count > 1:
                issues.append(
                    {
                        "code": "duplicate_edge_registration",
                        "message": f"Duplicate edge registration '{source} -> {target}'.",
                        "source": source,
                        "target": target,
                        "count": count,
                    }
                )

        if issues:
            return self.failed_report(
                "Invalid LangGraph topology detected in generated notebook code.",
                suggestions=[
                    "Generate each node function and workflow.add_node registration exactly once.",
                    "Reject graph specs with unknown edge endpoints or unguarded terminal self-loops before notebook rendering.",
                    "Ensure Mermaid/prose/code are based on the same validated graph spec.",
                ],
                evidence={
                    "issues": issues,
                    "node_registrations": node_registrations,
                    "edge_registrations": edge_registrations,
                },
            )

        return self.passed_report(
            "No duplicate node registrations, invalid endpoints, or unguarded self-loops were detected.",
            evidence={
                "node_registrations": node_registrations,
                "edge_registrations": edge_registrations,
            },
        )


class StateReducerSemanticsRule(QAValidationRule):
    """Validate state schemas preserve reducer-backed update semantics."""

    rule_id = "state_reducer_semantics"
    check_name = "State Reducer Semantics"
    category = "state"
    failure_severity = "error"
    repairable = False

    STATE_CLASS_NAMES = {"WorkflowState", "GraphState", "State"}

    def validate(self, context: NotebookValidationContext) -> Optional[QAReport]:
        tree = context.ast_tree()
        if tree is None:
            return None

        issues: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []
        state_fields: dict[str, dict[str, object]] = {}
        uses_messages_state = False

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = _class_base_names(node)
            is_state_class = (
                node.name in self.STATE_CLASS_NAMES
                or "TypedDict" in base_names
                or any(base.endswith("MessagesState") for base in base_names)
            )
            if not is_state_class:
                continue
            if any(base.endswith("MessagesState") for base in base_names):
                uses_messages_state = True
                state_fields.setdefault(
                    "messages",
                    {
                        "class": node.name,
                        "has_reducer": True,
                        "source": "MessagesState",
                    },
                )

            seen_in_class: dict[str, dict[str, object]] = {}
            for statement in node.body:
                if not isinstance(statement, ast.AnnAssign):
                    continue
                field_names = _target_names(statement.target)
                for field_name in field_names:
                    field_info = {
                        "class": node.name,
                        "field": field_name,
                        "has_reducer": _annotation_uses_annotated(statement.annotation),
                        **context.resolve_line(getattr(statement, "lineno", None)),
                    }
                    if field_name in seen_in_class:
                        issues.append(
                            {
                                "code": "duplicate_state_field",
                                "message": f"Duplicate state field '{field_name}' in {node.name}.",
                                "field": field_name,
                                "class": node.name,
                                "first": seen_in_class[field_name],
                                "duplicate": field_info,
                            }
                        )
                    seen_in_class[field_name] = field_info
                    state_fields[field_name] = field_info

        writer_map: dict[str, set[str]] = {}

        def _record_return_keys(function_name: str, value: ast.AST | None) -> None:
            if value is None:
                return
            if isinstance(value, ast.Dict):
                for key in _dict_string_keys(value):
                    writer_map.setdefault(key, set()).add(function_name)
                return
            if isinstance(value, ast.Call) and _call_name(value.func).endswith("Command"):
                for keyword in value.keywords:
                    if keyword.arg == "update" and isinstance(keyword.value, ast.Dict):
                        for key in _dict_string_keys(keyword.value):
                            writer_map.setdefault(key, set()).add(function_name)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for statement in ast.walk(node):
                if isinstance(statement, ast.Return):
                    _record_return_keys(node.name, statement.value)

        for field_name, writers in sorted(writer_map.items()):
            field = state_fields.get(field_name)
            has_reducer = bool(field and field.get("has_reducer"))
            if field_name == "messages" and uses_messages_state:
                has_reducer = True
            if field_name == "messages" and writers and not has_reducer:
                issues.append(
                    {
                        "code": "messages_missing_reducer",
                        "message": "State field 'messages' is updated by nodes but does not use add_messages or MessagesState.",
                        "field": field_name,
                        "writers": sorted(writers),
                    }
                )
            elif len(writers) > 1 and field is not None and not has_reducer:
                warnings.append(
                    {
                        "code": "multi_writer_field_without_reducer",
                        "message": f"State field '{field_name}' is updated by multiple nodes without an explicit reducer.",
                        "field": field_name,
                        "writers": sorted(writers),
                    }
                )

        if issues:
            return self.failed_report(
                "Invalid LangGraph state reducer semantics detected.",
                suggestions=[
                    "Do not emit duplicate TypedDict field annotations.",
                    "Use MessagesState or Annotated[..., add_messages] for message state.",
                    "Add reducers for state fields that can receive updates from multiple nodes.",
                ],
                evidence={
                    "issues": issues,
                    "warnings": warnings,
                    "state_fields": state_fields,
                    "writer_map": {key: sorted(value) for key, value in writer_map.items()},
                },
            )

        if warnings:
            return QAReport(
                check_name=self.check_name,
                passed=False,
                message="State reducer advisories detected.",
                rule_id=self.rule_id,
                severity="warning",
                category=self.category,
                repairable=self.repairable,
                suggestions=[
                    "Add reducers for state fields that may receive updates from multiple nodes, or document why writers are mutually exclusive.",
                ],
                evidence={
                    "warnings": warnings,
                    "state_fields": state_fields,
                    "writer_map": {key: sorted(value) for key, value in writer_map.items()},
                },
            )

        return self.passed_report(
            "State schema has no duplicate fields and message reducers are preserved.",
            evidence={
                "state_fields": state_fields,
                "writer_map": {key: sorted(value) for key, value in writer_map.items()},
            },
        )


class ToolReachabilityRule(QAValidationRule):
    """Check that generated LangChain tools are reachable and honestly described."""

    rule_id = "tool_reachability"
    check_name = "Tool Reachability"
    category = "tools"
    failure_severity = "warning"
    repairable = False

    def validate(self, context: NotebookValidationContext) -> Optional[QAReport]:
        tree = context.ast_tree()
        if tree is None:
            return None

        tool_functions: dict[str, dict[str, object]] = {}
        reachable_tools: set[str] = set()
        list_assignments: dict[str, set[str]] = {}
        advisories: list[dict[str, object]] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = {_call_name(decorator) for decorator in node.decorator_list}
                docstring = ast.get_docstring(node) or ""
                is_tool = "tool" in decorators or any(
                    decorator.endswith(".tool") for decorator in decorators
                )
                if is_tool:
                    tool_functions[node.name] = {
                        "name": node.name,
                        "docstring": docstring,
                        **context.resolve_line(getattr(node, "lineno", None)),
                    }
                    lowered_doc = docstring.lower()
                    if "placeholder" in lowered_doc or "auxiliary context lookup" in lowered_doc:
                        advisories.append(
                            {
                                "code": "placeholder_tool_description",
                                "message": f"Tool '{node.name}' is described as placeholder/fallback behavior.",
                                "tool": node.name,
                            }
                        )
                elif "placeholder tool" in docstring.lower():
                    advisories.append(
                        {
                            "code": "unmarked_placeholder_tool",
                            "message": f"Function '{node.name}' looks like a placeholder tool but is not decorated as a LangChain tool.",
                            "tool": node.name,
                        }
                    )
            elif isinstance(node, ast.Assign):
                if isinstance(node.value, ast.List):
                    names = {_call_name(element) for element in node.value.elts}
                    names = {name for name in names if name}
                    for target in node.targets:
                        for target_name in _target_names(target):
                            list_assignments[target_name] = names

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func)
            tool_args: list[ast.AST] = []
            if call_name.endswith(".bind_tools"):
                tool_args.extend(node.args[:1])
            elif call_name.endswith("create_react_agent"):
                for keyword in node.keywords:
                    if keyword.arg == "tools":
                        tool_args.append(keyword.value)
                if len(node.args) >= 2:
                    tool_args.append(node.args[1])
            for argument in tool_args:
                if isinstance(argument, ast.Name):
                    reachable_tools.update(list_assignments.get(argument.id, set()))
                elif isinstance(argument, ast.List):
                    reachable_tools.update(
                        name for name in (_call_name(element) for element in argument.elts) if name
                    )

        for tool_name in sorted(tool_functions):
            if tool_name not in reachable_tools:
                advisories.append(
                    {
                        "code": "unreachable_tool",
                        "message": f"Tool '{tool_name}' is defined but not bound or passed to a documented tool execution pattern.",
                        "tool": tool_name,
                    }
                )

        if advisories:
            return self.failed_report(
                "Tool reachability advisories detected.",
                suggestions=[
                    "Bind generated tools with model.bind_tools(...) and execute returned tool calls, or pass tools into a documented LangGraph agent/tool node.",
                    "Label placeholder tools honestly and keep broad external API tools deny-by-default.",
                ],
                evidence={
                    "advisories": advisories,
                    "tool_functions": tool_functions,
                    "reachable_tools": sorted(reachable_tools),
                },
            )

        return self.passed_report(
            "Generated tools are either absent or reachable through a documented tool pattern.",
            evidence={
                "tool_functions": tool_functions,
                "reachable_tools": sorted(reachable_tools),
            },
        )


class InvocationConfigRule(QAValidationRule):
    """Validate generated graph invocations include documented runtime config."""

    rule_id = "invocation_config"
    check_name = "Invocation Config"
    category = "docs_alignment"
    failure_severity = "error"
    repairable = True

    def validate(self, context: NotebookValidationContext) -> Optional[QAReport]:
        tree = context.ast_tree()
        if tree is None:
            return None

        config_assignments: dict[str, ast.Dict] = {}
        invocations: list[dict[str, object]] = []
        issues: list[dict[str, object]] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                for target in node.targets:
                    for name in _target_names(target):
                        config_assignments[name] = node.value

        def _config_status(config_node: ast.AST | None) -> dict[str, object]:
            if config_node is None:
                return {
                    "has_config": False,
                    "has_thread_id": False,
                    "has_recursion_limit": False,
                    "config_source": None,
                }
            source = "literal"
            resolved = config_node
            if isinstance(config_node, ast.Name):
                source = config_node.id
                resolved = config_assignments.get(config_node.id)
            if not isinstance(resolved, ast.Dict):
                return {
                    "has_config": True,
                    "has_thread_id": False,
                    "has_recursion_limit": False,
                    "config_source": source,
                    "unresolved": True,
                }
            keys = _dict_string_keys(resolved)
            configurable = _dict_value_for_key(resolved, "configurable")
            configurable_keys = _dict_string_keys(configurable) if configurable else set()
            return {
                "has_config": True,
                "has_thread_id": "thread_id" in configurable_keys,
                "has_recursion_limit": "recursion_limit" in keys,
                "config_source": source,
            }

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func)
            method = call_name.rsplit(".", 1)[-1]
            if method not in {"invoke", "stream", "get_state"}:
                continue
            target_name = call_name.rsplit(".", 1)[0]
            if target_name not in {"graph", "compiled_graph", "app"}:
                continue

            config_node: ast.AST | None = None
            for keyword in node.keywords:
                if keyword.arg == "config":
                    config_node = keyword.value
                    break
            if config_node is None:
                if method == "get_state" and node.args:
                    config_node = node.args[0]
                elif method in {"invoke", "stream"} and len(node.args) >= 2:
                    config_node = node.args[1]

            status = _config_status(config_node)
            invocation = {
                "call_name": call_name,
                "method": method,
                **status,
                **context.resolve_line(getattr(node, "lineno", None)),
            }
            invocations.append(invocation)
            if not status["has_config"]:
                issues.append(
                    {
                        "code": "missing_config",
                        "message": f"{call_name}(...) does not pass a config object.",
                        "call_name": call_name,
                    }
                )
            else:
                if not status["has_thread_id"]:
                    issues.append(
                        {
                            "code": "missing_thread_id",
                            "message": f"{call_name}(...) config does not include configurable.thread_id.",
                            "call_name": call_name,
                            "config_source": status["config_source"],
                        }
                    )
                if not status["has_recursion_limit"]:
                    issues.append(
                        {
                            "code": "missing_recursion_limit",
                            "message": f"{call_name}(...) config does not include top-level recursion_limit.",
                            "call_name": call_name,
                            "config_source": status["config_source"],
                        }
                    )

        if issues:
            return self.failed_report(
                "Graph invocation config is missing required LangGraph runtime keys.",
                suggestions=[
                    'Use config = {"configurable": {"thread_id": "lnf-demo-thread"}, "recursion_limit": 25}.',
                    "Pass the same config object to graph.invoke(...), graph.stream(...), and graph.get_state(...).",
                ],
                evidence={"issues": issues, "invocations": invocations},
            )

        return self.passed_report(
            "Graph invocation examples include configurable.thread_id and top-level recursion_limit.",
            evidence={"invocations": invocations},
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

    def disable(self, rule_id: str) -> bool:
        """Disable a validation rule by id."""

        return self._rules.pop(rule_id.strip(), None) is not None

    def get(self, rule_id: str) -> QAValidationRule:
        """Return a registered validation rule."""

        return self._rules[rule_id]

    def rule_ids(self) -> List[str]:
        """Return registered validation rule ids in execution order."""

        return list(self._rules)

    def rules(self) -> List[QAValidationRule]:
        """Return the ordered list of registered validation rules."""

        return list(self._rules.values())

    def clone(self) -> "ValidatorRegistry":
        """Return a shallow clone of the current registry."""

        return ValidatorRegistry(self.rules())


@runtime_checkable
class SupportsValidatorRegistry(Protocol):
    """Structural typing contract for objects that can provide a validator registry."""

    def validator_registry(self) -> ValidatorRegistry: ...


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

    def __init__(
        self,
        registry: ValidatorRegistry | SupportsValidatorRegistry | None = None,
    ):
        if registry is None:
            from langgraph_system_generator.qa.registry import get_qa_repair_registry

            self.registry = get_qa_repair_registry().validator_registry()
        elif isinstance(registry, ValidatorRegistry):
            self.registry = registry.clone()
        elif isinstance(registry, SupportsValidatorRegistry):
            self.registry = registry.validator_registry()
        else:
            raise TypeError(
                "NotebookValidator registry must be a ValidatorRegistry or implement "
                "validator_registry()."
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
        except (json.JSONDecodeError, nbformat.reader.NotJSONError) as exc:
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
            rule = (
                self.registry.get("required_sections")
                if required_sections is None
                else RequiredSectionsRule(required_sections)
            )
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
            rule = (
                self.registry.get("required_import_symbols")
                if required_imports is None
                else RequiredImportsRule(required_imports)
            )
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
            syntax_rule = self.registry.get("python_syntax")
            syntax_report = syntax_rule.validate(context)
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

            graph_rule = self.registry.get("graph_structure")
            graph_report = graph_rule.validate(context)
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
