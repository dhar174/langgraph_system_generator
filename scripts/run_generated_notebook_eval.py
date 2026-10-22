"""Repository-only runner for trusted generated notebook behavior evaluations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from qualification_support.process_scope import ProcessScope
from qualification_support.resource_limits import configure_limits

from langgraph_system_generator.constants import _compute_base_output
from langgraph_system_generator.qa.execution_models import (
    ExecutionCase,
    ExecutionDataset,
    ExecutionResult,
)
from langgraph_system_generator.utils.credential_redaction import (
    _sanitize_text_credentials,
)

DEFAULT_DATASET = REPO_ROOT / "tests/evaluation/generated_notebook_cases.json"
MUTATIONS = {
    "runtime-failure": "support-router-v1",
    "wrong-route": "support-router-v1",
    "unreachable-tool": "chatbot-tool-v1",
    "nontermination": "support-router-v1",
}


def mutation_detected(clean: ExecutionResult, mutant: ExecutionResult) -> bool:
    """Require evidence of the intended defect, never an unrelated setup failure."""
    if not (
        clean.status == "passed"
        and mutant.status == "failed"
        and mutant.mutation_applied
        and mutant.cleanup_verified
        and mutant.candidate_sha256 != clean.candidate_sha256
        and mutant.original_candidate_sha256 == clean.candidate_sha256
    ):
        return False
    failed = {item.name for item in mutant.assertions if not item.passed}
    if mutant.mutation == "runtime-failure":
        return any(
            error.get("phase") == "notebook_execution"
            and error.get("kernel_error_type") == "RuntimeError"
            for error in mutant.errors
        )
    if mutant.mutation == "wrong-route":
        return not mutant.errors and "billing:executed_nodes" in failed
    if mutant.mutation == "unreachable-tool":
        return not mutant.errors and "tool-turn:actual_tool_executions" in failed
    if mutant.mutation == "nontermination":
        return mutant.timed_out and any(
            error.get("type") == "CellTimeoutError"
            and isinstance(error.get("timeout_seconds"), int)
            and error["timeout_seconds"] > 0
            and error.get("timeout_seconds")
            == mutant.environment.get("nbclient_timeout_seconds")
            and (
                error.get("derived_cell", {}).get("role") == "behavioral_probe"
                or error.get("derived_cell", {}).get("section") == "execution"
            )
            for error in mutant.errors
        )
    return False


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def output_root(path: Path) -> Path:
    """Use the same resolved trusted root as shared generation; reject traversal."""
    base = Path(_compute_base_output()).resolve()
    if ".." in path.parts:
        raise ValueError("Output traversal is not permitted")
    target = path.resolve()
    if not target.is_relative_to(base) or target == base:
        raise ValueError("Evaluation output must be a child of the trusted output root")
    target.mkdir(parents=True, exist_ok=True)
    # Existing artifacts must never be overwritten by an independent run.
    if any(target.iterdir()):
        raise ValueError("Evaluation output must be empty")
    return target


def child_environment(work: Path, directory: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}
    }
    for name in [
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "IPYTHONDIR",
        "JUPYTER_CONFIG_DIR",
        "JUPYTER_RUNTIME_DIR",
    ]:
        location = work / name.lower()
        location.mkdir()
        env[name] = str(location)
    env.update(
        PYTHONPATH=os.pathsep.join(
            [str(REPO_ROOT / "scripts/qualification_support"), str(REPO_ROOT / "src")]
        ),
        LNF_QUALIFICATION_GUARD="1",
        PYTHON_DOTENV_DISABLED="1",
        LNF_DISABLE_DOTENV="1",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        ANONYMIZED_TELEMETRY="false",
        DO_NOT_TRACK="1",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        OPENAI_API_KEY="lnf-evaluation-synthetic",
        BASE_OUTPUT_DIR=str(directory),
        PYTHONIOENCODING="utf-8",
    )
    return env


def stop_observed_descendants(observed: dict) -> None:
    """Reap observed processes, including kernels that create a POSIX session."""
    targets = []
    for (pid, created), process in observed.items():
        try:
            if process.is_running() and process.create_time() == created:
                process.kill()  # psutil also checks PID reuse before signaling.
                targets.append(process)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    _, alive = psutil.wait_procs(targets, timeout=5)
    live = []
    for process in alive:
        try:
            if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                live.append(process.pid)
        except psutil.NoSuchProcess:
            continue
    if live:
        raise RuntimeError(f"Observed descendants survived cleanup: {live}")


def run_case(
    case: ExecutionCase, root: Path, provenance: dict, mutation: str | None = None
) -> ExecutionResult:
    directory = root / case.id
    directory.mkdir(exist_ok=True)
    label = mutation or "clean"
    receipt = directory / f"{label}-receipt.json"
    result = ExecutionResult(
        case_id=case.id,
        fixture=case.fixture,
        mutation=mutation,
        **provenance,
        limitations=[
            *case.untested,
            "Trusted fixtures only; Python socket guard is bypassable by native or hostile code",
            "No filesystem access sandbox; child has the current user's OS privileges",
            "No environment-smoke, production qualification, or live-provider claim",
        ],
    )
    started = time.monotonic()
    scope = None
    process = None
    descendants = {}
    cleaned = False
    captured = bytearray()
    overflow = threading.Event()
    try:
        scope = ProcessScope()
        limits = configure_limits(scope, case.memory_mb, case.cpu_seconds)
        result.isolation = {
            "level": "trusted-fixture child process + kernel",
            "process_tree": (
                "Windows Job Object" if os.name == "nt" else "POSIX session"
            ),
            "network": "Python TCP connect, UDP sendto, DNS and grpc loopback guard; native sockets uncontained",
            "working_directory": "temporary",
            "cell_timeout_seconds": case.cell_timeout,
            "total_timeout_seconds": case.total_timeout,
            "memory_mb": case.memory_mb,
            "cpu_seconds": case.cpu_seconds,
            "enforced_limits": limits,
            "capture_bytes": case.capture_bytes,
            "credentials": "allowlisted environment; synthetic fixture key only",
        }
        with tempfile.TemporaryDirectory(
            prefix=f"{label}-", dir=directory
        ) as temporary:
            work = Path(temporary)
            request = work / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "case": case.model_dump(mode="json"),
                        "result": result.model_dump(mode="json"),
                        "receipt": str(receipt),
                        "directory": str(directory),
                        "work": str(work),
                    }
                ),
                encoding="utf-8",
            )
            process = scope.start(
                [
                    sys.executable,
                    "-m",
                    "langgraph_system_generator.qa.execution_evaluation",
                    str(request),
                ],
                cwd=work,
                env=child_environment(work, directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            def drain() -> None:
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        return
                    remaining = case.capture_bytes - len(captured)
                    captured.extend(chunk[: max(0, remaining)])
                    if len(chunk) > remaining:
                        overflow.set()

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            while process.poll() is None:
                try:
                    for child in psutil.Process(process.pid).children(recursive=True):
                        descendants[(child.pid, child.create_time())] = child
                except psutil.NoSuchProcess:
                    pass
                if time.monotonic() - started > case.total_timeout or overflow.is_set():
                    break
                time.sleep(0.05)
            timed_out = process.poll() is None and not overflow.is_set()
            scope.stop(process)  # Also kills descendants after normal child exit.
            stop_observed_descendants(descendants)
            cleaned = True
            result.cleanup_verified = True
            reader.join(timeout=5)
            if reader.is_alive():
                raise RuntimeError(
                    "Child output pipe did not close after process-tree cleanup"
                )
            if receipt.exists():
                result = ExecutionResult.model_validate_json(
                    receipt.read_text(encoding="utf-8")
                )
                result.cleanup_verified = True
            result.isolation["observed_descendant_pids"] = [
                key[0] for key in descendants
            ]
            result.isolation["surviving_observed_descendants"] = []
            if timed_out or overflow.is_set():
                result.status = "failed"
                result.timed_out = timed_out
                result.errors.append(
                    {
                        "phase": "supervision",
                        "type": (
                            "OverallTimeout" if timed_out else "OutputLimitExceeded"
                        ),
                    }
                )
            elif process.returncode != 0 and result.status != "failed":
                result.status = "failed"
                result.resource_limit_outcome = "unknown"
                result.errors.append(
                    {
                        "phase": "child_process",
                        "type": "NonzeroExit",
                        "exit_code": process.returncode,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        result.status = "failed"
        result.errors.append(
            {
                "phase": "isolation_setup_or_cleanup",
                "type": type(exc).__name__,
                "message": _sanitize_text_credentials(str(exc))[:2000],
            }
        )
    finally:
        if scope is not None and not cleaned:
            try:
                if process is not None:
                    try:
                        scope.stop(process)
                    finally:
                        stop_observed_descendants(descendants)
                else:
                    scope.close()
            except Exception as exc:  # noqa: BLE001
                result.status = "failed"
                result.cleanup_verified = False
                result.errors.append(
                    {
                        "phase": "cleanup",
                        "type": type(exc).__name__,
                        "message": _sanitize_text_credentials(str(exc))[:2000],
                    }
                )
    result.runtime_seconds = round(time.monotonic() - started, 3)
    if (
        result.status == "incomplete"
        and result.observations
        and result.cleanup_verified
    ):
        result.status = (
            "passed" if all(item.passed for item in result.assertions) else "failed"
        )
    result = ExecutionResult.model_validate(result.model_dump())
    receipt.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    (directory / f"{label}-process.log").write_text(
        _sanitize_text_credentials(captured.decode("utf-8", errors="replace")),
        encoding="utf-8",
    )
    return result


def run(dataset: ExecutionDataset, root: Path, *, mutations: bool = True) -> dict:
    diff = git_output("diff", "HEAD")
    source_files = {
        str(path.relative_to(REPO_ROOT))
        .replace("\\", "/"): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for source in [
            REPO_ROOT / "src",
            REPO_ROOT / "scripts",
            REPO_ROOT / "tests/evaluation",
        ]
        for path in sorted(source.rglob("*"))
        if path.is_file() and path.suffix in {".py", ".json"}
    }
    provenance = {
        "generator_revision": git_output("rev-parse", "HEAD"),
        "source_dirty": bool(git_output("status", "--porcelain")),
        "source_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "source_tree_sha256": hashlib.sha256(
            json.dumps(source_files, sort_keys=True).encode()
        ).hexdigest(),
        "source_files_sha256": source_files,
    }
    clean = [run_case(case, root, provenance) for case in dataset.cases]
    controls = []
    if mutations:
        for mutation, fixture in MUTATIONS.items():
            case = next(case for case in dataset.cases if case.fixture == fixture)
            clean_result = next(result for result in clean if result.case_id == case.id)
            result = run_case(case, root, provenance, mutation)
            controls.append(
                {
                    "mutation": mutation,
                    "detected": mutation_detected(clean_result, result),
                    "result": result.model_dump(mode="json"),
                }
            )
    passed = (
        all(item.status == "passed" for item in clean)
        and all(item["detected"] for item in controls)
        and mutations
    )
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "dataset": dataset.model_dump(mode="json"),
        "dataset_sha256": hashlib.sha256(
            dataset.model_dump_json().encode()
        ).hexdigest(),
        "cases": [item.model_dump(mode="json") for item in clean],
        "negative_controls": controls,
        "skipped": [] if mutations else ["negative controls"],
        "upload": "disabled",
    }
    (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Generated notebook execution evaluation",
        "",
        f"Overall: {'PASSED' if passed else 'FAILED'}",
        "",
        "| Case | Mode | Behavioral result | Candidate | Cells completed |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case, result in zip(dataset.cases, clean):
        lines.append(
            f"| {case.id} | {case.generator_mode} | {result.status} | {result.candidate_sha256} | {len(result.completed_cells)} |"
        )
    lines.append("")
    for case, result in zip(dataset.cases, clean):
        lines.append(
            f"- {case.id}: [execution receipt]({case.id}/clean-receipt.json); untested: "
            + "; ".join(result.limitations)
        )
        for assertion in result.assertions:
            if not assertion.passed:
                lines.append(f"  - Failed `{assertion.name}`: {assertion.detail}")
        for error in result.errors:
            lines.append(
                f"  - Error: `{error.get('type')}` at {error.get('derived_cell', error.get('phase'))}"
            )
    lines.extend(["", "## Negative controls", ""])
    for control in controls:
        failure_names = [
            item["name"]
            for item in control["result"]["assertions"]
            if not item["passed"]
        ]
        error_types = [item["type"] for item in control["result"]["errors"]]
        lines.append(
            f"- {control['mutation']}: {'detected' if control['detected'] else 'NOT VERIFIED'}; evidence: "
            + ", ".join([*failure_names, *error_types])
        )
    lines.extend(
        [
            "",
            "These receipts are separate from generation_outcome v1; generated_execution remains not_run.",
        ]
    )
    (root / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--output", type=Path, default=REPO_ROOT / "output/generated-notebook-eval"
    )
    args = parser.parse_args(argv)
    dataset = ExecutionDataset.model_validate_json(
        args.dataset.read_text(encoding="utf-8")
    )
    report = run(dataset, output_root(args.output))
    print(
        json.dumps(
            {"passed": report["passed"], "report": str(args.output / "report.json")}
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
