"""Command-line interface for LangGraph Notebook Foundry.

Provides lightweight commands to generate notebook artifacts (stub by default)
and to build the documentation index from cached docs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, TypedDict
from urllib.parse import urlparse

from langgraph_system_generator.generator.state import CellSpec, Constraint, NotebookPlan
from langgraph_system_generator.utils.generation_options import (
    SUPPORTED_AGENT_TYPES,
    SUPPORTED_OPENAI_MODELS,
    normalize_agent_type,
    normalize_optional_string,
)
from langgraph_system_generator.utils.config import GenerationConfig, settings
from langgraph_system_generator.utils.optional_deps import (
    OptionalDependencyError,
    require_optional_module,
)

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = (BASE_DIR / "data" / "cached_docs").resolve()
DEFAULT_EXPORT_FORMATS = ("ipynb", "html", "markdown", "docx", "zip")
GenerationMode = Literal["stub", "live"]


class GenerationArtifacts(TypedDict):
    """Serialized generation results written by the CLI/API."""

    mode: GenerationMode
    prompt: str
    manifest: Dict[str, Any]
    manifest_path: str
    output_dir: str
    result: Dict[str, Any]


def _default_state(
    prompt: str,
    generation_config: GenerationConfig | None = None,
) -> Dict[str, Any]:
    """Return a baseline GeneratorState payload."""

    return {
        "user_prompt": prompt,
        "uploaded_files": None,
        "constraints": [],
        "selected_patterns": {},
        "docs_context": [],
        "notebook_plan": None,
        "architecture_justification": "",
        "architecture_type": None,
        "workflow_design": None,
        "tools_plan": None,
        "generated_cells": [],
        "qa_reports": [],
        "repair_attempts": 0,
        "artifacts_manifest": {},
        "generation_complete": False,
        "error_message": None,
        "generation_config": generation_config,
    }


def _serialize(obj: Any) -> Any:
    """Recursively convert Pydantic models and objects into plain dicts/lists."""

    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _serialize(val) for key, val in obj.items()}
    return obj


def _validate_generation_options(
    *,
    mode: GenerationMode,
    model: str | None,
    custom_endpoint: str | None,
    agent_type: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Validate advanced options and normalize key string fields.

    Args:
        mode: Generation mode used to determine whether live-only checks apply.
        model: Requested model override.
        custom_endpoint: Requested OpenAI-compatible base URL override.
        agent_type: Requested architecture override.

    Returns:
        tuple[str | None, str | None, str | None]:
            (normalized_model, normalized_custom_endpoint, normalized_agent_type)
    """

    normalized_model = normalize_optional_string(model)
    normalized_custom_endpoint = normalize_optional_string(custom_endpoint)
    normalized_agent_type = normalize_agent_type(agent_type)

    if normalized_agent_type and normalized_agent_type not in SUPPORTED_AGENT_TYPES:
        supported = ", ".join(sorted(SUPPORTED_AGENT_TYPES))
        raise ValueError(f"Unsupported agent_type. Supported values are: {supported}.")

    if mode == "live":
        if normalized_custom_endpoint and normalized_model in (None, "custom"):
            raise ValueError(
                "custom_endpoint requires an explicit OpenAI-compatible model identifier."
            )

        if normalized_custom_endpoint:
            parsed_endpoint = urlparse(normalized_custom_endpoint)
            if parsed_endpoint.scheme not in {"http", "https"} or not parsed_endpoint.hostname:
                raise ValueError(
                    "custom_endpoint must be a valid http or https URL with a hostname."
                )

        if normalized_model == "custom":
            raise ValueError(
                "Provide an explicit model identifier instead of the placeholder value 'custom'."
            )

        if (
            normalized_model
            and not normalized_custom_endpoint
            and normalized_model not in SUPPORTED_OPENAI_MODELS
        ):
            raise ValueError(
                "Unsupported model for the built-in provider. Choose an OpenAI-compatible model "
                "or set custom_endpoint with an explicit model identifier."
            )

    return normalized_model, normalized_custom_endpoint, normalized_agent_type


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _infer_stub_architecture(prompt: str) -> tuple[str, str]:
    """Lightweight heuristic to pick an architecture in stub mode."""

    text = prompt.lower()
    if any(keyword in text for keyword in ["delegate", "supervisor", "team", "subagent"]):
        return (
            "subagents",
            "Subagents pattern selected based on collaborative/delegation cues in the prompt.",
        )
    if any(keyword in text for keyword in ["hybrid", "combined", "mix", "multi-stage"]):
        return (
            "hybrid",
            "Hybrid pattern selected for mixed or multi-stage requirements detected in the prompt.",
        )
    if any(keyword in text for keyword in ["router", "route", "triage", "dispatch", "classification"]):
        return (
            "router",
            "Router pattern selected for routing/triage style requests in the prompt.",
        )
    return ("router", "Router pattern selected as a sensible default for general workflows.")


