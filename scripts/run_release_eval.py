"""Run the local deterministic 1.0 release evaluation gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from langgraph_system_generator.cli import _build_stub_result, _serialize  # noqa: E402


DEFAULT_DATASET = REPO_ROOT / "tests" / "evaluation" / "release_1_0_eval_cases.json"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "release-evaluation" / "release_1_0_eval_report.json"


def _load_dataset(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _edge_count(workflow_design: dict[str, Any]) -> int:
    return len(workflow_design.get("edges") or []) + len(
        workflow_design.get("conditional_edges") or []
    )


def _check_generator_case(case: dict[str, Any]) -> list[str]:
    result = _serialize(
        _build_stub_result(case["prompt"], agent_type=case.get("agent_type"))
    )
    failures: list[str] = []

    expected_architecture = case.get("expected_architecture")
    if expected_architecture and result.get("architecture_type") != expected_architecture:
        failures.append(
            f"expected architecture {expected_architecture!r}, got {result.get('architecture_type')!r}"
        )

    if "graph_design" in case["surfaces"]:
        workflow_design = result.get("workflow_design") or {}
        if not workflow_design.get("nodes"):
            failures.append("workflow_design has no nodes")
        if _edge_count(workflow_design) == 0:
            failures.append("workflow_design has no edges or conditional_edges")

    if "notebook_composition" in case["surfaces"]:
        generated_cells = result.get("generated_cells") or []
        min_cell_count = int(case.get("min_cell_count") or 0)
        if len(generated_cells) < min_cell_count:
            failures.append(
                f"expected at least {min_cell_count} generated cells, got {len(generated_cells)}"
            )
        if not (result.get("notebook_plan") or {}).get("sections"):
            failures.append("notebook_plan has no sections")

    if "qa_repair" in case["surfaces"]:
        qa_repair_feedback = result.get("qa_repair_feedback") or {}
        if qa_repair_feedback.get("unrepaired_failures"):
            failures.append("qa_repair_feedback contains unrepaired failures")
        if result.get("generation_complete") is not True:
            failures.append("generation_complete is not true")

    return failures


def _check_examples_case(case: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for relative_path in case.get("expected_examples") or []:
        if not (REPO_ROOT / relative_path).exists():
            failures.append(f"missing example {relative_path}")
    return failures


def run_evaluation(dataset: dict[str, Any], *, upload_enabled: bool) -> dict[str, Any]:
    case_results = []
    for case in dataset["cases"]:
        failures: list[str] = []
        if any(surface != "examples" for surface in case["surfaces"]):
            failures.extend(_check_generator_case(case))
        if "examples" in case["surfaces"]:
            failures.extend(_check_examples_case(case))

        case_results.append(
            {
                "id": case["id"],
                "surfaces": case["surfaces"],
                "status": "passed" if not failures else "failed",
                "failures": failures,
            }
        )

    failed = sum(1 for case in case_results if case["status"] == "failed")
    return {
        "dataset": dataset["name"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upload": "requested" if upload_enabled else "disabled",
        "summary": {
            "total": len(case_results),
            "passed": len(case_results) - failed,
            "failed": failed,
        },
        "cases": case_results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local 1.0 release evaluation gate.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--no-upload",
        action="store_true",
        default=False,
        help="Keep evaluation local-only. This is the default for CI and release PRs.",
    )
    parser.add_argument(
        "--upload-langsmith",
        action="store_true",
        help="Mark that a LangSmith upload was requested by the caller.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    upload_enabled = bool(args.upload_langsmith and not args.no_upload)
    dataset = _load_dataset(args.dataset)
    report = run_evaluation(dataset, upload_enabled=upload_enabled)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "Release evaluation: "
        f"{report['summary']['passed']}/{report['summary']['total']} passed; "
        f"upload={report['upload']}; report={args.output}"
    )
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
