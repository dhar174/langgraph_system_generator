"""Qualification evidence must fail closed, independently of product behavior."""

import json
import subprocess
import sys

import pytest

from scripts.qualify_durable_backend import ROOT, account, environment, run


def evidence(tmp_path, collection, cases):
    collected = tmp_path / "collection.json"
    junit = tmp_path / "junit.xml"
    collected.write_text(json.dumps(collection), encoding="utf-8")
    junit.write_text(
        "<testsuites><testsuite>" + cases + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return collected, junit


@pytest.mark.parametrize(
    "collection,cases",
    [
        ([], ""),
        (["tests/unit/test_demo.py::test_one"], ""),
        (
            ["tests/unit/test_demo.py::test_one"],
            '<testcase classname="tests.unit.test_demo" name="test_one"><skipped message="missing SDK"/></testcase>',
        ),
        (
            ["tests/unit/test_demo.py::test_one"],
            '<testcase classname="tests.unit.test_demo" name="test_one"><failure/></testcase>',
        ),
    ],
)
def test_missing_partial_skipped_or_failed_evidence_fails(tmp_path, collection, cases):
    with pytest.raises(RuntimeError):
        account(*evidence(tmp_path, collection, cases))


def test_exact_collection_and_junit_pass(tmp_path):
    result = account(
        *evidence(
            tmp_path,
            ["tests/unit/test_demo.py::test_one"],
            '<testcase classname="tests.unit.test_demo" name="test_one"/>',
        )
    )
    assert result == {"collected": 1, "passed": 1, "skipped": []}


def test_environment_excludes_credentials_and_hosting(monkeypatch, tmp_path):
    for key in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "OPENAI_API_KEY",
        "K_SERVICE",
        "LANGSMITH_API_KEY",
        "LNF_DURABLE_SUBMISSIONS_ENABLED",
        "HTTP_PROXY",
    ):
        monkeypatch.setenv(key, "ambient-must-not-survive")
    env = environment(tmp_path)
    assert "ambient-must-not-survive" not in env.values()
    assert env["LNF_ENV_FILE"] == "" and env["PYTHON_DOTENV_DISABLED"] == "1"
    assert env["USERPROFILE"] == str(tmp_path)


def test_child_guard_denies_external_socket_grpc_and_dotenv(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("QUALIFICATION_SENTINEL=must-not-load\n", encoding="utf-8")
    assert dotenv.read_text(encoding="utf-8").endswith("must-not-load\n")
    code = """
import os,socket
from dotenv import load_dotenv
load_dotenv(os.environ['HOME']+'/.env')
assert 'QUALIFICATION_SENTINEL' not in os.environ
for host in ('metadata.google.internal','169.254.169.254','api.openai.com'):
    try: socket.create_connection((host,443),timeout=.1)
    except OSError as error: assert 'qualification permits loopback' in str(error)
    else: raise AssertionError('external socket permitted')
try:
    import grpc
except ImportError: pass
else:
    for channel in (grpc.insecure_channel, grpc.aio.insecure_channel):
        try: channel('firestore.googleapis.com:443')
        except OSError: pass
        else: raise AssertionError('external native gRPC permitted')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        env=environment(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_timeout_stops_owned_process_and_preserves_log(tmp_path):
    import psutil

    log = tmp_path / "timeout.log"
    with pytest.raises(subprocess.TimeoutExpired):
        run(
            [
                sys.executable,
                "-c",
                "import os,time; print(os.getpid(),flush=True); time.sleep(60)",
            ],
            environment(tmp_path),
            log,
            2,
        )
    pid = int(log.read_text(encoding="utf-8").strip())
    assert not psutil.pid_exists(pid)


def test_timeout_stops_owned_descendant_tree(tmp_path):
    import psutil

    log = tmp_path / "tree-timeout.log"
    code = (
        "import subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "print(child.pid,flush=True); time.sleep(60)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, "-c", code], environment(tmp_path), log, 2)
    assert not psutil.pid_exists(int(log.read_text(encoding="utf-8").strip()))


def test_cleanup_does_not_inspect_reaped_pid():
    from scripts.qualify_durable_backend import stop

    class Exited:
        def poll(self):
            return 0

    class UnrelatedIdentity:
        def is_running(self):
            raise AssertionError("must not inspect a reaped/reused PID")

    stop(Exited(), UnrelatedIdentity())