def _load_patterns() -> tuple[Any, Any]:
    """Import pattern generators lazily to preserve minimal installs."""

    patterns_module = require_optional_module(
        "langgraph_system_generator.patterns",
        feature="Stub artifact generation",
        extra="full",
    )
    return patterns_module.RouterPattern, patterns_module.SubagentsPattern


def _load_generator_graph() -> Any:
    """Import the live generator graph lazily."""

    graph_module = require_optional_module(
        "langgraph_system_generator.generator.graph",
        feature="Live generation",
        extra="full",
    )
    return graph_module.create_generator_graph


def _build_stub_result(prompt: str, agent_type: str | None = None) -> Dict[str, Any]:
    """Create a deterministic, offline-friendly generation result."""

    RouterPattern, SubagentsPattern = _load_patterns()
    normalized_agent_type = normalize_agent_type(agent_type)
    if normalized_agent_type in SUPPORTED_AGENT_TYPES:
        architecture_type = normalized_agent_type
        justification = (
            f"{normalized_agent_type.title()} pattern selected from the requested "
            "agent_type override."
        )
    else:
        architecture_type, justification = _infer_stub_architecture(prompt)

    constraints = [
        Constraint(type="goal", value=f"Deliver a notebook for: {prompt}", priority=5),
        Constraint(
            type="environment",
            value="Designed to run in Jupyter/Colab without extra setup",
            priority=3,
        ),
    ]

    plan = NotebookPlan(
        title=f"LangGraph Workflow: {prompt[:48]}",
        sections=[
            "Setup",
            "State Definition",
            "Tools",
            "Nodes",
            "Graph Construction",
            "Execution",
        ],
        cell_count_estimate=12,
        patterns_used=[architecture_type],
        architecture_type=architecture_type,
    )

    cells: List[CellSpec] = [
        CellSpec(
            cell_type="markdown",
            content=f"# {plan.title}\nGenerated by LangGraph Notebook Foundry",
            section="intro",
        ),
        CellSpec(
            cell_type="code",
            content="!pip install -q langgraph langchain-openai",
            section="setup",
        ),
    ]

    if architecture_type == "router":
        routes = ["search", "analyze", "summarize"]
        route_purposes = {
            "search": "Search for information",
            "analyze": "Analyze data and identify patterns",
            "summarize": "Condense content into summaries",
        }

        # State
        cells.append(CellSpec(
            cell_type="code",
            content=RouterPattern.generate_state_code(),
            section="state_definition"
        ))

        # Router node
        cells.append(CellSpec(
            cell_type="code",
            content=RouterPattern.generate_router_node_code(routes),
            section="nodes"
        ))

        # Route nodes
        for route in routes:
            cells.append(CellSpec(
                cell_type="code",
                content=RouterPattern.generate_route_node_code(route, route_purposes[route]),
                section="nodes"
            ))

        # Graph
        cells.append(CellSpec(
            cell_type="code",
            content=RouterPattern.generate_graph_code(routes),
            section="graph"
        ))

    elif architecture_type == "subagents":
        subagents = ["researcher", "writer", "reviewer"]
        descriptions = {
            "researcher": "Gathers information",
            "writer": "Drafts content",
            "reviewer": "Reviews content",
        }

        # State
        cells.append(CellSpec(
            cell_type="code",
            content=SubagentsPattern.generate_state_code(),
            section="state_definition"
        ))

        # Supervisor
        cells.append(CellSpec(
            cell_type="code",
            content=SubagentsPattern.generate_supervisor_code(subagents, descriptions),
            section="nodes"
        ))

        # Subagents
        for agent in subagents:
            cells.append(CellSpec(
                cell_type="code",
                content=SubagentsPattern.generate_subagent_code(agent, descriptions[agent]),
                section="nodes"
            ))

        # Graph
        cells.append(CellSpec(
            cell_type="code",
            content=SubagentsPattern.generate_graph_code(subagents),
            section="graph"
        ))
    else:
        cells.append(CellSpec(
            cell_type="code",
            content="from langgraph.graph import StateGraph\n\n# Define your workflow here",
            section="graph",
        ))

    return {
        "constraints": constraints,
        "selected_patterns": {"primary": architecture_type},
        "docs_context": [],
        "notebook_plan": plan,
        "architecture_type": plan.architecture_type,
        "architecture_justification": justification,
        "workflow_design": {
            "entry_point": architecture_type,
            "nodes": [
                {
                    "name": architecture_type,
                    "purpose": "Dispatch to specialists" if architecture_type == "router" else "Coordinate sub-agents",
                }
            ],
        },
        "tools_plan": [],
        "generated_cells": cells,
        "qa_reports": [],
        "repair_attempts": 0,
        "artifacts_manifest": {},
        "generation_complete": True,
        "error_message": None,
    }


