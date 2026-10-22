"""Qualification evidence must fail closed, independently of product behavior."""

import json
import subprocess
import sys
import time

import pytest

from scripts.qualify_durable_backend import (
    PREFLIGHT_PREFIX,
    ROOT,
    account,
    environment,
    read_preflight,
    run,
)


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


def test_class_and_parameterized_junit_identities(tmp_path):
    result = account(
        *evidence(
            tmp_path,
            [
                "tests/unit/test_demo.py::TestRecovery::test_one[a::b.c]",
                "tests/unit/test_demo.py::TestOther::test_one[a::b.c]",
            ],
            '<testcase classname="tests.unit.test_demo.TestRecovery" name="test_one[a::b.c]"/>'
            '<testcase classname="tests.unit.test_demo.TestOther" name="test_one[a::b.c]"/>',
        )
    )
    assert result == {"collected": 2, "passed": 2, "skipped": []}


def test_real_pytest_class_and_parameterized_junit(tmp_path):
    fixture = tmp_path / "test_recovery.py"
    fixture.write_text(
        "import pytest\nclass TestRecovery:\n"
        "    @pytest.mark.parametrize('value', ['a::b.c'])\n"
        "    def test_case(self, value):\n        assert value == 'a::b.c'\n",
        encoding="utf-8",
    )
    env = environment(tmp_path)
    collection = tmp_path / "collection.json"
    junit = tmp_path / "junit.xml"
    env["LNF_QUALIFICATION_COLLECTION"] = str(collection)
    assert (
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(fixture),
                "--rootdir=" + str(tmp_path),
                "-p",
                "collection_plugin",
                "-o",
                "junit_family=xunit1",
                "--junitxml=" + str(junit),
            ],
            env,
            tmp_path / "pytest.log",
            30,
        )
        == 0
    )
    assert account(collection, junit) == {"collected": 1, "passed": 1, "skipped": []}


def test_zombie_is_stopped_even_when_pid_exists(monkeypatch):
    import psutil

    class Zombie:
        def is_running(self):
            return True

        def status(self):
            return psutil.STATUS_ZOMBIE

    monkeypatch.setattr(psutil, "Process", lambda pid: Zombie())
    assert_stopped(123)


def test_preflight_record_survives_teardown_warnings_and_blank_lines(tmp_path):
    log = tmp_path / "preflight.log"
    record = {"import": "checkout/src/__init__.py", "versions": {"pytest": "test"}}
    log.write_text(
        "import warning\n"
        + PREFLIGHT_PREFIX
        + json.dumps(record)
        + "\nResourceWarning: interpreter teardown\n\n  \n",
        encoding="utf-8",
    )
    assert read_preflight(log) == record


@pytest.mark.parametrize(
    "record", ["", "{}", PREFLIGHT_PREFIX + "{}", PREFLIGHT_PREFIX + "bad"]
)
def test_preflight_rejects_missing_or_invalid_record(tmp_path, record):
    log = tmp_path / "preflight.log"
    log.write_text(record, encoding="utf-8")
    with pytest.raises((ValueError, TypeError, RuntimeError)):
        read_preflight(log)


def assert_stopped(pid):
    """A zombie has stopped execution even if container PID 1 never reaps it."""
    import psutil

    deadline = time.monotonic() + 5
    while True:
        try:
            process = psutil.Process(pid)
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return
        except psutil.NoSuchProcess:
            return
        assert time.monotonic() < deadline, f"owned process {pid} is still executing"
        time.sleep(0.05)


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
    log = tmp_path / "timeout.log"
    with pytest.raises(subprocess.TimeoutExpired):
        run(
            [
                sys.executable,
                "-S",  # This trusted PID/sleep fixture needs no SDK/site startup.
                "-c",
                "import os,time; print(os.getpid(),flush=True); time.sleep(60)",
            ],
            environment(tmp_path),
            log,
            10,  # Allow guarded Windows launcher startup before the PID fixture.
        )
    pid = int(log.read_text(encoding="utf-8").strip())
    assert_stopped(pid)


def test_timeout_stops_owned_descendant_tree(tmp_path):
    log = tmp_path / "tree-timeout.log"
    code = (
        "import subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-S','-c','import time; time.sleep(60)']); "
        "print(child.pid,flush=True); time.sleep(60)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, "-S", "-c", code], environment(tmp_path), log, 10)
    assert_stopped(int(log.read_text(encoding="utf-8").strip()))


def test_normal_exit_stops_orphan_without_touching_unrelated_process(tmp_path):
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        log = tmp_path / "normal-exit.log"
        code = (
            "import subprocess,sys; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
            "print(child.pid,flush=True)"
        )
        assert run([sys.executable, "-c", code], environment(tmp_path), log, 10) == 0
        assert_stopped(int(log.read_text(encoding="utf-8").strip()))
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


def test_cleanup_does_not_inspect_reaped_pid():
    from scripts.qualify_durable_backend import stop

    class Exited:
        def poll(self):
            return 0

    class UnrelatedIdentity:
        def is_running(self):
            raise AssertionError("must not inspect a reaped/reused PID")

    stop(Exited(), UnrelatedIdentity())
