"""Tests for generator NotebookComposer."""

from __future__ import annotations

import asyncio
import ast
import re
import sys
import types

import pytest

from langgraph_system_generator.generator.agents import (
    notebook_composer as composer_module,
)
import langgraph_system_generator.generator.notebook_composer_registry as registry_module
from langgraph_system_generator.generator.notebook_composer_registry import (
    NotebookComposerArchitectureRegistration,
    get_notebook_composer_registry,
)
from langgraph_system_generator.generator.state import (
    CellSpec,
    NotebookPlan,
    ToolPlanningFeedback,
)
from langgraph_system_generator.notebook.composer import (
    NotebookComposer as NotebookFileComposer,
)
from langgraph_system_generator.qa.validators import NotebookValidator
from langgraph_system_generator.utils.config import ModelConfig


class DummyLLM:
    """Simple LLM stub to avoid API initialization."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def invoke(self, *args, **kwargs):
        """Minimal invoke stub returning an object with a `content` attribute."""

        class Response:
            def __init__(self, content: str) -> None:
                self.content = content

        content = args[0] if args and isinstance(args[0], str) else ""
        return Response(content)

    async def ainvoke(self, *args, **kwargs):
        """Async invoke stub matching the synchronous empty-response behavior."""

        return self.invoke(*args, **kwargs)


class TrackingLLM(DummyLLM):
    """Async LLM stub that records concurrency and returns meaningful code."""

    _class_delay_map: dict[str, float] = {}
    default_delay: float = 0.01
    _class_active_calls: int = 0
    _class_max_active_calls: int = 0
    _class_completed_items: list[str] = []

    @classmethod
    def reset(cls, *, delay_map: dict[str, float] | None = None) -> None:
        cls._class_delay_map = dict(delay_map or {})
        cls._class_active_calls = 0
        cls._class_max_active_calls = 0
        cls._class_completed_items = []

    async def ainvoke(self, messages, *args, **kwargs):
        user_content = getattr(messages[-1], "content", "")
        tool_match = re.search(r"Tool Name:\s*(.+)", user_content)
        node_match = re.search(r"Node Name:\s*(.+)", user_content)
        label = ""
        if tool_match:
            label = tool_match.group(1).strip()
            safe_identifier = composer_module.NotebookComposer._safe_identifier(
                label, "tool"
            )
            content = (
                f"def {safe_identifier}(query: str) -> str:\n" f"    return {label!r}"
            )
        elif node_match:
            label = node_match.group(1).strip()
            safe_identifier = composer_module.NotebookComposer._safe_identifier(
                label, "node"
            )
            content = (
                f"def {safe_identifier}_node(state: WorkflowState) -> WorkflowState:\n"
                "    updates = dict(state)\n"
                f"    updates['last_node'] = {label!r}\n"
                "    return updates"
            )
        else:
            content = ""

        type(self)._class_active_calls += 1
        type(self)._class_max_active_calls = max(
            type(self)._class_max_active_calls,
            type(self)._class_active_calls,
        )
        await asyncio.sleep(
            type(self)._class_delay_map.get(label, type(self).default_delay)
        )
        type(self)._class_completed_items.append(label)
        type(self)._class_active_calls -= 1
        return self.invoke(content)


class DelayedEmptyLLM(DummyLLM):
    """Async LLM stub that delays and forces fallback behavior."""

    _class_delay_map: dict[str, float] = {}
    default_delay: float = 0.01
    _class_active_calls: int = 0
    _class_max_active_calls: int = 0

    @classmethod
    def reset(cls, *, delay_map: dict[str, float] | None = None) -> None:
        cls._class_delay_map = dict(delay_map or {})
        cls._class_active_calls = 0
        cls._class_max_active_calls = 0

    async def ainvoke(self, messages, *args, **kwargs):
        user_content = getattr(messages[-1], "content", "")
        tool_match = re.search(r"Tool Name:\s*(.+)", user_content)
        node_match = re.search(r"Node Name:\s*(.+)", user_content)
        label = ""
        if tool_match:
            label = tool_match.group(1).strip()
        elif node_match:
            label = node_match.group(1).strip()

        type(self)._class_active_calls += 1
        type(self)._class_max_active_calls = max(
            type(self)._class_max_active_calls,
            type(self)._class_active_calls,
        )
        await asyncio.sleep(
            type(self)._class_delay_map.get(label, type(self).default_delay)
        )
        type(self)._class_active_calls -= 1
        return self.invoke("")


def test_notebook_composer_registry_includes_builtin_architectures():
    registry = get_notebook_composer_registry().clone()

    for architecture_type in [
        "router",
        "subagents",
        "hybrid",
        "autoagent",
        "critique_loop",
        "deepagents",
    ]:
        registration = registry.get(architecture_type)
        assert registration.section_overrides["nodes"].endswith("_nodes")
        assert registration.section_overrides["graph"].endswith("_graph")


def test_notebook_composer_registry_preserves_explicit_section_subset():
    registry = get_notebook_composer_registry().clone()
    registry.register(
        NotebookComposerArchitectureRegistration(
            architecture_id="focused",
            section_order=["intro", "state"],
        )
    )

    registration = registry.get("focused")
    assert registration.section_order == ["intro", "state"]


def test_state_cells_filter_pattern_base_state_fields(
    monkeypatch: pytest.MonkeyPatch,
):
    """Graph-spec state metadata should not duplicate pattern base fields."""

    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    cells = composer._create_state_cells(
        {
            "architecture_type": "router",
            "state_schema": {
                "messages": "Conversation state",
                "route": "Selected route",
                "results": "Specialist outputs",
                "final_output": "Final answer",
                "catalog_id": "Museum catalog identifier",
            },
        }
    )
    state_code = next(cell.content for cell in cells if cell.cell_type == "code")

    assert state_code.count("    messages:") == 1
    assert state_code.count("    route:") == 1
    assert state_code.count("    results:") == 1
    assert state_code.count("    final_output:") == 1
    assert "catalog_id: str  # Museum catalog identifier" in state_code


@pytest.mark.asyncio
async def test_notebook_composer_registry_plugins_can_inject_pre_section_cells(
    monkeypatch: pytest.MonkeyPatch,
):
    module_name = "tests.fake_notebook_composer_plugin"
    plugin_module = types.ModuleType(module_name)

    def register_notebook_composer_builders(registry):
        def plugin_intro_banner(_composer, _context):
            return [
                CellSpec(
                    cell_type="markdown",
                    content="> Plugin intro banner",
                    section="intro",
                )
            ]

        registry.register_builder("plugin_intro_banner", plugin_intro_banner)
        base = registry.get("router")
        registry.register(
            NotebookComposerArchitectureRegistration(
                architecture_id="router",
                section_order=base.section_order,
                section_overrides=dict(base.section_overrides),
                pre_section_hooks={
                    "intro": ["plugin_intro_banner"],
                    **base.pre_section_hooks,
                },
                post_section_hooks=base.post_section_hooks,
            )
        )

    plugin_module.register_notebook_composer_builders = (
        register_notebook_composer_builders
    )
    monkeypatch.setitem(sys.modules, module_name, plugin_module)
    monkeypatch.setattr(
        registry_module.settings,
        "notebook_composer_plugin_modules",
        [module_name],
    )
    registry_module.get_notebook_composer_registry.cache_clear()
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)

    composer = composer_module.NotebookComposer()
    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Plugin Notebook",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[],
        architecture={"architecture_type": "router", "justification": "Plugin test."},
    )

    intro_cells = [
        cell.content for cell in composition.cells if cell.section == "intro"
    ]
    assert any("Plugin intro banner" in cell for cell in intro_cells)
    registry_module.get_notebook_composer_registry.cache_clear()


@pytest.mark.asyncio
async def test_compose_notebook_emits_tool_planning_warning_cells(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Tool Planning Notes",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[],
        architecture={"architecture_type": "router", "justification": "Warning test."},
        tool_planning_feedback=ToolPlanningFeedback(
            fallback_used=True,
            fallback_reason="Tool planning used heuristic fallback inference.",
            validation_errors=["Unsupported tool suggestion 'swarm_tool'."],
            unresolved_tools=["swarm_tool"],
            environment_notes=["Blocked tool 'web_search' for an offline runtime."],
            dependency_conflicts=[
                "Kept 'pypdf' instead of 'pdfminer.six' for PDF parsing."
            ],
            available_tool_ids=["web_search"],
            warnings=["Tool planning used heuristic fallback inference."],
        ),
    )

    tool_markdown = [
        cell.content
        for cell in composition.cells
        if cell.section == "tools" and cell.cell_type == "markdown"
    ]
    assert any("Tool Planning Notes" in cell for cell in tool_markdown)
    assert any("swarm_tool" in cell for cell in tool_markdown)
    assert any("Environment notes" in cell for cell in tool_markdown)
    assert any("Dependency conflicts" in cell for cell in tool_markdown)


@pytest.mark.asyncio
async def test_compose_notebook_dependency_plan_uses_tool_packages_and_env_vars(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Dependency Plan",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[
            {
                "tool_id": "http_client",
                "name": "HTTP Client",
                "category": "api",
                "purpose": "Fetch API data",
                "configuration": {},
                "packages": ["requests", "pydantic"],
                "provider_env_vars": ["SERVICE_API_KEY"],
                "status": "ready",
                "warnings": [],
            }
        ],
        architecture={
            "architecture_type": "router",
            "justification": "Dependency test.",
        },
    )

    assert "requests" in composition.dependency_plan.packages
    assert "pydantic" in composition.dependency_plan.packages
    assert "SERVICE_API_KEY" in composition.dependency_plan.provider_env_vars


@pytest.mark.asyncio
async def test_compose_notebook_emits_deepagents_sections_and_dependency(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer(
        model_config=ModelConfig(model="gpt-5.2")
    )

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Deep Agents Notebook",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["deepagents"],
            architecture_type="deepagents",
        ),
        workflow_design={
            "architecture_type": "deepagents",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "deep_agent", "purpose": "Plan and delegate work"},
                {"name": "researcher", "purpose": "Research detailed context"},
            ],
            "graph_exports": {
                "mermaid": "flowchart TD\n    deep_agent[Deep Agent]",
                "schema": {
                    "entry_point": "deep_agent",
                    "terminal_nodes": ["deep_agent"],
                },
            },
        },
        tools=[
            {
                "tool_id": "web_search",
                "name": "Lookup Topic",
                "status": "ready",
                "packages": [],
                "provider_env_vars": [],
            },
            {
                "tool_id": "unsupported_demo",
                "name": "Unsupported Tool",
                "status": "unsupported",
                "packages": ["unsupported-package"],
                "provider_env_vars": [],
            },
        ],
        architecture={
            "architecture_type": "deepagents",
            "justification": "Explicit opt-in Deep Agents request.",
        },
    )

    code = "\n\n".join(
        cell.content for cell in composition.cells if cell.cell_type == "code"
    )
    markdown = "\n\n".join(
        cell.content for cell in composition.cells if cell.cell_type == "markdown"
    )

    assert "deepagents" not in composition.dependency_plan.packages
    assert "create_deep_agent" in code
    assert "_deterministic_deepagents_fallback" in code
    assert '"Lookup_Topic"' in code
    assert "Unsupported_Tool" not in code
    assert "tools=available_tools" in code
    assert 'workflow.add_node("deep_agent", deep_agent_node)' in code
    assert '"openai:gpt-5.2"' in code
    assert "Deep Agents Harness" in markdown
    assert "experimental" in markdown.lower()
    assert any(
        "python -m pip install deepagents" in note
        for note in composition.dependency_plan.runtime_notes
    )


@pytest.mark.asyncio
async def test_compose_notebook_sanitizes_provider_env_vars_for_config_code(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Sanitized Dependency Plan",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[
            {
                "tool_id": "http_client",
                "name": "HTTP Client",
                "category": "api",
                "purpose": "Fetch API data",
                "configuration": {
                    "provider_env_vars": ["openai-api-key", "Service API Key", "for"],
                },
                "packages": ["requests"],
                "provider_env_vars": ["123 service key"],
                "status": "ready",
                "warnings": [],
            }
        ],
        architecture={
            "architecture_type": "router",
            "justification": "Dependency sanitization test.",
        },
    )

    assert "OPENAI_API_KEY" in composition.dependency_plan.provider_env_vars
    assert "SERVICE_API_KEY" in composition.dependency_plan.provider_env_vars
    assert "ENV_123_SERVICE_KEY" in composition.dependency_plan.provider_env_vars
    assert "ENV_FOR" in composition.dependency_plan.provider_env_vars
    assert any(
        "Normalized provider env var 'openai-api-key' to 'OPENAI_API_KEY'" in note
        for note in composition.dependency_plan.runtime_notes
    )
    assert any(
        "Normalized provider env var '123 service key' to 'ENV_123_SERVICE_KEY'" in note
        for note in composition.dependency_plan.runtime_notes
    )
    assert any(
        "Normalized provider env var 'for' to 'ENV_FOR'" in note
        for note in composition.dependency_plan.runtime_notes
    )

    config_cells = [
        cell.content
        for cell in composition.cells
        if cell.section == "config"
        and cell.cell_type == "code"
        and "MODEL =" in cell.content
    ]
    assert config_cells
    assert 'OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")' in config_cells[0]
    assert (
        'ENV_123_SERVICE_KEY = os.environ.get("ENV_123_SERVICE_KEY", "")'
        in config_cells[0]
    )
    ast.parse(config_cells[0])


@pytest.mark.asyncio
async def test_custom_registry_can_override_graph_section_builder(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    registry = get_notebook_composer_registry().clone()

    def custom_graph_section(_composer, _context):
        return [
            CellSpec(
                cell_type="markdown",
                content="## Custom Graph",
                section="graph",
            ),
            CellSpec(
                cell_type="code",
                content="graph = 'custom_graph'",
                section="graph",
            ),
        ]

    registry.register_builder("custom_graph", custom_graph_section)
    router_base = registry.get("router")
    registry.register(
        NotebookComposerArchitectureRegistration(
            architecture_id="router",
            section_order=router_base.section_order,
            section_overrides={
                **router_base.section_overrides,
                "graph": "custom_graph",
            },
            pre_section_hooks=router_base.pre_section_hooks,
            post_section_hooks=router_base.post_section_hooks,
        )
    )
    composer = composer_module.NotebookComposer(registry=registry)

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Override Graph",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[],
        architecture={"architecture_type": "router", "justification": "Override test."},
    )

    graph_cells = [
        cell.content for cell in composition.cells if cell.section == "graph"
    ]
    assert "## Custom Graph" in graph_cells[0]
    assert "graph = 'custom_graph'" in graph_cells[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "architecture_type, state_marker, expected_execution_markers",
    [
        (
            "router",
            "route: str",
            ['"route": ""', '"results": {}', '"final_output": ""'],
        ),
        (
            "subagents",
            "next_agent: str",
            [
                '"next_agent": "supervisor"',
                '"instructions": ""',
                '"task_results": {}',
            ],
        ),
        (
            "critique_loop",
            "revision_count: int",
            ['"revision_count": 0', '"quality_score": 0.0', '"approved": False'],
        ),
        (
            "hybrid",
            "next_agent: str",
            [
                '"route": ""',
                '"next_agent": "supervisor"',
                '"task_results": {}',
            ],
        ),
    ],
)
async def test_compose_notebook_sections_and_packages(
    monkeypatch: pytest.MonkeyPatch,
    architecture_type: str,
    state_marker: str,
    expected_execution_markers: list[str],
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)

    composer = composer_module.NotebookComposer()

    plan = NotebookPlan(
        title="Test Workflow Notebook",
        sections=["Installation", "Workflow", "Execution"],
        patterns_used=[architecture_type],
        architecture_type=architecture_type,
    )

    if architecture_type == "router":
        nodes = [
            {"name": "router", "purpose": "Route requests"},
            {"name": "search", "purpose": "Search documents"},
        ]
    elif architecture_type == "subagents":
        nodes = [
            {"name": "supervisor", "purpose": "Coordinate agents"},
            {"name": "researcher", "purpose": "Research documents"},
        ]
    elif architecture_type == "hybrid":
        nodes = [
            {"name": "router", "purpose": "Route requests"},
            {"name": "specialist_1", "purpose": "Handle direct specialist work"},
            {"name": "supervisor", "purpose": "Coordinate worker team"},
            {"name": "researcher", "purpose": "Research documents"},
            {"name": "reviewer", "purpose": "Review worker output"},
        ]
    else:
        nodes = [
            {"name": "generate", "purpose": "Generate an initial draft"},
            {"name": "critique", "purpose": "Critique the current draft"},
            {"name": "revise", "purpose": "Revise the draft using feedback"},
        ]

    workflow_design = {
        "architecture_type": architecture_type,
        "state_schema": {"user_input": "User question"},
        "nodes": nodes,
    }

    tools = [
        {
            "name": "File Reader",
            "purpose": "Read documents",
            "category": "file",
        }
    ]

    architecture = {
        "architecture_type": architecture_type,
        "justification": "Matches the workflow requirements.",
    }

    composition = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design=workflow_design,
        tools=tools,
        architecture=architecture,
    )
    cells = composition.cells

    intro_cells = [cell for cell in cells if cell.section == "intro"]
    assert len(intro_cells) >= 2

    title_cell = intro_cells[0]
    assert title_cell.cell_type == "markdown"
    assert plan.title in title_cell.content
    assert plan.architecture_type in title_cell.content

    overview_cell = intro_cells[1]
    assert overview_cell.cell_type == "markdown"
    for section in plan.sections:
        assert section in overview_cell.content

    install_cells = [
        cell
        for cell in cells
        if cell.section == "setup"
        and cell.cell_type == "code"
        and "missing_packages" in cell.content
    ]
    assert install_cells
    assert "pypdf" in install_cells[0].content
    assert "subprocess.check_call" in install_cells[0].content

    config_cells = [
        cell
        for cell in cells
        if cell.section == "config"
        and cell.cell_type == "code"
        and "MODEL =" in cell.content
    ]
    assert config_cells
    assert (
        'OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")'
        in config_cells[0].content
    )
    assert "ANTHROPIC_API_KEY" not in config_cells[0].content
    assert "MAX_ITERATIONS = 10" in config_cells[0].content

    state_cells = [
        cell for cell in cells if cell.section == "state" and cell.cell_type == "code"
    ]
    assert state_cells
    assert state_marker in state_cells[0].content

    tool_cells = [
        cell for cell in cells if cell.section == "tools" and cell.cell_type == "code"
    ]
    assert tool_cells
    assert tool_cells[0].content.startswith(
        "# WARNING: Deterministic fallback generated"
    )
    assert "def File_Reader" in tool_cells[0].content
    assert "Path(" in tool_cells[0].content
    assert "pass" not in tool_cells[0].content
    assert "TODO" not in tool_cells[0].content

    graph_cells = [
        cell for cell in cells if cell.section == "graph" and cell.cell_type == "code"
    ]
    assert graph_cells
    assert "StateGraph" in graph_cells[0].content
    assert "add_node" in graph_cells[0].content
    assert "compile" in graph_cells[0].content

    execution_cells = [
        cell
        for cell in cells
        if cell.section == "execution" and cell.cell_type == "code"
    ]
    assert execution_cells
    execution_cell = execution_cells[0]
    assert "stream" in execution_cell.content or "invoke" in execution_cell.content
    for marker in expected_execution_markers:
        assert marker in execution_cell.content

    if architecture_type == "hybrid":
        assert "route: str" in state_cells[0].content
        assert 'workflow.add_node("router", router_node)' in graph_cells[0].content
        assert (
            'workflow.add_node("supervisor", supervisor_node)' in graph_cells[0].content
        )
        assert 'workflow.add_edge("specialist_1", "finish")' in graph_cells[0].content
        node_source = "\n\n".join(
            cell.content for cell in cells if cell.section == "nodes"
        )
        assert "def router_node" in node_source
        assert "def supervisor_node" in node_source
        assert "def reviewer_node" in node_source

    assert composition.feedback.fallback_used is True
    assert composition.feedback.resolved_model
    assert composition.feedback.fallback_events[0].kind == "tool"
    assert composition.feedback.fallback_events[0].item_name == "File Reader"
    assert composition.feedback.sections_built == [
        "intro",
        "install",
        "config",
        "state",
        "tools",
        "nodes",
        "graph",
        "execution",
    ]
    assert "langgraph" in composition.dependency_plan.packages
    assert "langchain-openai" in composition.dependency_plan.packages
    assert "deepagents" not in composition.dependency_plan.packages
    assert "OPENAI_API_KEY" in composition.dependency_plan.provider_env_vars

    sections = {cell.section for cell in cells}
    assert {
        "intro",
        "setup",
        "config",
        "state",
        "tools",
        "graph",
        "execution",
    }.issubset(sections)

    section_order = [cell.section for cell in cells if cell.section]
    expected_order = [
        "intro",
        "setup",
        "config",
        "state",
        "tools",
        "nodes",
        "graph",
        "execution",
    ]
    unique_sections: list[str] = []
    for section in section_order:
        if section not in unique_sections:
            unique_sections.append(section)

    expected_positions = {s: i for i, s in enumerate(expected_order)}
    unexpected_sections = [s for s in unique_sections if s not in expected_positions]
    assert not unexpected_sections

    prev_expected_pos = -1
    for section in unique_sections:
        current_expected_pos = expected_positions[section]
        assert current_expected_pos > prev_expected_pos
        prev_expected_pos = current_expected_pos


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "architecture_type,nodes",
    [
        (
            "router",
            [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        ),
        (
            "subagents",
            [
                {"name": "supervisor", "purpose": "Coordinate agents"},
                {"name": "researcher", "purpose": "Research documents"},
            ],
        ),
        (
            "hybrid",
            [
                {"name": "router", "purpose": "Route requests"},
                {"name": "specialist_1", "purpose": "Handle direct specialist work"},
                {"name": "supervisor", "purpose": "Coordinate worker team"},
                {"name": "researcher", "purpose": "Research documents"},
            ],
        ),
        (
            "autoagent",
            [{"name": "planner", "purpose": "Plan the work"}],
        ),
        (
            "deepagents",
            [{"name": "researcher", "purpose": "Research documents"}],
        ),
    ],
)
async def test_pattern_notebooks_have_no_scaffold_created_app_advisory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    architecture_type: str,
    nodes: list[dict[str, str]],
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title=f"{architecture_type} Workflow Notebook",
            sections=["Installation", "Configuration", "Workflow", "Execution"],
            patterns_used=[architecture_type],
            architecture_type=architecture_type,
        ),
        workflow_design={
            "architecture_type": architecture_type,
            "state_schema": {"user_input": "User question"},
            "nodes": nodes,
        },
        tools=[],
        architecture={
            "architecture_type": architecture_type,
            "justification": "Matches the workflow requirements.",
        },
    )

    notebook = NotebookFileComposer().build_notebook(
        composition.cells,
        ensure_minimum_sections=True,
    )
    notebook_path = tmp_path / f"{architecture_type}.ipynb"
    NotebookFileComposer().write(notebook, notebook_path)

    reports = NotebookValidator().validate_all(notebook_path)
    failed_undefined_names = [
        report
        for report in reports
        if report.rule_id == "undefined_names" and not report.passed
    ]

    assert failed_undefined_names == []


@pytest.mark.asyncio
async def test_compose_notebook_parallel_tool_generation_preserves_order_and_cap(
    monkeypatch: pytest.MonkeyPatch,
):
    TrackingLLM.reset(
        delay_map={
            "Tool Alpha": 0.04,
            "Tool Beta": 0.01,
            "Tool Gamma": 0.02,
        }
    )
    monkeypatch.setattr(composer_module, "ChatOpenAI", TrackingLLM)
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_parallelism_mode",
        "parallel",
    )
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_max_concurrency",
        2,
    )
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Parallel Tools",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[
            {"name": "Tool Alpha", "purpose": "First tool", "category": "misc"},
            {"name": "Tool Beta", "purpose": "Second tool", "category": "misc"},
            {"name": "Tool Gamma", "purpose": "Third tool", "category": "misc"},
        ],
        architecture={
            "architecture_type": "router",
            "justification": "Parallel tools.",
        },
    )

    tool_cells = [
        cell.content
        for cell in composition.cells
        if cell.section == "tools" and cell.cell_type == "code"
    ]
    assert "def Tool_Alpha" in tool_cells[0]
    assert "def Tool_Beta" in tool_cells[1]
    assert "def Tool_Gamma" in tool_cells[2]
    assert TrackingLLM._class_max_active_calls == 2
    assert composition.feedback.fallback_used is False


@pytest.mark.asyncio
async def test_compose_notebook_parallel_tool_fallback_metadata_preserves_input_order(
    monkeypatch: pytest.MonkeyPatch,
):
    DelayedEmptyLLM.reset(
        delay_map={
            "Tool Alpha": 0.04,
            "Tool Beta": 0.01,
            "Tool Gamma": 0.02,
        }
    )
    monkeypatch.setattr(composer_module, "ChatOpenAI", DelayedEmptyLLM)
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_parallelism_mode",
        "parallel",
    )
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_max_concurrency",
        2,
    )
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Parallel Tool Fallback Order",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[
            {"name": "Tool Alpha", "purpose": "First tool", "category": "misc"},
            {"name": "Tool Beta", "purpose": "Second tool", "category": "misc"},
            {"name": "Tool Gamma", "purpose": "Third tool", "category": "misc"},
        ],
        architecture={
            "architecture_type": "router",
            "justification": "Parallel tools.",
        },
    )

    assert [event.item_name for event in composition.feedback.fallback_events] == [
        "Tool Alpha",
        "Tool Beta",
        "Tool Gamma",
    ]
    assert composition.feedback.warnings == [
        'Deterministic fallback used for tool "Tool Alpha".',
        'Deterministic fallback used for tool "Tool Beta".',
        'Deterministic fallback used for tool "Tool Gamma".',
    ]


@pytest.mark.asyncio
async def test_compose_notebook_parallel_custom_node_generation_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
):
    TrackingLLM.reset(
        delay_map={
            "enrich": 0.04,
            "summarize": 0.01,
            "finalize": 0.02,
        }
    )
    monkeypatch.setattr(composer_module, "ChatOpenAI", TrackingLLM)
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_parallelism_mode",
        "parallel",
    )
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_max_concurrency",
        2,
    )
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Parallel Nodes",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["custom"],
            architecture_type="custom",
        ),
        workflow_design={
            "architecture_type": "custom",
            "state_schema": {"last_node": "Last processed node"},
            "nodes": [
                {"name": "enrich", "purpose": "Enrich results"},
                {"name": "summarize", "purpose": "Summarize results"},
                {"name": "finalize", "purpose": "Finalize results"},
            ],
        },
        tools=[],
        architecture={
            "architecture_type": "custom",
            "justification": "Parallel nodes.",
        },
    )

    node_cells = [
        cell.content
        for cell in composition.cells
        if cell.section == "nodes" and cell.cell_type == "code"
    ]
    assert "def enrich_node" in node_cells[0]
    assert "def summarize_node" in node_cells[1]
    assert "def finalize_node" in node_cells[2]
    assert TrackingLLM._class_max_active_calls == 2
    assert composition.feedback.fallback_used is False


@pytest.mark.asyncio
async def test_compose_notebook_parallel_node_fallback_metadata_preserves_input_order(
    monkeypatch: pytest.MonkeyPatch,
):
    DelayedEmptyLLM.reset(
        delay_map={
            "enrich": 0.04,
            "summarize": 0.01,
            "finalize": 0.02,
        }
    )
    monkeypatch.setattr(composer_module, "ChatOpenAI", DelayedEmptyLLM)
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_parallelism_mode",
        "parallel",
    )
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_max_concurrency",
        2,
    )
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Parallel Node Fallback Order",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["custom"],
            architecture_type="custom",
        ),
        workflow_design={
            "architecture_type": "custom",
            "state_schema": {"last_node": "Last processed node"},
            "nodes": [
                {"name": "enrich", "purpose": "Enrich results"},
                {"name": "summarize", "purpose": "Summarize results"},
                {"name": "finalize", "purpose": "Finalize results"},
            ],
        },
        tools=[],
        architecture={
            "architecture_type": "custom",
            "justification": "Parallel nodes.",
        },
    )

    assert [event.item_name for event in composition.feedback.fallback_events] == [
        "enrich",
        "summarize",
        "finalize",
    ]
    assert composition.feedback.warnings == [
        'Deterministic fallback used for node "enrich".',
        'Deterministic fallback used for node "summarize".',
        'Deterministic fallback used for node "finalize".',
    ]


@pytest.mark.asyncio
async def test_compose_notebook_sequential_mode_serializes_llm_generation(
    monkeypatch: pytest.MonkeyPatch,
):
    TrackingLLM.reset(
        delay_map={
            "Tool One": 0.01,
            "Tool Two": 0.01,
            "Tool Three": 0.01,
        }
    )
    monkeypatch.setattr(composer_module, "ChatOpenAI", TrackingLLM)
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_parallelism_mode",
        "sequential",
    )
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_max_concurrency",
        3,
    )
    composer = composer_module.NotebookComposer()

    await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Sequential Tools",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[
            {"name": "Tool One", "purpose": "First tool", "category": "misc"},
            {"name": "Tool Two", "purpose": "Second tool", "category": "misc"},
            {"name": "Tool Three", "purpose": "Third tool", "category": "misc"},
        ],
        architecture={
            "architecture_type": "router",
            "justification": "Sequential tools.",
        },
    )

    assert TrackingLLM._class_max_active_calls == 1


@pytest.mark.asyncio
async def test_compose_notebook_parallel_mode_treats_zero_concurrency_as_one(
    monkeypatch: pytest.MonkeyPatch,
):
    TrackingLLM.reset(
        delay_map={
            "Tool One": 0.01,
            "Tool Two": 0.01,
        }
    )
    monkeypatch.setattr(composer_module, "ChatOpenAI", TrackingLLM)
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_parallelism_mode",
        "parallel",
    )
    monkeypatch.setattr(
        composer_module.settings,
        "notebook_composer_max_concurrency",
        0,
    )
    composer = composer_module.NotebookComposer()

    await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Zero Concurrency Tools",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[
            {"name": "Tool One", "purpose": "First tool", "category": "misc"},
            {"name": "Tool Two", "purpose": "Second tool", "category": "misc"},
        ],
        architecture={
            "architecture_type": "router",
            "justification": "Zero concurrency.",
        },
    )

    assert TrackingLLM._class_max_active_calls == 1


@pytest.mark.asyncio
async def test_compose_notebook_hybrid_sparse_nodes_keep_defaults_aligned(
    monkeypatch: pytest.MonkeyPatch,
):
    """Sparse hybrid designs should emit matching fallback nodes and graph wiring."""

    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    plan = NotebookPlan(
        title="Sparse Hybrid",
        sections=["Setup", "Workflow", "Execution"],
        patterns_used=["hybrid"],
        architecture_type="hybrid",
    )
    workflow_design = {
        "architecture_type": "hybrid",
        "state_schema": {},
        "nodes": [
            {"name": "router", "purpose": "Route requests"},
            {"name": "supervisor", "purpose": "Coordinate workers"},
        ],
    }

    composition = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design=workflow_design,
        tools=[],
        architecture={
            "architecture_type": "hybrid",
            "justification": "Fallback hybrid.",
        },
    )
    cells = composition.cells

    node_source = "\n\n".join(cell.content for cell in cells if cell.section == "nodes")
    graph_code = next(
        cell.content
        for cell in cells
        if cell.section == "graph" and cell.cell_type == "code"
    )

    assert "def specialist_1_node" in node_source
    assert "def researcher_node" in node_source
    assert "def reviewer_node" in node_source
    assert 'workflow.add_node("specialist_1", specialist_1_node)' in graph_code
    assert 'workflow.add_node("researcher", researcher_node)' in graph_code
    assert 'workflow.add_node("reviewer", reviewer_node)' in graph_code
    assert 'workflow.add_edge("specialist_1", "finish")' in graph_code


@pytest.mark.asyncio
async def test_compose_notebook_normalizes_mixed_case_architecture_type(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    composition = await composer.compose_notebook(
        notebook_plan=NotebookPlan(
            title="Mixed Case Router",
            sections=["Setup", "Workflow", "Execution"],
            patterns_used=["router"],
            architecture_type="router",
        ),
        workflow_design={
            "architecture_type": "Router",
            "state_schema": {"messages": "Conversation state"},
            "nodes": [
                {"name": "router", "purpose": "Route requests"},
                {"name": "search", "purpose": "Search documents"},
            ],
        },
        tools=[],
        architecture={
            "architecture_type": "Router",
            "justification": "Mixed case input.",
        },
    )

    state_code = next(
        cell.content
        for cell in composition.cells
        if cell.section == "state" and cell.cell_type == "code"
    )
    execution_code = next(
        cell.content
        for cell in composition.cells
        if cell.section == "execution" and cell.cell_type == "code"
    )

    assert "route: str" in state_code
    assert '"route": ""' in execution_code
    assert '"results": {}' in execution_code
    assert '"final_output": ""' in execution_code


@pytest.mark.asyncio
async def test_compose_notebook_hybrid_sanitizes_worker_and_specialist_graph_ids(
    monkeypatch: pytest.MonkeyPatch,
):
    """Hybrid graph wiring should use sanitized node ids for direct and worker paths."""

    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    plan = NotebookPlan(
        title="Hybrid Sanitization",
        sections=["Setup", "Workflow", "Execution"],
        patterns_used=["hybrid"],
        architecture_type="hybrid",
    )
    workflow_design = {
        "architecture_type": "hybrid",
        "state_schema": {},
        "nodes": [
            {"name": "router", "purpose": "Route requests"},
            {"name": "supervisor", "purpose": "Coordinate workers"},
            {"name": "fact checker", "purpose": "Handle direct fact checking"},
            {"name": "review lead", "purpose": "Review worker output"},
            {"name": "research analyst", "purpose": "Gather supporting facts"},
        ],
    }

    composition = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design=workflow_design,
        tools=[],
        architecture={
            "architecture_type": "hybrid",
            "justification": "Hybrid sanitization.",
        },
    )
    cells = composition.cells

    node_source = "\n\n".join(cell.content for cell in cells if cell.section == "nodes")
    graph_code = next(
        cell.content
        for cell in cells
        if cell.section == "graph" and cell.cell_type == "code"
    )

    assert "def fact_checker_node" in node_source
    assert "def review_lead_node" in node_source
    assert "def research_analyst_node" in node_source
    assert 'workflow.add_node("fact_checker", fact_checker_node)' in graph_code
    assert 'workflow.add_node("review_lead", review_lead_node)' in graph_code
    assert 'workflow.add_node("research_analyst", research_analyst_node)' in graph_code
    assert '"fact checker": "fact_checker"' in graph_code


@pytest.mark.asyncio
async def test_compose_notebook_includes_graph_overview_from_exports(
    monkeypatch: pytest.MonkeyPatch,
):
    """Graph exports should appear in the intro section as notebook-facing context."""

    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    plan = NotebookPlan(
        title="Graph Overview Notebook",
        sections=["Setup", "Workflow", "Execution"],
        patterns_used=["router"],
        architecture_type="router",
    )
    workflow_design = {
        "architecture_type": "router",
        "state_schema": {"messages": "Conversation state"},
        "nodes": [
            {"name": "router", "purpose": "Route requests"},
            {"name": "search", "purpose": "Search documents"},
        ],
        "graph_exports": {
            "mermaid": "flowchart TD\n    START --> router\n    router --> search",
            "schema": {
                "entry_point": "router",
                "terminal_nodes": ["search"],
                "validation_summary": {"errors": [], "warnings": []},
            },
        },
    }

    composition = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design=workflow_design,
        tools=[],
        architecture={
            "architecture_type": "router",
            "justification": "Router is sufficient.",
        },
    )
    cells = composition.cells

    intro_markdown = "\n\n".join(
        cell.content
        for cell in cells
        if cell.section == "intro" and cell.cell_type == "markdown"
    )

    assert "Graph Overview" in intro_markdown
    assert "```mermaid" in intro_markdown
    assert "flowchart TD" in intro_markdown
    assert "terminal_nodes" in intro_markdown


@pytest.mark.asyncio
async def test_generate_node_implementation_falls_back_to_meaningful_state_updates(
    monkeypatch: pytest.MonkeyPatch,
):
    """Custom architectures should fall back to runnable node code."""
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    node_code = await composer._generate_node_implementation(
        {"name": "enrich", "purpose": "Enrich the current workflow results"},
        {
            "architecture_type": "custom",
            "state_schema": {"results": "Collected outputs"},
            "nodes": [
                {"name": "enrich", "purpose": "Enrich the current workflow results"}
            ],
        },
    )

    assert "def enrich_node" in node_code
    assert 'updates["messages"]' in node_code
    assert 'updates["results"]' in node_code
    assert "return updates" in node_code
    assert "return state" not in node_code
    assert "pass" not in node_code
    assert "TODO" not in node_code


@pytest.mark.asyncio
async def test_generate_tool_implementation_records_visible_fallback_warning(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()
    feedback = composer_module.NotebookCompositionFeedback()

    fallback_code = await composer._generate_tool_implementation(
        {
            "name": "Example Tool",
            "purpose": "Fallback to a deterministic helper",
            "category": "misc",
        },
        feedback=feedback,
    )

    assert fallback_code.startswith("# WARNING: Deterministic fallback generated")
    assert feedback.fallback_used is True
    assert feedback.fallback_events[0].kind == "tool"


@pytest.mark.asyncio
async def test_generate_node_implementation_records_visible_fallback_warning(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()
    feedback = composer_module.NotebookCompositionFeedback()

    fallback_code = await composer._generate_node_implementation(
        {"name": "enrich", "purpose": "Enrich the current workflow results"},
        {
            "architecture_type": "custom",
            "state_schema": {"results": "Collected outputs"},
            "nodes": [
                {"name": "enrich", "purpose": "Enrich the current workflow results"}
            ],
        },
        feedback=feedback,
    )

    assert fallback_code.startswith("# WARNING: Deterministic fallback generated")
    assert feedback.fallback_used is True
    assert feedback.fallback_events[0].kind == "node"


def test_tool_fallback_sanitizes_identifier_and_compiles(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    fallback_code = composer._generate_tool_fallback(
        {
            "name": '9 bad tool";\nprint("oops")',
            "purpose": 'Line 1\n"""\nprint("owned")',
            "category": 'api"\n# injected',
        }
    )

    assert "def _9_bad_tool_print_oops" in fallback_code
    assert '# Tool: 9 bad tool"; print("oops")' in fallback_code
    assert '9 bad tool";\nprint("oops")' not in fallback_code
    assert '"category": "api\\" # injected"' in fallback_code
    assert fallback_code.splitlines()[0].startswith(
        "# WARNING: Deterministic fallback generated"
    )
    compile(fallback_code, "<tool_fallback>", "exec")
    parsed = ast.parse(fallback_code)
    assert len(parsed.body) == 1
    assert isinstance(parsed.body[0], ast.FunctionDef)