async def generate_artifacts(
    prompt: str,
    *,
    output_dir: str | Path,
    mode: GenerationMode = "stub",
    formats: List[str] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    agent_type: str | None = None,
    memory_config: str | None = None,
    custom_endpoint: str | None = None,
    preset: str | None = None,
    graph_style: str | None = None,
    retriever_type: str | None = None,
    document_loader: str | None = None,
    progress_callback: Any | None = None,
) -> GenerationArtifacts:
    """Generate notebook artifacts either in stub or live mode.

    Stub mode produces deterministic outputs without external API calls.
    Live mode invokes the generator graph and requires configured LLM credentials.

    Args:
        prompt: User prompt describing the desired system
        output_dir: Directory to write generation artifacts
        mode: Generation mode ('stub' or 'live')
        formats: List of output formats to generate (ipynb, html, markdown, pdf, docx, zip).
                 If None or empty, generates all formats.
        model: LLM model to use (optional, uses default if not specified)
        temperature: Temperature for LLM sampling (0.0-2.0, optional)
        max_tokens: Maximum tokens for LLM response (optional)
        agent_type: Type of agent architecture (optional, auto-detected if not specified)
        memory_config: Memory configuration for the agent (optional)
        custom_endpoint: Custom API endpoint URL (optional)
        preset: Task preset for optimized settings (optional)
        graph_style: Graph execution style (optional)
        retriever_type: Document retriever type for RAG (optional)
        document_loader: Document loader type (optional)
        progress_callback: Optional callback function(node, percentage, message) for progress tracking
    """
    model, custom_endpoint, agent_type = _validate_generation_options(
        mode=mode,
        model=model,
        custom_endpoint=custom_endpoint,
        agent_type=agent_type,
    )

    require_optional_module(
        "langgraph_system_generator.notebook.composer",
        feature="Artifact generation",
        extra="full",
    )
    require_optional_module(
        "langgraph_system_generator.notebook.exporters",
        feature="Artifact generation",
        extra="full",
    )

    from langgraph_system_generator.notebook.composer import NotebookComposer
    from langgraph_system_generator.notebook.exporters import NotebookExporter

    generation_config = GenerationConfig(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_base=custom_endpoint,
        agent_type=agent_type,
    )

    def _report_progress(node: str, percentage: int, message: str) -> None:
        """Helper to report progress if callback is provided."""
        if progress_callback:
            try:
                progress_callback(node, percentage, message)
            except Exception as e:
                # Log progress callback failures instead of silently swallowing
                logging.warning(
                    f"Progress callback failed for node={node}, percentage={percentage}: {e}",
                    exc_info=True
                )

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    _report_progress("init", 5, "Initializing generation...")

    if mode == "live":
        create_generator_graph = _load_generator_graph()
        if not custom_endpoint and not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("LLM API credentials are required for live generation mode.")
        _report_progress("graph_init", 10, "Creating generator graph...")
        graph = create_generator_graph(generation_config=generation_config)
        _report_progress("graph_invoke", 15, "Invoking generator graph...")
        result = await graph.ainvoke(_default_state(prompt, generation_config))
        _report_progress("graph_complete", 60, "Generator graph completed")
    else:
        _report_progress("stub", 30, "Building stub result...")
        result = _build_stub_result(prompt, agent_type=agent_type)
        _report_progress("stub_complete", 60, "Stub generation complete")

    _report_progress("serialize", 62, "Serializing results...")
    serialized = _serialize(result)
    if "architecture_type" in serialized and serialized.get("architecture_type"):
        architecture_type = serialized.get("architecture_type")
    else:
        selected_patterns = serialized.get("selected_patterns") or {}
        architecture_type = selected_patterns.get("primary") or "router"
    
    plan_title = serialized.get("notebook_plan", {}).get("title") or "Generated Notebook"
    
    manifest: Dict[str, Any] = {
        "prompt": prompt,
        "mode": mode,
        "architecture_type": architecture_type,
        "cell_count": len(serialized.get("generated_cells", []) or []),
        "plan_title": plan_title,
    }
    
    # Persist request metadata for reproducibility and downstream consumers.
    if model:
        manifest["model"] = model
    if temperature is not None:
        manifest["temperature"] = temperature
    if max_tokens is not None:
        manifest["max_tokens"] = max_tokens
    if agent_type:
        manifest["agent_type"] = agent_type
    if memory_config:
        manifest["memory_config"] = memory_config
    if custom_endpoint:
        manifest["custom_endpoint"] = custom_endpoint
    if preset:
        manifest["preset"] = preset
    if graph_style:
        manifest["graph_style"] = graph_style
    if retriever_type:
        manifest["retriever_type"] = retriever_type
    if document_loader:
        manifest["document_loader"] = document_loader

    # Persist helpful artifacts for downstream consumers
    plan = serialized.get("notebook_plan")
    if plan:
        plan_path = target / "notebook_plan.json"
        _write_json(plan_path, plan)
        manifest["plan_path"] = str(plan_path)

    cells = serialized.get("generated_cells")
    if isinstance(cells, list):
        cells_path = target / "generated_cells.json"
        _write_json(cells_path, cells)
        manifest["cells_path"] = str(cells_path)

    # Build and export notebook in requested formats
    if cells:
        _report_progress("compose", 65, "Composing notebook...")
        # Convert serialized cells back to CellSpec objects
        cell_specs = [CellSpec(**cell) for cell in cells]
        
        # Build the notebook
        composer = NotebookComposer(colab_friendly=True)
        notebook = composer.build_notebook(cell_specs, ensure_minimum_sections=True)
        
        # Determine which formats to generate
        if formats is None or not formats:
            formats = list(DEFAULT_EXPORT_FORMATS)
        
        _report_progress("export_init", 70, f"Exporting to {len(formats)} format(s)...")
        exporter = NotebookExporter()
        
        # Export to requested formats
        if "ipynb" in formats:
            _report_progress("export_ipynb", 72, "Exporting to Jupyter notebook...")
            ipynb_path = target / "notebook.ipynb"
            exporter.export_ipynb(notebook, ipynb_path)
            manifest["notebook_path"] = str(ipynb_path)
        
        if "html" in formats:
            try:
                _report_progress("export_html", 78, "Exporting to HTML...")
                html_path = target / "notebook.html"
                exporter.export_to_html(notebook, html_path)
                manifest["html_path"] = str(html_path)
            except Exception as e:
                manifest["html_error"] = str(e)

        if "markdown" in formats:
            try:
                _report_progress("export_markdown", 81, "Exporting to Markdown...")
                markdown_path = target / "notebook.md"
                exporter.export_to_markdown(notebook, markdown_path)
                manifest["markdown_path"] = str(markdown_path)
            except Exception as e:
                manifest["markdown_error"] = str(e)

        if "docx" in formats:
            try:
                _report_progress("export_docx", 84, "Exporting to Word document...")
                docx_path = target / "notebook.docx"
                exporter.export_notebook_to_docx(notebook, docx_path, title=plan_title)
                manifest["docx_path"] = str(docx_path)
            except Exception as e:
                manifest["docx_error"] = str(e)
        
        if "pdf" in formats:
            try:
                _report_progress("export_pdf", 90, "Exporting to PDF...")
                # PDF export requires the notebook to be saved first
                if "ipynb" not in formats:
                    ipynb_path = target / "notebook.ipynb"
                    exporter.export_ipynb(notebook, ipynb_path)
                pdf_path = target / "notebook.pdf"
                exporter.export_to_pdf(ipynb_path, pdf_path, method="webpdf")
                manifest["pdf_path"] = str(pdf_path)
            except Exception as e:
                manifest["pdf_error"] = str(e)
        
        if "zip" in formats:
            try:
                _report_progress("export_zip", 95, "Creating ZIP archive...")
                # Include JSON artifacts in the ZIP
                extra_files = []
                if manifest.get("plan_path"):
                    extra_files.append(manifest["plan_path"])
                if manifest.get("cells_path"):
                    extra_files.append(manifest["cells_path"])
                
                zip_path = target / "notebook_bundle.zip"
                exporter.export_zip(notebook, zip_path, extra_files=extra_files)
                manifest["zip_path"] = str(zip_path)
            except Exception as e:
                manifest["zip_error"] = str(e)

    _report_progress("finalize", 98, "Finalizing artifacts...")
    manifest_path = target / "manifest.json"
    _write_json(manifest_path, manifest)

    _report_progress("complete", 100, "Generation complete!")
    return GenerationArtifacts(
        mode=mode,
        prompt=prompt,
        manifest=manifest,
        manifest_path=str(manifest_path),
        output_dir=str(target),
        result=serialized,
    )


