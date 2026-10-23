"""New local presentation bundles for subsequent trusted fixture evaluation.

Original generation/publication artifacts are read-only. This module does not
publish cloud objects, import receipt JSON, or execute notebooks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph_system_generator.generator.outcome_models import (
    SupportedGenerationOutcome,
)

from langgraph_system_generator.qa.execution_models import (
    ExecutionCase,
    ExecutionResult,
)
from langgraph_system_generator.qa.execution_qualification import (
    digest,
    qualify_execution,
)


@dataclass(frozen=True)
class EvaluatedBundle:
    outcome: SupportedGenerationOutcome
    manifest: Path
    receipt: Path

    def as_report(self) -> dict[str, Any]:
        return {
            "generation_outcome": self.outcome.model_dump(mode="json"),
            "manifest": str(self.manifest),
            "receipt": str(self.receipt),
        }


def build_evaluated_bundle(
    case: ExecutionCase,
    result: ExecutionResult,
    directory: Path,
    *,
    provenance: dict[str, Any],
    dataset_sha256: str,
    controls_verified: bool,
) -> EvaluatedBundle:
    """Consume only the current supervised runner's typed case result."""
    import nbformat

    from langgraph_system_generator.notebook.exporters import NotebookExporter
    from langgraph_system_generator.qa.outcomes import (
        SUMMARY_SECTIONS,
        candidate_id,
        derive_generation_outcome,
        notebook_candidate_id,
        outcome_markdown,
    )
    from langgraph_system_generator.qa.summary import build_qa_summary

    target = directory / "evaluated"
    target.mkdir(exist_ok=False)
    source = directory / "generated" / "notebook.ipynb"
    manifest_path = directory / "fixture-manifest.json"
    source_bytes = source.read_bytes() if source.is_file() else None
    manifest_bytes = manifest_path.read_bytes() if manifest_path.is_file() else b"{}"
    source_manifest = json.loads(manifest_bytes)
    notebook = (
        nbformat.reads(source_bytes.decode("utf-8"), as_version=4)
        if source_bytes
        else None
    )
    if notebook is not None:
        nbformat.validate(notebook)
        cells_path = directory / "generated" / "generated_cells.json"
        if (
            digest(manifest_bytes) != result.environment.get("source_manifest_sha256")
            or not cells_path.is_file()
            or digest(cells_path.read_bytes())
            != result.environment.get("source_cells_sha256")
        ):
            raise ValueError("Source manifest or cells changed after execution began")
        if not cells_path.is_file() or candidate_id(
            json.loads(cells_path.read_text(encoding="utf-8"))
        ) != notebook_candidate_id(notebook):
            raise ValueError("Exported source and original generated cells differ")
    raw_receipt = directory / "clean-receipt.json"
    evaluation = qualify_execution(
        case,
        result,
        notebook=notebook,
        manifest=source_manifest,
        source_bytes=source_bytes,
        provenance=provenance,
        dataset_sha256=dataset_sha256,
        controls_verified=controls_verified,
        raw_receipt_sha256=digest(raw_receipt.read_bytes()),
    )
    receipt_path = target / "evaluation-receipt.json"
    receipt_path.write_bytes(
        json.dumps(evaluation.receipt, sort_keys=True, indent=2).encode("utf-8")
    )
    if digest(receipt_path.read_bytes()) != evaluation.summary.receipt_sha256:
        raise ValueError("Written qualification receipt digest mismatch")
    original_outcome = source_manifest.get("generation_outcome", {})
    repair = original_outcome.get("repair", {})
    reports = source_manifest.get("qa_reports", [])
    outcome = derive_generation_outcome(
        reports,
        candidate_sha256=notebook_candidate_id(notebook) if notebook else None,
        pipeline=original_outcome.get("pipeline", "unknown"),
        has_cells=bool(notebook),
        artifacts_present=bool(notebook),
        artifacts_available=bool(notebook),
        repair_attempts=repair.get("attempts", 0),
        max_repair_attempts=repair.get("limit", 0),
        rollback_used=repair.get("rollback_used", False),
        execution_evaluation=evaluation,
    )
    files = [receipt_path]
    if notebook is not None:
        # Copy exact source bytes before changing only derived Markdown.
        assert source_bytes is not None
        source_copy = target / (
            "executed-source.ipynb"
            if result.attempted_cells
            else "source-notebook.ipynb"
        )
        source_copy.write_bytes(source_bytes)
        if digest(source_copy.read_bytes()) != result.notebook_sha256:
            raise ValueError("Executed source changed before presentation export")
        files.append(source_copy)
        notebook.cells = [
            cell
            for cell in notebook.cells
            if not (
                cell.cell_type == "markdown"
                and any(
                    cell.metadata.get(marker) in SUMMARY_SECTIONS
                    for marker in ("section", "kind")
                )
            )
        ]
        notebook.cells.append(
            nbformat.v4.new_markdown_cell(
                outcome_markdown(outcome, reports),
                metadata={
                    "section": "generation_outcome",
                    "kind": "generation_outcome",
                },
            )
        )
        if notebook_candidate_id(notebook) != outcome.candidate.sha256:
            raise ValueError("Presentation changed the executable candidate")
        exporter = NotebookExporter()
        ipynb, html, bundle = (
            target / name
            for name in ("notebook.ipynb", "notebook.html", "notebook_bundle.zip")
        )
        exporter.export_ipynb(notebook, ipynb)
        exporter.export_to_html(notebook, html)
        exporter.export_zip(
            notebook, bundle, extra_files=[html, receipt_path, source_copy]
        )
        files.extend([ipynb, html, bundle])
    inventory = [
        {
            "path": path.name,
            "sha256": digest(path.read_bytes()),
            "size_bytes": path.stat().st_size,
        }
        for path in files
    ]
    manifest = {
        "evaluation_kind": "subsequent_trusted_fixture_evaluation",
        "generation_outcome": outcome.model_dump(mode="json"),
        "source_generation_outcome": original_outcome,
        "source_artifact": {
            "notebook_sha256": digest(source_bytes) if source_bytes else None,
            "manifest_sha256": digest(manifest_bytes),
            "publication_facts": source_manifest.get("artifact_contract", {}),
        },
        "qa_reports": reports,
        "qa_summary": build_qa_summary(reports, outcome),
        "artifact_inventory": inventory,
        "presentation_note": "Source notebook is included; executed cells are recorded in the receipt. Derived QA prose changed afterward.",
    }
    output_manifest = target / "manifest.json"
    output_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if json.loads(output_manifest.read_text(encoding="utf-8")) != manifest:
        raise ValueError("Written evaluated manifest mismatch")
    if source_bytes is not None and source.read_bytes() != source_bytes:
        raise ValueError("Original generation notebook changed")
    if manifest_path.is_file() and manifest_path.read_bytes() != manifest_bytes:
        raise ValueError("Original generation manifest changed")
    return EvaluatedBundle(outcome, output_manifest, receipt_path)