def test_node_fallback_sanitizes_identifier_and_compiles(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    fallback_code = composer._generate_node_fallback(
        {
            "name": '9 node name";\nraise SystemExit',
            "purpose": 'Node purpose\n"""\nraise RuntimeError("boom")',
        },
        {},
    )

    assert "def _9_node_name_raise_SystemExit_node" in fallback_code
    assert '9 node name";\nraise SystemExit' not in fallback_code
    assert '\\"\\"\\"' in fallback_code
    compile(fallback_code, "<node_fallback>", "exec")
    parsed = ast.parse(fallback_code)
    assert len(parsed.body) == 1
    assert isinstance(parsed.body[0], ast.FunctionDef)


def test_graph_fallback_uses_sanitized_function_references(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer()

    graph_code = composer._generate_graph_fallback(
        {
            "entry_point": "start node",
            "nodes": [
                {"name": "start node"},
                {"name": "9 result-node"},
            ],
            "edges": [{"from": "start node", "to": "9 result-node"}],
        }
    )

    assert 'workflow.add_node("start node", start_node_node)' in graph_code
    assert 'workflow.add_node("9 result-node", _9_result_node_node)' in graph_code
    compile(graph_code, "<graph_fallback>", "exec")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "architecture_type",
    ["router", "subagents", "critique_loop", "autoagent", "hybrid"],
)
async def test_pattern_nodes_use_request_scoped_model_config(
    monkeypatch: pytest.MonkeyPatch,
    architecture_type: str,
):
    monkeypatch.setattr(composer_module, "ChatOpenAI", DummyLLM)
    composer = composer_module.NotebookComposer(
        model_config=ModelConfig(
            model="gpt-5.2",
            temperature=0.3,
            api_base="https://example.test/v1",
            max_tokens=2048,
        )
    )

    plan = NotebookPlan(
        title="Configured Workflow Notebook",
        sections=["Installation", "Workflow", "Execution"],
        patterns_used=[architecture_type],
        architecture_type=architecture_type,
    )

    if architecture_type == "router":
        nodes = [
            {"name": "router", "purpose": "Route requests"},
            {"name": "search", "purpose": "Search documents"},
        ]
    elif architecture_type == "subagents":
        nodes = [
            {"name": "supervisor", "purpose": "Coordinate agents"},
            {"name": "researcher", "purpose": "Research documents"},
        ]
    elif architecture_type == "autoagent":
        nodes = [{"name": "planner", "purpose": "Plan the work"}]
    elif architecture_type == "hybrid":
        nodes = [
            {"name": "router", "purpose": "Route requests"},
            {"name": "specialist_1", "purpose": "Handle direct specialist work"},
            {"name": "supervisor", "purpose": "Coordinate worker team"},
            {"name": "researcher", "purpose": "Research documents"},
            {"name": "reviewer", "purpose": "Review worker output"},
        ]
    else:
        nodes = [
            {"name": "generate", "purpose": "Generate an initial draft"},
            {"name": "critique", "purpose": "Critique the current draft"},
            {"name": "revise", "purpose": "Revise the draft using feedback"},
        ]

    composition = await composer.compose_notebook(
        notebook_plan=plan,
        workflow_design={
            "architecture_type": architecture_type,
            "state_schema": {"user_input": "User question"},
            "nodes": nodes,
        },
        tools=[],
        architecture={
            "architecture_type": architecture_type,
            "justification": "Matches the workflow requirements.",
        },
    )
    cells = composition.cells

    node_cells = [cell for cell in cells if cell.section == "nodes"]
    assert node_cells
    assert any(
        "ChatOpenAI(model='gpt-5.2', temperature=0.3, base_url='https://example.test/v1', max_tokens=2048)"
        in cell.content
        for cell in node_cells
    )

    config_code_cells = [
        cell for cell in cells if cell.section == "config" and cell.cell_type == "code"
    ]
    assert any('MODEL = "gpt-5.2"' in cell.content for cell in config_code_cells)
    assert any("TEMPERATURE = 0.3" in cell.content for cell in config_code_cells)
    assert any(
        'API_BASE = "https://example.test/v1"' in cell.content
        for cell in config_code_cells
    )
    assert any("MAX_TOKENS = 2048" in cell.content for cell in config_code_cells)
    assert composition.feedback.resolved_model == "gpt-5.2"
    assert composition.feedback.resolved_api_base == "https://example.test/v1"
