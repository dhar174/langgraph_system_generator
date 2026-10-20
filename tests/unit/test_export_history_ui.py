"""Focused tests for export and history UI controls."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from bs4 import BeautifulSoup


def _static_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parent.parent.parent
    static_dir = repo_root / "src/langgraph_system_generator/api/static"
    return static_dir / "index.html", static_dir / "app.js"


def test_history_quick_actions_exist():
    """Verify quick actions exist for rerunning and copying the last prompt."""
    html_file, _ = _static_paths()
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    rerun_button = soup.find(id="rerunLastBtn")
    assert rerun_button is not None, "Missing rerunLastBtn"
    assert (
        rerun_button.get("disabled") is not None
    ), "rerunLastBtn should start disabled"

    copy_button = soup.find(id="copyLastPromptBtn")
    assert copy_button is not None, "Missing copyLastPromptBtn"
    assert (
        copy_button.get("disabled") is not None
    ), "copyLastPromptBtn should start disabled"


def test_output_formats_include_markdown_checkbox():
    """Verify Markdown is available as a selectable output format."""
    html_file, _ = _static_paths()
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "html.parser")

    markdown_checkbox = soup.find(
        "input", {"type": "checkbox", "name": "formats", "value": "markdown"}
    )
    assert markdown_checkbox is not None, "Missing Markdown output format checkbox"


def test_app_js_uses_safe_artifact_download_urls():
    """Verify download links are routed through the backend artifact endpoint."""
    _, js_file = _static_paths()
    content = js_file.read_text(encoding="utf-8")

    assert "function buildArtifactDownloadUrl(reference)" in content
    assert (
        "/artifacts?run_id=${encodeURIComponent(runId)}&artifact=${encodeURIComponent(artifact)}"
        in content
    )
    assert "artifact.api_download_path" in content
    assert "artifact_contract" in content
    assert "/artifacts?path=" not in content
    assert "Manifest (JSON)" in content
    assert "copyLastPromptFromHistory" in content
    assert "rerunLastBtn.addEventListener('click'" in content


def test_browser_generation_mode_and_connection_states_are_explicit():
    _, js_file = _static_paths()
    content = js_file.read_text(encoding="utf-8")
    assert "serverCapabilities.generation_enabled === false" in content
    assert "serverCapabilities.async_generation === false" in content
    assert "startSyncGeneration(data)" in content
    assert "startAsyncGeneration(data)" in content
    assert "new EventSource(streamUrl)" in content
    assert "Reconnecting to progress stream" in content
    assert "payload.result_url" in content
    assert "fetchCompletedJobResult(resultUrl.pathname" in content
    assert "local artifact references may have expired" in content


def test_browser_stream_transport_disconnect_does_not_reject_generation():
    """Execute the actual browser functions with a deterministic fake EventSource."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable for executable browser-function regression")
    _, js_file = _static_paths()
    content = js_file.read_text(encoding="utf-8")
    url_helper = content[
        content.index("function buildArtifactDownloadUrl(") : content.index(
            "function showToast("
        )
    ]
    errors_and_close = content[
        content.index("function extractErrorMessage(") : content.index("// Show error")
    ]
    stream = content[
        content.index("function streamGeneration(") : content.index(
            "async function startAsyncGeneration("
        )
    ]
    harness = r"""
const assert = require('node:assert/strict');
const window = { location: { origin: 'https://unit.test' } };
let currentEventSource = null;
const progressPercentage = { textContent: '10' };
const progress = [];
function showProgress(...args) { progress.push(args); }
class EventSource {
    static CLOSED = 2;
    constructor(url) { this.url = url; this.listeners = {}; this.readyState = 1; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    close() { this.readyState = 2; }
    fire(name, data) { return (this.listeners[name] || this.onerror)(data === undefined ? {} : { data: JSON.stringify(data) }); }
}
let fetchFailures = [];
let fetchCalls = 0;
const setTimeout = (callback) => { callback(); };
async function fetch(path) {
    fetchCalls += 1;
    assert.equal(path, '/jobs/example/result');
    const failure = fetchFailures.shift();
    if (failure instanceof Error) { throw failure; }
    if (failure) { return {ok: false, status: failure, json: async () => ({})}; }
    return { ok: true, status: 200, json: async () => ({success: true, manifest: {cell_count: 7}}) };
}
"""
    scenarios = r"""
(async () => {
    assert.equal(extractErrorMessage({}, '  Result unavailable  '), 'Result unavailable');
    assert.equal(extractErrorMessage({detail: {}}, 'Result unavailable'), 'Result unavailable');
    assert.equal(extractErrorMessage({message: 'Specific error'}, 'Fallback'), 'Specific error');
    assert.equal(extractErrorMessage({}, {error: 'Object fallback'}), 'Object fallback');
    assert.match(extractErrorMessage({}, '  '), /Generation failed/);
    let outcome = 'pending';
    const promise = streamGeneration('/stream/example');
    promise.then(() => outcome = 'resolved', () => outcome = 'rejected');
    const source = currentEventSource;
    source.fire('error');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(outcome, 'pending');
    assert.equal(source.readyState, 1);
    assert.ok(progress.some(args => args[0] === 'reconnecting'));
    await source.fire('complete', {success: true, result_url: '/jobs/example/result'});
    const result = await promise;
    assert.equal(result.manifest.cell_count, 7);
    assert.equal(source.readyState, EventSource.CLOSED);
    for (const failures of [[new Error('offline')], [503, 429]]) {
        fetchFailures = [...failures];
        const before = fetchCalls;
        const retry = streamGeneration('/stream/example');
        await currentEventSource.fire('complete', {result_url: '/jobs/example/result'});
        assert.equal((await retry).manifest.cell_count, 7);
        assert.equal(fetchCalls - before, failures.length + 1);
    }
    for (const [failures, attempts, message] of [
        [[404], 1, /no longer available/],
        [[503, 503, 503], 3, /Generation completed.*Result reference: \/jobs\/example\/result/],
        [[new Error('offline'), new Error('offline'), new Error('offline')], 3, /Generation completed.*Result reference: \/jobs\/example\/result/],
    ]) {
        fetchFailures = [...failures];
        const before = fetchCalls;
        const retry = streamGeneration('/stream/example');
        const rejection = assert.rejects(retry, message);
        await currentEventSource.fire('complete', {result_url: '/jobs/example/result'});
        await rejection;
        assert.equal(fetchCalls - before, attempts);
    }
    const failed = streamGeneration('/stream/failed');
    const rejected = assert.rejects(failed, /cancelled/);
    currentEventSource.fire('error', {error: 'Generation cancelled', status: 'cancelled'});
    await rejected;
    const unavailable = streamGeneration('/stream/lost');
    const lost = assert.rejects(unavailable, /unavailable/);
    currentEventSource.fire('error', {error: 'Job unavailable in this process', status: 'unavailable'});
    await lost;
    const disconnected = streamGeneration('/stream/closed');
    const closed = assert.rejects(disconnected, /Connection to the progress stream was lost/);
    currentEventSource.readyState = EventSource.CLOSED;
    currentEventSource.fire('error');
    await closed;
    const runId = 'a'.repeat(32);
    const valid = `/artifacts?run_id=${runId}&artifact=notebook.ipynb`;
    assert.equal(buildArtifactDownloadUrl(valid), valid);
    for (const ref of ['/artifacts?path=/app/.env', '/app/notebook.ipynb', `https://evil.test${valid}`, `/artifacts?run_id=${runId}&artifact=../secret`]) {
        assert.equal(buildArtifactDownloadUrl(ref), null);
    }
    console.log(JSON.stringify({transport_reconnect: true, completion_fetch: true, cancelled: true, unavailable: true, safe_links: true}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-"],
        input=harness + url_helper + errors_and_close + stream + scenarios,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert all(json.loads(result.stdout).values())
