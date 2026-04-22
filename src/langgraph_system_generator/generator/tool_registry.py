"""Internal registry for ToolchainEngineer canonical tool metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import importlib
from typing import Any, Iterable, Mapping

from langgraph_system_generator.generator.state import ToolSpec
from langgraph_system_generator.utils.config import settings


def _normalize_tool_id(value: str) -> str:
    """Return a normalized tool identifier."""

    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        raise ValueError("Tool registrations must include a non-empty tool_id.")
    return normalized


def _normalize_string_list(values: Iterable[str] | None) -> list[str]:
    """Return an ordered, de-duplicated list of non-empty strings."""

    normalized_values: list[str] = []
    for raw_value in values or []:
        normalized = str(raw_value or "").strip()
        if normalized and normalized not in normalized_values:
            normalized_values.append(normalized)
    return normalized_values


def _normalize_token_list(values: Iterable[str] | None) -> list[str]:
    """Return an ordered, de-duplicated list of normalized tool tokens."""

    normalized_values: list[str] = []
    for raw_value in values or []:
        normalized = _normalize_tool_id(raw_value)
        if normalized not in normalized_values:
            normalized_values.append(normalized)
    return normalized_values


def _normalize_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a shallow normalized mapping."""

    return {
        str(key).strip(): value
        for key, value in (values or {}).items()
        if str(key or "").strip()
    }


def normalize_tool_token(value: Any) -> str:
    """Return a normalized tool token suitable for registry lookups."""

    return _normalize_tool_id(str(value or ""))


@dataclass(frozen=True)
class ToolRegistration:
    """Metadata describing a canonical supported tool."""

    tool_id: str
    name: str
    description: str
    category: str
    aliases: list[str] = field(default_factory=list)
    default_packages: list[str] = field(default_factory=list)
    provider_env_vars: list[str] = field(default_factory=list)
    environment_compatibility: dict[str, Any] = field(default_factory=dict)
    fallback_configuration_defaults: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "ToolRegistration":
        """Return a normalized copy suitable for registry storage."""

        normalized_tool_id = _normalize_tool_id(self.tool_id)
        normalized_name = str(self.name or "").strip()
        normalized_description = str(self.description or "").strip()
        normalized_category = str(self.category or "").strip().lower()
        if not normalized_name:
            raise ValueError(
                f"Tool registration '{normalized_tool_id}' must include a default name."
            )
        if not normalized_description:
            raise ValueError(
                f"Tool registration '{normalized_tool_id}' must include a description."
            )
        if not normalized_category:
            raise ValueError(
                f"Tool registration '{normalized_tool_id}' must include a category."
            )

        aliases = _normalize_token_list(self.aliases)
        if normalized_tool_id not in aliases:
            aliases.insert(0, normalized_tool_id)

        return ToolRegistration(
            tool_id=normalized_tool_id,
            name=normalized_name,
            description=normalized_description,
            category=normalized_category,
            aliases=aliases,
            default_packages=_normalize_string_list(self.default_packages),
            provider_env_vars=_normalize_string_list(self.provider_env_vars),
            environment_compatibility=_normalize_mapping(self.environment_compatibility),
            fallback_configuration_defaults=dict(self.fallback_configuration_defaults or {}),
        )

    def build_tool_spec(
        self,
        *,
        purpose: str,
        configuration: Mapping[str, Any] | None = None,
        status: str = "ready",
        warnings: Iterable[str] | None = None,
        name: str | None = None,
    ) -> ToolSpec:
        """Build a normalized ToolSpec from this registration."""

        merged_configuration = dict(self.fallback_configuration_defaults)
        merged_configuration.update(dict(configuration or {}))
        return ToolSpec(
            tool_id=self.tool_id,
            name=str(name or self.name).strip() or self.name,
            category=self.category,
            purpose=str(purpose or "").strip()
            or f"Use the canonical {self.tool_id} capability.",
            configuration=merged_configuration,
            packages=list(self.default_packages),
            provider_env_vars=list(self.provider_env_vars),
            status=status,
            warnings=[warning for warning in warnings or [] if str(warning or "").strip()],
        )


class ToolRegistry:
    """Mutable in-memory registry for canonical tool metadata."""

    def __init__(self, registrations: Iterable[ToolRegistration] | None = None):
        self._registrations: dict[str, ToolRegistration] = {}
        self._aliases: dict[str, str] = {}
        for registration in registrations or []:
            self.register(registration)

    def clone(self) -> "ToolRegistry":
        """Return a shallow copy of the registry."""

        return ToolRegistry(self._registrations.values())

    def register(self, registration: ToolRegistration) -> ToolRegistration:
        """Register or replace a tool registration."""

        normalized = registration.normalized()
        stale_aliases = [
            alias
            for alias, tool_id in self._aliases.items()
            if tool_id == normalized.tool_id
        ]
        for alias in stale_aliases:
            del self._aliases[alias]

        for alias in normalized.aliases:
            existing_tool_id = self._aliases.get(alias)
            if existing_tool_id and existing_tool_id != normalized.tool_id:
                raise ValueError(
                    f"Alias '{alias}' is already registered to tool '{existing_tool_id}'."
                )

        self._registrations[normalized.tool_id] = normalized
        for alias in normalized.aliases:
            self._aliases[alias] = normalized.tool_id
        return normalized

    def get(self, tool_id: str) -> ToolRegistration:
        """Return a registered tool by canonical id."""

        return self._registrations[_normalize_tool_id(tool_id)]

    def resolve_tool_id(self, value: Any) -> str | None:
        """Resolve an arbitrary tool token or alias to a canonical tool id."""

        text = str(value or "").strip()
        if not text:
            return None
        normalized = normalize_tool_token(text)
        return self._aliases.get(normalized)

    def supported_tool_ids(self) -> list[str]:
        """Return registered canonical tool identifiers in insertion order."""

        return list(self._registrations.keys())

    def render_planning_prompt_catalog(self) -> str:
        """Render a human-readable tool catalog for the planner prompt."""

        lines: list[str] = []
        for registration in self._registrations.values():
            aliases = [
                alias for alias in registration.aliases if alias != registration.tool_id
            ]
            alias_text = f" Aliases: {', '.join(aliases)}." if aliases else ""
            lines.append(
                f"- {registration.tool_id}: {registration.description}.{alias_text}"
            )
        return "\n".join(lines)


