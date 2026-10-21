"""Credential-free durable qualification. Setup/install is deliberately separate.

Run with a task-private virtualenv Python. See docs/durable-api-rollout.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "scripts" / "qualification_support"
CORE = [
    "test_optional_dependency_guards.py",
    "test_worker_import_safety.py",
    "test_async_job_lifecycle.py",
    "test_durable_job_contracts.py::test_imports_without_cloud_credentials_or_network",
]
SDK = [
    "test_durable_job_contracts.py",
    "test_job_identity.py",
    "test_firestore_job_store.py",
    "test_managed_dispatch.py",
    "test_managed_worker.py",
    "test_private_artifacts.py",
    "test_worker_identity.py",
    "test_worker_configuration.py",
    "test_worker_provider_policy.py",
    "test_durable_api.py",
    "test_durable_browser.py",
    "test_worker_import_safety.py",
    "test_optional_dependency_guards.py",
    "test_durable_qualification_runner.py",
]
EMULATOR = [
    "tests/integration/test_firestore_job_emulator.py",
    "tests/integration/test_durable_api_emulator.py",
]
EMULATOR_REQUIRED = {
    EMULATOR[0] + "::test_emulator_acceptance_contention_and_fresh_instance_replay",
    EMULATOR[0]
    + "::test_emulator_new_process_recovers_lost_worker_and_rejects_old_fence",
    EMULATOR[1]
    + "::test_separate_api_worker_processes_survive_loss_and_read_same_committed_result",
    EMULATOR[0] + "::test_emulator_independent_processes_cannot_both_claim",
}
WINDOWS_ONLY = {
    "tests/unit/test_async_job_lifecycle.py::test_output_parent_accepts_root_case_alias_without_changing_child_case": "Windows path casing contract",
    "tests/unit/test_async_job_lifecycle.py::test_output_parent_rejects_windows_parent_alias": "Windows trailing-space path alias",
}
SDK_MODULES = [
    "google.cloud.firestore",
    "google.cloud.tasks_v2",
    "google.cloud.storage",
    "google.oauth2.id_token",
    "jwt",
    "cryptography.hazmat.primitives.asymmetric.ec",
]


def environment(private: Path) -> dict[str, str]:
    """Allow OS execution essentials only, then set explicit test controls."""
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        env[name] = str(private)
    env.update(
        PYTHONPATH=os.pathsep.join((str(SUPPORT), str(ROOT / "src"), str(ROOT))),
        PYTHONNOUSERSITE="1",
        PYTHONUNBUFFERED="1",
        PYTHON_DOTENV_DISABLED="1",
        LNF_DISABLE_DOTENV="1",
        LNF_ENV_FILE="",
        LNF_QUALIFICATION_GUARD="1",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        ANONYMIZED_TELEMETRY="false",
        DISABLE_GCS_PYTHON_CLIENT_OTEL_BUCKET_METADATA="true",
        GCE_METADATA_HOST="127.0.0.1:9",
        GCE_METADATA_IP="127.0.0.1",
        NO_PROXY="127.0.0.1,localhost,::1",
        CLOUDSDK_CONFIG=str(private / "gcloud"),
        JUPYTER_CONFIG_DIR=str(private / "jupyter"),
        IPYTHONDIR=str(private / "ipython"),
    )
    return env


def stop(process: subprocess.Popen, identity) -> None:
    """Bounded cleanup of this process and its descendants only."""
    import psutil

    # Popen retains the original OS handle. Do not look up a reaped/reused PID.
    if process.poll() is not None:
        return
    try:
        if not identity.is_running():
            return
        descendants = identity.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    if process.poll() is None:
        process.terminate()
    _, alive = psutil.wait_procs(descendants, timeout=5)
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run(command, env, log, timeout):
    import psutil

    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT
        )
        identity = psutil.Process(process.pid)
        try:
            return process.wait(timeout=timeout)
        finally:
            stop(process, identity)


def account(collection: Path, junit: Path, allow_skips=None):
    """Fail closed on empty/missing/partial results, skips, errors or failures."""
    ids = json.loads(collection.read_text(encoding="utf-8"))
    if not ids or len(set(ids)) != len(ids):
        raise RuntimeError("empty or duplicate test collection")
    cases = ET.parse(junit).getroot().findall(".//testcase")
    results = {}
    for case in cases:
        node = (
            case.attrib["classname"].replace(".", "/") + ".py::" + case.attrib["name"]
        )
        if node in results:
            raise RuntimeError("duplicate JUnit test result: " + node)
        results[node] = case
    if set(results) != set(ids):
        raise RuntimeError("JUnit identities do not match collected tests")
    skipped = []
    for node, case in results.items():
        if case.find("failure") is not None or case.find("error") is not None:
            raise RuntimeError("failed test: " + node)
        skip = case.find("skipped")
        if skip is not None:
            reason = skip.attrib.get("message", "")
            skipped.append({"test": node, "reason": reason})
            if (allow_skips or {}).get(node) != reason:
                raise RuntimeError("unexpected skip: " + node + ": " + reason)
    return {
        "collected": len(ids),
        "passed": len(ids) - len(skipped),
        "skipped": skipped,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=("core", "sdk", "emulator"), required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--emulator-jar", type=Path)
    parser.add_argument("--java", default="java")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--startup-timeout", type=int, default=60)
    parser.add_argument("--test-timeout", type=int, default=900)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    receipt_dir = args.receipts.resolve()
    receipt_dir.mkdir(parents=True, exist_ok=False)
    receipt = {
        "level": args.level,
        "python": sys.version,
        "platform": platform.platform(),
        "source": str(ROOT),
        "runs": [],
        "exit": 1,
    }
    emulator = None
    emulator_identity = None
    emulator_log = None
    temporary = tempfile.TemporaryDirectory(prefix="lnf-qualification-")
    try:
        try:
            import psutil
        except ImportError:
            raise RuntimeError(
                "psutil prerequisite missing; install it in the task virtualenv"
            ) from None
        if sys.prefix == sys.base_prefix:
            raise RuntimeError("use a task-private virtualenv Python")
        if (
            args.repeat < 1
            or not 0 < args.port < 65536
            or args.startup_timeout <= 0
            or args.test_timeout <= 0
        ):
            raise RuntimeError("repeat and port must be positive and valid")
        directory = temporary.name
        private = Path(directory)
        env = environment(private)
        preflight = (
            "import importlib,json,sys; from importlib.metadata import version; "
            "from pathlib import Path; import psutil; "
            "import langgraph_system_generator as p; "
            f"assert Path(p.__file__).resolve().is_relative_to(Path({str(ROOT / 'src')!r})); "
            f"mods={SDK_MODULES if args.level != 'core' else []!r}; "
            "[importlib.import_module(m) for m in mods]; "
            "print(json.dumps({'import':p.__file__,'versions':{d:version(d) for d in "
            "['pytest','pydantic','psutil']+(['google-cloud-firestore','google-cloud-tasks',"
            "'google-cloud-storage','google-auth','PyJWT'] if mods else [])}}))"
        )
        code = run(
            [sys.executable, "-c", preflight], env, receipt_dir / "preflight.log", 60
        )
        if code:
            raise RuntimeError("dependency/import preflight failed; see preflight.log")
        # SDK support warnings are retained in the log; the final line is JSON.
        receipt["preflight"] = json.loads(
            (receipt_dir / "preflight.log").read_text(encoding="utf-8").splitlines()[-1]
        )
        if args.level == "sdk" and shutil.which("node", path=env.get("PATH")) is None:
            raise RuntimeError("Node is required for the durable browser tests")
        if args.level == "core":
            code = run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from importlib.metadata import distributions; "
                        "assert not any(d.metadata['Name'].startswith('google-cloud-') "
                        "for d in distributions())"
                    ),
                ],
                env,
                receipt_dir / "no-sdk.log",
                30,
            )
            if code:
                raise RuntimeError(
                    "core level requires an environment without cloud SDKs"
                )
        if args.level == "emulator":
            if not args.emulator_jar or not args.emulator_jar.is_file():
                raise RuntimeError(
                    "--emulator-jar must name an installed official emulator"
                )
            java = shutil.which(args.java)
            if java is None:
                raise RuntimeError("Java 21+ missing; supply --java")
            code = run([java, "-version"], env, receipt_dir / "java.log", 30)
            if code:
                raise RuntimeError("Java preflight failed")
            java_text = (receipt_dir / "java.log").read_text(encoding="utf-8")
            major = re.search(r'version "(\d+)', java_text)
            if major is None or int(major.group(1)) < 21:
                raise RuntimeError("Java 21+ is required")
            receipt["java"] = java_text.strip()
            receipt["emulator_sha256"] = hashlib.sha256(
                args.emulator_jar.read_bytes()
            ).hexdigest()
            receipt["emulator_version"] = (
                "1.22.0"
                if receipt["emulator_sha256"]
                == "9b6498b7f62714d67f48f59b3818883cd682dbcd46b9f59511de81c97bb5166c"
                else "unrecognized JAR (see SHA-256)"
            )
            # Refuse an occupied port; never adopt or shut down another emulator.
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", args.port))
            env["FIRESTORE_EMULATOR_HOST"] = f"127.0.0.1:{args.port}"
            env["LNF_TEST_FIRESTORE_EMULATOR"] = "1"
            emulator_log = (receipt_dir / "emulator.log").open("w", encoding="utf-8")
            command = [
                java,
                "-jar",
                str(args.emulator_jar.resolve()),
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ]
            receipt["emulator_command"] = command
            emulator = subprocess.Popen(
                command,
                cwd=private,
                env=env,
                stdout=emulator_log,
                stderr=subprocess.STDOUT,
            )
            emulator_identity = psutil.Process(emulator.pid)
            receipt["emulator_pid"] = emulator.pid
            deadline = time.monotonic() + args.startup_timeout
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while True:
                if emulator.poll() is not None:
                    raise RuntimeError(
                        "emulator exited during startup; see emulator.log"
                    )
                try:
                    url = (
                        f"http://127.0.0.1:{args.port}/v1/projects/demo-lnf-readiness/"
                        "databases/(default)/documents/qualification"
                    )
                    with opener.open(url, timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("emulator readiness timed out")
                time.sleep(0.2)
        suites = (
            EMULATOR
            if args.level == "emulator"
            else [
                "tests/unit/" + name for name in (CORE if args.level == "core" else SDK)
            ]
        )
        for index in range(args.repeat):
            project = "demo-lnf-" + uuid.uuid4().hex[:16]
            env["LNF_PROBE_PROJECT"] = project
            env["LNF_TEST_PROJECT"] = project
            collection = receipt_dir / f"collection-{index}.json"
            junit = receipt_dir / f"junit-{index}.xml"
            env["LNF_QUALIFICATION_COLLECTION"] = str(collection)
            command = [
                sys.executable,
                "-m",
                "pytest",
                *suites,
                "-v",
                "-rs",
                "--asyncio-mode=auto",
                "-o",
                "junit_family=xunit1",
                "-p",
                "collection_plugin",
                "--junitxml=" + str(junit),
            ]
            code = run(
                command, env, receipt_dir / f"pytest-{index}.log", args.test_timeout
            )
            entry = {"project": project, "command": command, "exit": code}
            receipt["runs"].append(entry)
            entry.update(
                account(collection, junit, WINDOWS_ONLY if os.name != "nt" else {})
            )
            ids = set(json.loads(collection.read_text(encoding="utf-8")))
            if args.level == "emulator" and not EMULATOR_REQUIRED <= ids:
                raise RuntimeError("required emulator tests not collected")
            if any(
                not any(node == suite or node.startswith(suite + "::") for node in ids)
                for suite in suites
            ):
                raise RuntimeError("a designated suite collected no tests")
            if code:
                raise RuntimeError(f"pytest exited {code}")
        receipt["exit"] = 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.TimeoutExpired,
        ET.ParseError,
    ) as exc:
        receipt["error"] = str(exc)
    finally:
        if emulator is not None:
            receipt["emulator_terminated_by_runner"] = emulator.poll() is None
            stop(emulator, emulator_identity)
            receipt["emulator_exit"] = emulator.returncode
        if emulator_log is not None:
            emulator_log.close()
        temporary.cleanup()
        path = receipt_dir / "receipt.json"
        path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        assert json.loads(path.read_text(encoding="utf-8")) == receipt
        print(json.dumps(receipt, indent=2))
    return receipt["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
