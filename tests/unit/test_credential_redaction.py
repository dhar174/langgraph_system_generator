"""Synthetic credential completeness and bounded-work regressions."""

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock

import httpx
import pytest

from langgraph_system_generator.utils import credential_redaction as redaction
from langgraph_system_generator.utils.error_handling import GenerationError
from tests.unit.test_durable_job_contracts import OWNER, running, store  # noqa: F401
from tests.unit.test_firestore_job_store import firestore_transport  # noqa: F401


SECRET = "FAKE_REDACTION_SECRET"
PROBE = Path(__file__).resolve().parents[1] / "fixtures/credential_redaction_probe.py"


@pytest.mark.parametrize(
    "padding", [("", " benign"), ("benign ", " benign"), ("benign ", "")]
)
@pytest.mark.parametrize(
    "credential",
    [
        f"access_token={SECRET}",
        f"paſſword={SECRET}",
        f"sİgnature={SECRET}",
        f"sıgnature={SECRET}",
        f'"ſecret": "{SECRET}"',
        f"?client_secret={SECRET}&page=2",
        f'"api_key": "{SECRET}"',
        f"'refresh_token': '{SECRET}'",
        f'api_key="{SECRET}"',
        f"Bearer {SECRET}",
        f"https://user:{SECRET}@example.test/path?token={SECRET}&page=2",
        f"https://[invalid/?token={SECRET}",
    ],
)
def test_secret_at_every_position(credential, padding):
    prefix, suffix = padding
    output = redaction._sanitize_text_credentials(prefix + credential + suffix)
    assert SECRET not in output
    assert prefix + suffix == "" or "benign" in output
    assert "[REDACTED]" in output or "[invalid URL omitted]" in output


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ""),
        (None, ""),
        ("Unicode 雪 café\nbenign", "Unicode 雪 café\nbenign"),
        ("key! token secret=", "key! token secret="),
        ('"key" ! no value', '"key" ! no value'),
        ('"key": ', '"key": '),
        ('"key": ""', '"key": ""'),
        ("key=&page=2", "key=&page=2"),
        ('key= ""', 'key= ""'),
        ("key=[REDACTED]", "key=[REDACTED]"),
        ('"key": "[REDACTED]"', '"key": "[REDACTED]"'),
        ("Bearer [REDACTED]", "Bearer [REDACTED]"),
        (f"雪_client_SECRET \n = {SECRET}", "雪_client_SECRET \n = [REDACTED]"),
        (f'"client_secret" \n : \n "{SECRET}"', '"client_secret" \n : \n "[REDACTED]"'),
        (f'"key": "first\\"{SECRET}"; page=2', '"key": "[REDACTED]"; page=2'),
        (f"'key': 'first\\'{SECRET}'; page=2", "'key': '[REDACTED]'; page=2"),
        (f'"key": "{SECRET}\\', '"key": "[REDACTED]'),
        (f'key="{SECRET}', 'key="[REDACTED]'),
        (f'"key": "{SECRET} apostrophe\' suffix"', '"key": "[REDACTED]"'),
        (f"key={SECRET}&token={SECRET}", "key=[REDACTED]&token=[REDACTED]"),
    ],
)
def test_delimiters_progress_and_safe_controls(text, expected):
    assert redaction._sanitize_text_credentials(text) == expected


def test_valid_url_provenance_and_explicit_endpoint_remain_useful():
    url = (
        f"https://user:{SECRET}@docs.example.test/guide?%61pi_key={SECRET}&page=2#intro"
    )
    safe = "https://user:[REDACTED]@docs.example.test/guide?api_key=[REDACTED]&page=2#intro"
    assert redaction._sanitize_url_for_logging(url) == safe
    assert (
        redaction._sanitize_text_credentials(f"Failed ({url}).", endpoint=url)
        == f"Failed ({safe})."
    )
    assert redaction.sanitize_generation_payload(f"Failed {url}") == "Failed [endpoint]"


@pytest.mark.parametrize(
    "url",
    [
        f"https://[invalid/?api_key={SECRET},suffix",
        f"https://{SECRET}@[invalid/path?%74oken={SECRET}",
    ],
)
def test_malformed_url_is_omitted_in_full(url):
    assert redaction._sanitize_url_for_logging(url) == "[invalid URL omitted]"
    assert SECRET not in redaction._sanitize_text_credentials("Failed " + url)


def test_nested_errors_and_sse_do_not_escape():
    from langgraph_system_generator.api import progress_streaming as progress

    text = f'key={SECRET}&token={SECRET} "client_secret": "{SECRET}" Bearer {SECRET}'
    nested = {"items": [{"message": text}], "password": SECRET}
    payload = GenerationError(text, hint=text, details=nested).to_payload()
    assert SECRET not in json.dumps(payload)
    job_id = progress.create_job()
    try:
        progress.emit_log(job_id, "warning", text, nested)
        progress.emit_error(job_id, text, nested)
        events = progress._active_jobs[job_id].events
        assert len(events) == 2
        assert SECRET not in json.dumps(events)
        assert "[REDACTED]" in json.dumps(events)
    finally:
        progress.discard_job(job_id)


@pytest.mark.asyncio
async def test_structured_api_error_does_not_escape(monkeypatch, tmp_path, caplog):
    from langgraph_system_generator.api import server

    text = f'key={SECRET} "client_secret": "{SECRET}"'
    monkeypatch.setattr(server, "_BASE_OUTPUT", tmp_path)
    monkeypatch.setattr(server, "_resolve_output_dir", lambda *_: tmp_path)
    monkeypatch.setattr(
        server,
        "generate_artifacts",
        AsyncMock(side_effect=GenerationError(text, details={"items": [text]})),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/generate", json={"prompt": "test", "mode": "stub"}
        )
    assert response.status_code == 500, response.text
    assert SECRET not in response.text + caplog.text
    assert "[REDACTED]" in response.text


@pytest.mark.usefixtures("store")
def test_durable_log_redacts_before_clipping(request):
    backend, _ = request.getfixturevalue("store")
    job = running(backend)
    text = f'key={SECRET} "client_secret": "{SECRET}" ' + f"token={SECRET}" * 100
    backend.append_log(
        job.job_id, job.version, job.fencing_token, "worker-a", "warning", text
    )
    page = backend.replay(OWNER, job.job_id)
    serialized = page.model_dump_json()
    assert SECRET not in serialized
    assert "[REDACTED]" in serialized


@pytest.mark.parametrize("family", ["query", "json", "fallback", "tail", "mixed"])
@pytest.mark.parametrize("size", [4096, 16384, 65536])
def test_long_inputs_under_subprocess_watchdog(family, size):
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(PROBE), "candidate", family, str(size)],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert not result.stderr
    observation = json.loads(result.stdout)
    assert observation["size"] == size


def test_scanner_visits_a_linear_number_of_python_steps():
    functions = {
        redaction._redact_named_credentials.__code__,
        redaction._skip_whitespace.__code__,
    }
    steps = 0

    def trace(frame, event, arg):
        nonlocal steps
        if frame.f_code in functions and event == "line":
            steps += 1
        return trace

    unit = (
        'key! "key" ! key= &key="" key=abc& "key": "escaped\\"value" key \n = value& '
    )
    for repetitions in (64, 128, 256):
        text = unit * repetitions + '"key": "unterminated\\'
        steps = 0
        previous_trace = sys.gettrace()
        try:
            sys.settrace(trace)
            redaction._redact_named_credentials(text)
        finally:
            sys.settrace(previous_trace)
        assert steps < 100 * len(text)