def _default_registrations() -> list[ToolRegistration]:
    """Return the built-in tool registry entries."""

    return [
        ToolRegistration(
            tool_id="web_search",
            name="Web Docs Search",
            description="Search public web pages and documentation snippets",
            category="search",
            aliases=[
                "search",
                "web search",
                "docs_search",
                "documentation_search",
                "duckduckgo",
            ],
            default_packages=["langchain-community"],
            provider_env_vars=[],
            environment_compatibility={
                "requires_network": True,
                "public_web": True,
                "notebook_safe": True,
            },
            fallback_configuration_defaults={"backend": "duckduckgo"},
        ),
        ToolRegistration(
            tool_id="file_reader",
            name="File Reader",
            description="Read local files, documents, and PDFs",
            category="file_io",
            aliases=[
                "file",
                "document_reader",
                "pdf_reader",
                "read_file",
            ],
            default_packages=["pypdf"],
            provider_env_vars=[],
            environment_compatibility={
                "requires_network": False,
                "public_web": False,
                "notebook_safe": True,
            },
            fallback_configuration_defaults={"mode": "text"},
        ),
        ToolRegistration(
            tool_id="http_client",
            name="HTTP Client",
            description="Fetch remote HTTP and API resources",
            category="api",
            aliases=[
                "http",
                "api",
                "fetch",
                "requests",
                "webhook",
            ],
            default_packages=["requests"],
            provider_env_vars=[],
            environment_compatibility={
                "requires_network": True,
                "public_web": True,
                "notebook_safe": True,
            },
            fallback_configuration_defaults={"method": "GET"},
        ),
        ToolRegistration(
            tool_id="data_processor",
            name="Data Processor",
            description="Parse and transform structured or semi-structured data",
            category="data_processing",
            aliases=[
                "data",
                "transform",
                "parser",
                "json_parser",
                "csv_parser",
            ],
            default_packages=[],
            provider_env_vars=[],
            environment_compatibility={
                "requires_network": False,
                "public_web": False,
                "notebook_safe": True,
            },
            fallback_configuration_defaults={"format": "auto"},
        ),
        ToolRegistration(
            tool_id="schema_validator",
            name="Schema Validator",
            description="Validate records, schemas, and structured outputs",
            category="validation",
            aliases=[
                "validator",
                "validate",
                "schema",
                "schema_check",
                "checker",
            ],
            default_packages=["pydantic"],
            provider_env_vars=[],
            environment_compatibility={
                "requires_network": False,
                "public_web": False,
                "notebook_safe": True,
            },
            fallback_configuration_defaults={"strict": True},
        ),
    ]


def _normalize_plugin_modules(plugin_modules: Iterable[str] | None) -> tuple[str, ...]:
    """Return normalized plugin module paths for cache keys and loading."""

    normalized: list[str] = []
    for raw_value in plugin_modules or []:
        module_name = str(raw_value or "").strip()
        if module_name and module_name not in normalized:
            normalized.append(module_name)
    return tuple(normalized)


def _load_plugin_modules(
    registry: ToolRegistry,
    plugin_modules: tuple[str, ...],
) -> ToolRegistry:
    """Load plugin registrations into a cloned registry."""

    for module_name in plugin_modules:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise ValueError(
                f"Failed to import toolchain engineer plugin module '{module_name}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        register = getattr(module, "register_toolchain_tools", None)
        if not callable(register):
            raise ValueError(
                f"Toolchain engineer plugin module '{module_name}' must define "
                "register_toolchain_tools(registry)."
            )
        try:
            register(registry)
        except Exception as exc:
            raise ValueError(
                f"Toolchain engineer plugin module '{module_name}' failed while "
                f"running register_toolchain_tools(registry): {type(exc).__name__}: {exc}"
            ) from exc
    return registry


def get_tool_registry(plugin_modules: tuple[str, ...] | None = None) -> ToolRegistry:
    """Return the built-in tool registry with optional plugin extensions."""

    normalized_modules = _normalize_plugin_modules(
        settings.toolchain_engineer_plugin_modules
        if plugin_modules is None
        else plugin_modules
    )
    return _get_tool_registry_cached(normalized_modules)


@lru_cache(maxsize=16)
def _get_tool_registry_cached(plugin_modules: tuple[str, ...]) -> ToolRegistry:
    """Return a cached registry keyed by explicit plugin module tuples."""

    registry = ToolRegistry(_default_registrations())
    if plugin_modules:
        registry = _load_plugin_modules(registry, plugin_modules)
    return registry