async def _handle_build_index(
    cache_path: str, store_path: str, use_openai: bool, chunk_size: int, chunk_overlap: int
) -> str:
    """Build a documentation index from cached docs."""

    embeddings_module = require_optional_module(
        "langchain_community.embeddings",
        feature="Index building",
        extra="full",
    )
    indexer_module = require_optional_module(
        "langgraph_system_generator.rag.indexer",
        feature="Index building",
        extra="full",
    )
    cache = str(Path(cache_path).resolve())
    store = str(Path(store_path).resolve())
    embeddings = None if use_openai else embeddings_module.FakeEmbeddings(size=32)
    manager = await indexer_module.build_index_from_cache(
        cache_path=cache,
        store_path=store,
        embeddings=embeddings,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return manager.store_path


def _run_generate(args: argparse.Namespace) -> int:
    try:
        artifacts = asyncio.run(
            generate_artifacts(
                args.prompt,
                output_dir=args.output,
                mode=args.mode,
                formats=args.formats,
            )
        )
    except OptionalDependencyError as exc:
        print(f"✗ Failed to generate artifacts: {exc}")
        return 1

    print(f"✓ Generated artifacts in {artifacts['output_dir']}")
    print(f"  Manifest: {artifacts['manifest_path']}")
    if artifacts["manifest"].get("plan_path"):
        print(f"  Plan: {artifacts['manifest']['plan_path']}")
    if artifacts["manifest"].get("cells_path"):
        print(f"  Cells: {artifacts['manifest']['cells_path']}")
    if artifacts["manifest"].get("notebook_path"):
        print(f"  Notebook: {artifacts['manifest']['notebook_path']}")
    if artifacts["manifest"].get("html_path"):
        print(f"  HTML: {artifacts['manifest']['html_path']}")
    if artifacts["manifest"].get("markdown_path"):
        print(f"  Markdown: {artifacts['manifest']['markdown_path']}")
    if artifacts["manifest"].get("docx_path"):
        print(f"  DOCX: {artifacts['manifest']['docx_path']}")
    if artifacts["manifest"].get("pdf_path"):
        print(f"  PDF: {artifacts['manifest']['pdf_path']}")
    if artifacts["manifest"].get("zip_path"):
        print(f"  ZIP Bundle: {artifacts['manifest']['zip_path']}")
    return 0


def _run_build_index(args: argparse.Namespace) -> int:
    try:
        path = asyncio.run(
            _handle_build_index(
                cache_path=args.cache,
                store_path=args.store,
                use_openai=args.use_openai,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
        )
        print(f"✓ Vector index written to {path}")
        return 0
    except (
        FileNotFoundError,
        OptionalDependencyError,
        RuntimeError,
        ValueError,
    ) as exc:  # pragma: no cover - defensive
        print(f"✗ Failed to build index: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LangGraph Notebook Foundry CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate", help="Generate notebook artifacts")
    gen.add_argument("prompt", type=str, help="User prompt describing the system to build")
    gen.add_argument(
        "-o",
        "--output",
        default=str((BASE_DIR / "output").resolve()),
        help="Directory to write artifacts (default: <project>/output)",
    )
    gen.add_argument(
        "--mode",
        choices=["stub", "live"],
        default="stub",
        help="Generation mode. 'stub' avoids external API calls (default).",
    )
    gen.add_argument(
        "--formats",
        nargs="+",
        choices=["ipynb", "html", "markdown", "pdf", "docx", "zip"],
        default=None,
        help="Output formats to generate (default: all formats). Specify one or more.",
    )
    gen.set_defaults(func=_run_generate)

    idx = subparsers.add_parser("build-index", help="Build vector index from cached docs")
    idx.add_argument(
        "--cache",
        default=str(DEFAULT_CACHE_PATH),
        help="Path to cached docs directory (defaults to package data/cached_docs)",
    )
    idx.add_argument(
        "--store",
        default=str(Path(settings.vector_store_path).resolve()),
        help="Path to save the vector index",
    )
    idx.add_argument(
        "--use-openai",
        action="store_true",
        help="Use OpenAI embeddings instead of local fake embeddings.",
    )
    idx.add_argument("--chunk-size", type=int, default=500, help="Chunk size for document splitting")
    idx.add_argument("--chunk-overlap", type=int, default=50, help="Chunk overlap for document splitting")
    idx.set_defaults(func=_run_build_index)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
